from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import get_pool
from bot.keyboards.territory import territory_keyboard
from bot.keyboards.main_menu import create_realm_keyboard

from bot.services.world import (
    MAX_CONTINENTS,
    TERRITORIES_PER_CONTINENT,
)


router = Router()


def format_date(value):
    if not value:
        return "Fecha desconocida"

    return value.strftime("%d/%m/%Y")


async def render_territories(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True
            )

            await callback.message.edit_text(
                "🏰 <b>Aún no posees un reino.</b>\n\n"
                "Debes fundar tu dominio antes de "
                "administrar tus territorios.",
                reply_markup=create_realm_keyboard()
            )
            return

        provinces = await connection.fetch(
            """
            SELECT
                id,
                name,
                province_number,
                continent,
                region,
                created_at
            FROM provinces
            WHERE realm_id = $1
            ORDER BY province_number ASC
            """,
            realm["id"]
        )

        research_level = await connection.fetchval(
            """
            SELECT level
            FROM realm_research
            WHERE realm_id = $1
              AND research_type = 'provincial_administration'
            """,
            realm["id"]
        ) or 0

    province_available = (
        research_level >= 1
        and len(provinces) == 0
    )

    lines = [
        "🗺 <b>TERRITORIOS DEL REINO</b>",
        "",
        f"🏰 Dominio: <b>{realm['name']}</b>",
        f"📍 Provincias: <b>{len(provinces)}/1</b>",
        "",
        "<b>PROVINCIAS</b>"
    ]

    if provinces:
        for province in provinces:
            location = (
                f"{province['continent']}:{province['region']}"
                if province["continent"] is not None
                else "Ubicación histórica"
            )

            lines.extend([
                "",
                f"🏞 <b>{province['name']}</b>",
                f"   Territorio: <code>{location}</code>",
                f"   Fundada: {format_date(province['created_at'])}"
            ])
    else:
        lines.extend([
            "",
            "<i>Tu reino todavía no tiene provincias.</i>"
        ])

    lines.extend([
        "",
        "⚒ <b>Expansión del reino</b>",
        "La provincia se desbloquea mediante "
        "<b>Administración provincial</b>.",
        "",
        "Cuando la tecnología esté completada, "
        "podrás elegir un territorio completamente "
        "vacío para establecerla.",
        "",
        "Cada reino puede fundar una sola provincia. "
        "El resto de la expansión se basa en el vasallaje."
    ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=territory_keyboard(province_available)
    )


@router.callback_query(
    F.data.in_({"territory", "territory_refresh"})
)
async def territory_handler(callback: CallbackQuery):
    await render_territories(callback)


@router.callback_query(F.data == "province:menu")
async def province_menu_handler(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True
            )
            return

        level = await connection.fetchval(
            """
            SELECT level
            FROM realm_research
            WHERE realm_id = $1
              AND research_type = 'provincial_administration'
            """,
            realm["id"]
        ) or 0

        existing = await connection.fetchval(
            """
            SELECT EXISTS(
                SELECT 1
                FROM provinces
                WHERE realm_id = $1
            )
            """,
            realm["id"]
        )

        if level < 1:
            await callback.answer(
                "Necesitas investigar Administración provincial.",
                show_alert=True
            )
            return

        if existing:
            await callback.answer(
                "Tu reino ya tiene su única provincia.",
                show_alert=True
            )
            return

        last_continent = await connection.fetchval(
            """
            SELECT GREATEST(
                1,
                COALESCE(MAX(continent), 1)
            )
            FROM realms
            """
        )

        last_continent = min(
            int(last_continent),
            MAX_CONTINENTS
        )

        empty_territories = await connection.fetch(
            """
            SELECT
                continents.continent,
                territories.territory
            FROM generate_series(1, $1)
                AS continents(continent)
            CROSS JOIN generate_series(1, $2)
                AS territories(territory)
            WHERE NOT EXISTS (
                SELECT 1
                FROM realms r
                WHERE r.continent = continents.continent
                  AND r.region = territories.territory
            )
            AND NOT EXISTS (
                SELECT 1
                FROM provinces p
                WHERE p.continent = continents.continent
                  AND p.region = territories.territory
            )
            ORDER BY continents.continent, territories.territory
            """,
            last_continent,
            TERRITORIES_PER_CONTINENT
        )

    if not empty_territories:
        await callback.answer(
            "No hay territorios completamente vacíos disponibles.",
            show_alert=True
        )
        return

    builder = InlineKeyboardBuilder()

    for territory in empty_territories:
        continent = territory["continent"]
        region = territory["territory"]

        builder.button(
            text=f"Continente {continent} · Territorio {region}",
            callback_data=f"province:found:{continent}:{region}"
        )

    builder.adjust(1)

    builder.button(
        text="◀ Volver a territorios",
        callback_data="territory"
    )

    builder.adjust(1)

    await callback.answer()

    await callback.message.edit_text(
        "🏞 <b>FUNDACIÓN DE PROVINCIA</b>\n\n"
        f"Reino: <b>{realm['name']}</b>\n\n"
        "Elige un territorio completamente vacío.\n"
        "No puede contener ningún reino ni otra provincia.\n\n"
        "<b>Importante:</b> solo podrás fundar una provincia "
        "durante toda la partida.",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("province:found:"))
async def province_found_handler(callback: CallbackQuery):
    try:
        _, _, continent, territory = callback.data.split(":")
        continent = int(continent)
        territory = int(territory)
    except (ValueError, IndexError):
        await callback.answer(
            "Territorio no válido.",
            show_alert=True
        )
        return

    if not 1 <= continent <= MAX_CONTINENTS:
        await callback.answer(
            "Continente no válido.",
            show_alert=True
        )
        return

    if not 1 <= territory <= TERRITORIES_PER_CONTINENT:
        await callback.answer(
            "Territorio no válido.",
            show_alert=True
        )
        return

    pool = await get_pool()
    error = None
    province_name = None

    async with pool.acquire() as connection:
        async with connection.transaction():
            realm = await connection.fetchrow(
                """
                SELECT id, name
                FROM realms
                WHERE owner_id = $1
                FOR UPDATE
                """,
                callback.from_user.id
            )

            if not realm:
                error = "No tienes un reino."

            else:
                realm_id = realm["id"]

                level = await connection.fetchval(
                    """
                    SELECT level
                    FROM realm_research
                    WHERE realm_id = $1
                      AND research_type = 'provincial_administration'
                    """,
                    realm_id
                ) or 0

                if level < 1:
                    error = (
                        "Necesitas Administración provincial "
                        "para fundar una provincia."
                    )

                if not error:
                    existing = await connection.fetchval(
                        """
                        SELECT EXISTS(
                            SELECT 1
                            FROM provinces
                            WHERE realm_id = $1
                        )
                        """,
                        realm_id
                    )

                    if existing:
                        error = "Tu reino ya tiene una provincia."

                if not error:
                    # Serializa las fundaciones sobre el mismo territorio.
                    await connection.execute(
                        """
                        SELECT pg_advisory_xact_lock($1, $2)
                        """,
                        continent,
                        territory
                    )

                    occupied = await connection.fetchval(
                        """
                        SELECT EXISTS(
                            SELECT 1
                            FROM realms
                            WHERE continent = $1
                              AND region = $2
                        )
                        """,
                        continent,
                        territory
                    )

                    province_occupied = await connection.fetchval(
                        """
                        SELECT EXISTS(
                            SELECT 1
                            FROM provinces
                            WHERE continent = $1
                              AND region = $2
                        )
                        """,
                        continent,
                        territory
                    )

                    if occupied or province_occupied:
                        error = (
                            "Ese territorio ya no está vacío. "
                            "Elige otro."
                        )

                if not error:
                    province_name = (
                        f"Provincia {continent}-{territory}"
                    )

                    await connection.execute(
                        """
                        INSERT INTO provinces (
                            realm_id,
                            name,
                            province_number,
                            continent,
                            region
                        )
                        VALUES ($1, $2, 1, $3, $4)
                        """,
                        realm_id,
                        province_name,
                        continent,
                        territory
                    )

                    await connection.execute(
                        """
                        INSERT INTO realm_event_log (
                            realm_id,
                            event_type,
                            description
                        )
                        VALUES ($1, 'province_founded', $2)
                        """,
                        realm_id,
                        (
                            f"Se fundó {province_name} "
                            f"en el territorio {continent}:{territory}."
                        )
                    )

    if error:
        await callback.answer(
            error,
            show_alert=True
        )

        if "ya no está vacío" in error:
            await province_menu_handler(callback)

        return

    await callback.answer(
        "¡Provincia fundada!",
        show_alert=True
    )

    await render_territories(callback)

from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import get_pool
from bot.keyboards.main_menu import create_realm_keyboard

from bot.services.world import (
    assign_world_position,
    normalize_coordinates,
    MAX_CONTINENTS,
    TERRITORIES_PER_CONTINENT,
    POSITIONS_PER_TERRITORY,
)


router = Router()


def number(value):
    return f"{int(value or 0):,}".replace(",", ".")


async def get_player_realm(connection, user_id):
    realm = await connection.fetchrow(
        """
        SELECT
            id,
            owner_id,
            name,
            continent,
            region,
            position
        FROM realms
        WHERE owner_id = $1
        """,
        user_id,
    )

    if not realm:
        return None

    realm = dict(realm)

    coordinates = (
        realm["continent"],
        realm["region"],
        realm["position"],
    )

    if any(value is None for value in coordinates):
        coordinates = await assign_world_position(
            connection,
            realm["id"],
        )

        realm["continent"] = coordinates[0]
        realm["region"] = coordinates[1]
        realm["position"] = coordinates[2]

    return realm


async def get_last_continent(connection):
    value = await connection.fetchval(
        """
        SELECT COALESCE(MAX(continent), 1)
        FROM realms
        """
    )

    return max(1, min(int(value or 1), MAX_CONTINENTS))


def continent_keyboard(continent, last_continent, counts):
    builder = InlineKeyboardBuilder()

    for territory in range(
        1,
        TERRITORIES_PER_CONTINENT + 1,
    ):
        occupied = counts.get(territory, 0)

        builder.button(
            text=(
                f"Territorio {territory} "
                f"· {occupied}/{POSITIONS_PER_TERRITORY}"
            ),
            callback_data=(
                f"world:t:{continent}:{territory}"
            ),
        )

    builder.adjust(1)

    navigation = []

    if continent > 1:
        navigation.append(
            (
                "◀ Continente anterior",
                f"world:c:{continent - 1}",
            )
        )

    if continent < last_continent:
        navigation.append(
            (
                "Continente siguiente ▶",
                f"world:c:{continent + 1}",
            )
        )

    for label, data in navigation:
        builder.button(
            text=label,
            callback_data=data,
        )

    if navigation:
        builder.adjust(
            1,
            *([len(navigation)]),
        )

    builder.button(
        text="🏰 Ir a mi reino",
        callback_data="world",
    )

    builder.button(
        text="↩ Menú principal",
        callback_data="main_menu",
    )

    builder.adjust(1)

    return builder.as_markup()


def position_keyboard(
    continent,
    territory,
    occupied_positions,
):
    builder = InlineKeyboardBuilder()

    for position in range(
        1,
        POSITIONS_PER_TERRITORY + 1,
    ):
        if position in occupied_positions:
            label = f"{position:02d} 🏰"
        else:
            label = f"{position:02d} ·"

        builder.button(
            text=label,
            callback_data=(
                f"world:s:{continent}:{territory}:{position}"
            ),
        )

    builder.adjust(4)

    builder.button(
        text="◀ Volver a territorios",
        callback_data=f"world:c:{continent}",
    )

    builder.button(
        text="🏰 Mi reino",
        callback_data="world",
    )

    builder.button(
        text="⌂ Menú principal",
        callback_data="main_menu",
    )

    builder.adjust(4, 4, 4, 4, 4, 1, 1, 1)

    return builder.as_markup()


def realm_detail_keyboard(
    realm_id,
    owner_id,
    current_user_id,
    continent,
    territory,
):
    builder = InlineKeyboardBuilder()

    if owner_id != current_user_id:
        builder.button(
            text="⚔ Preparar campaña",
            callback_data=f"battle:target:{realm_id}",
        )

    builder.button(
        text="◀ Volver al territorio",
        callback_data=(
            f"world:t:{continent}:{territory}"
        ),
    )

    builder.button(
        text="⌂ Menú principal",
        callback_data="main_menu",
    )

    builder.adjust(1)

    return builder.as_markup()


async def render_continent(
    callback,
    connection,
    realm,
    continent,
):
    last_continent = await get_last_continent(
        connection
    )

    if not 1 <= continent <= last_continent:
        await callback.answer(
            "Ese continente todavía no está disponible.",
            show_alert=True,
        )
        return

    rows = await connection.fetch(
        """
        SELECT
            region,
            COUNT(*) AS occupied
        FROM realms
        WHERE continent = $1
        GROUP BY region
        """,
        continent,
    )

    counts = {
        int(row["region"]): int(row["occupied"])
        for row in rows
    }

    total = sum(counts.values())

    lines = [
        "🗺️ <b>MAPA DEL MUNDO</b>",
        "",
        f"🌍 <b>CONTINENTE {continent}</b>",
        "",
        "Selecciona un territorio para explorar sus "
        "20 posiciones.",
        "",
    ]

    for territory in range(
        1,
        TERRITORIES_PER_CONTINENT + 1,
    ):
        occupied = counts.get(territory, 0)
        free = POSITIONS_PER_TERRITORY - occupied

        lines.append(
            f"🏞 Territorio {territory}: "
            f"<b>{occupied}/{POSITIONS_PER_TERRITORY}</b> ocupadas"
        )

        lines.append(
            f"   Posiciones libres: {free}"
        )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        f"🏰 Reinos en este continente: <b>{total}/60</b>",
        "",
        "📍 Tu reino: "
        f"<code>{realm['continent']}:"
        f"{realm['region']}:"
        f"{realm['position']}</code>",
        "",
        "🏰 = Posición ocupada",
        "· = Posición libre",
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=continent_keyboard(
            continent,
            last_continent,
            counts,
        ),
        parse_mode="HTML",
    )


async def render_territory(
    callback,
    connection,
    realm,
    continent,
    territory,
):
    last_continent = await get_last_continent(
        connection
    )

    if not 1 <= continent <= last_continent:
        await callback.answer(
            "Continente no disponible.",
            show_alert=True,
        )
        return

    if not 1 <= territory <= TERRITORIES_PER_CONTINENT:
        await callback.answer(
            "Territorio no válido.",
            show_alert=True,
        )
        return

    realms = await connection.fetch(
        """
        SELECT
            r.position,
            r.id,
            r.name,
            r.level,
            r.power,
            p.first_name,
            p.username
        FROM realms r
        LEFT JOIN players p
          ON p.id = r.owner_id
        WHERE r.continent = $1
          AND r.region = $2
        ORDER BY r.position
        """,
        continent,
        territory,
    )

    occupied = {
        int(row["position"]): row
        for row in realms
    }

    lines = [
        "🗺️ <b>EXPLORACIÓN TERRITORIAL</b>",
        "",
        f"🌍 Continente: <b>{continent}</b>",
        f"🏞 Territorio: <b>{territory}</b>",
        "",
        "<b>📍 REINOS Y JUGADORES</b>",
        "",
    ]

    for position in range(
        1,
        POSITIONS_PER_TERRITORY + 1,
    ):
        target = occupied.get(position)

        if target:
            realm_name = escape(
                target["name"] or "Reino sin nombre"
            )

            player_name = escape(
                target["first_name"]
                or target["username"]
                or "Jugador"
            )

            lines.append(
                f"<b>{position:02d}</b> — 🏰 "
                f"<b>{realm_name}</b>"
            )

            lines.append(
                f"     👑 {player_name}"
            )

        else:
            lines.append(
                f"<b>{position:02d}</b> — 🟢 "
                "<i>Posición libre</i>"
            )

        lines.append("")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        f"🏰 Reinos establecidos: "
        f"<b>{len(occupied)}/{POSITIONS_PER_TERRITORY}</b>",
        f"📍 Posiciones libres: "
        f"<b>{POSITIONS_PER_TERRITORY - len(occupied)}</b>",
        "",
        "Selecciona un número para consultar "
        "los detalles de esa posición.",
        "",
        "📍 Tu reino está aquí: "
        f"<code>{realm['continent']}:"
        f"{realm['region']}:"
        f"{realm['position']}</code>",
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=position_keyboard(
            continent,
            territory,
            occupied,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "world")
async def open_world(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await get_player_realm(
            connection,
            callback.from_user.id,
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True,
            )

            await callback.message.edit_text(
                "🏰 <b>Aún no posees un reino.</b>\n\n"
                "Funda tu dominio para poder explorar "
                "el mundo de Kingdram.",
                reply_markup=create_realm_keyboard(),
                parse_mode="HTML",
            )
            return

        await callback.answer()

        await render_continent(
            callback,
            connection,
            realm,
            realm["continent"],
        )


@router.callback_query(F.data.startswith("world:c:"))
async def change_continent(callback: CallbackQuery):
    try:
        continent = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer(
            "Continente no válido.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await get_player_realm(
            connection,
            callback.from_user.id,
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True,
            )
            return

        await callback.answer()

        await render_continent(
            callback,
            connection,
            realm,
            continent,
        )


@router.callback_query(F.data.startswith("world:t:"))
async def open_world_territory(
    callback: CallbackQuery,
):
    try:
        _, _, continent, territory = (
            callback.data.split(":")
        )

        continent = int(continent)
        territory = int(territory)

    except (ValueError, IndexError):
        await callback.answer(
            "Territorio no válido.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await get_player_realm(
            connection,
            callback.from_user.id,
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True,
            )
            return

        await callback.answer()

        await render_territory(
            callback,
            connection,
            realm,
            continent,
            territory,
        )


@router.callback_query(F.data.startswith("world:s:"))
async def inspect_world_position(
    callback: CallbackQuery,
):
    try:
        (
            _,
            _,
            continent,
            territory,
            position,
        ) = callback.data.split(":")

        coordinates = normalize_coordinates((
            int(continent),
            int(territory),
            int(position),
        ))

    except (ValueError, IndexError):
        await callback.answer(
            "Posición no válida.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await get_player_realm(
            connection,
            callback.from_user.id,
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True,
            )
            return

        target = await connection.fetchrow(
            """
            SELECT
                r.id,
                r.owner_id,
                r.name,
                r.level,
                r.power,
                r.population,
                p.first_name,
                p.username
            FROM realms r
            LEFT JOIN players p
              ON p.id = r.owner_id
            WHERE r.continent = $1
              AND r.region = $2
              AND r.position = $3
            """,
            coordinates[0],
            coordinates[1],
            coordinates[2],
        )

        if not target:
            await callback.answer(
                "Esta posición está libre.",
                show_alert=True,
            )
            return

        await callback.answer()

        owner_name = (
            target["first_name"]
            or target["username"]
            or "Jugador"
        )

        lines = [
            "🏰 <b>INFORMACIÓN DEL REINO</b>",
            "",
            f"👑 Reino: <b>{escape(target['name'])}</b>",
            f"🛡 Señor: <b>{escape(owner_name)}</b>",
            "",
            f"🗺 Coordenadas: "
            f"<code>{coordinates[0]}:"
            f"{coordinates[1]}:"
            f"{coordinates[2]}</code>",
            "",
            f"⭐ Nivel: <b>{number(target['level'])}</b>",
            f"👥 Población: "
            f"<b>{number(target['population'])}</b>",
            f"⚔ Poder: <b>{number(target['power'])}</b>",
        ]

        if target["owner_id"] == callback.from_user.id:
            lines.extend([
                "",
                "<i>Este es tu propio reino.</i>",
            ])

        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=realm_detail_keyboard(
                target["id"],
                target["owner_id"],
                callback.from_user.id,
                coordinates[0],
                coordinates[1],
            ),
            parse_mode="HTML",
        )

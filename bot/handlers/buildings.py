
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.connection import get_pool
from bot.services.construction import (
    BUILDINGS,
    get_upgrade_cost,
    get_upgrade_time
)
from bot.keyboards.buildings import (
    buildings_keyboard,
    building_detail_keyboard
)

router = Router()


RESOURCE_LABELS = {
    "wood": "Madera",
    "stone": "Piedra",
    "gold": "Oro",
    "food": "Alimentos"
}


def format_cost(cost):
    return "\n".join(
        f"{RESOURCE_LABELS[resource]}: {amount:,}"
        for resource, amount in cost.items()
    )


def format_remaining(value):
    seconds = max(
        0,
        int((value - datetime.now(timezone.utc)).total_seconds())
    )

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours} h {minutes} min"

    if minutes:
        return f"{minutes} min {seconds} s"

    return f"{seconds} s"


async def render_buildings(callback):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            "SELECT id FROM realms WHERE owner_id = $1",
            callback.from_user.id
        )

        if not realm:
            await callback.message.edit_text(
                "Primero debes fundar tu reino."
            )
            return

        buildings = await connection.fetch(
            """
            SELECT building_type, level
            FROM buildings
            WHERE realm_id = $1
            """,
            realm["id"]
        )

        pending = await connection.fetchrow(
            """
            SELECT building_type, target_level, finishes_at
            FROM construction_queue
            WHERE realm_id = $1
            ORDER BY started_at
            LIMIT 1
            """,
            realm["id"]
        )

    levels = {
        item["building_type"]: item["level"]
        for item in buildings
    }

    lines = [
        "<b>INFRAESTRUCTURA DEL REINO</b>",
        "",
        "Administra tus edificios y desarrolla "
        "la economía de tus dominios.",
        ""
    ]

    for building_type, info in BUILDINGS.items():
        level = levels.get(building_type, 0)

        lines.append(
            f"{info['icon']} <b>{info['name']}</b>"
        )

        if level:
            lines.append(f"Nivel actual: {level}")
        else:
            lines.append("Todavía no construido.")

        if pending and pending["building_type"] == building_type:
            lines.append(
                f"Construyendo nivel {pending['target_level']} "
                f"({format_remaining(pending['finishes_at'])})"
            )

        lines.append("")

    if pending:
        active_info = BUILDINGS.get(
            pending["building_type"],
            {}
        )

        lines.extend([
            "<b>COLA DE CONSTRUCCIÓN</b>",
            f"Edificio: {active_info.get('name', pending['building_type'])}",
            f"Nivel objetivo: {pending['target_level']}",
            f"Tiempo restante: {format_remaining(pending['finishes_at'])}",
        ])
    else:
        lines.append(
            "<i>No tienes construcciones pendientes.</i>"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=buildings_keyboard(
            levels,
            pending["building_type"] if pending else None
        )
    )


@router.callback_query(F.data == "buildings")
async def buildings_handler(callback: CallbackQuery):
    await callback.answer()
    await render_buildings(callback)


@router.callback_query(F.data.startswith("building:"))
async def building_detail_handler(callback: CallbackQuery):
    building_type = callback.data.split(":", 1)[1]
    info = BUILDINGS.get(building_type)

    if not info:
        await callback.answer(
            "Edificio desconocido.",
            show_alert=True
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar un reino.",
                show_alert=True
            )
            return

        building = await connection.fetchrow(
            """
            SELECT level
            FROM buildings
            WHERE realm_id = $1
              AND building_type = $2
            """,
            realm["id"],
            building_type
        )

        pending = await connection.fetchrow(
            """
            SELECT building_type, target_level, finishes_at
            FROM construction_queue
            WHERE realm_id = $1
            ORDER BY started_at
            LIMIT 1
            """,
            realm["id"]
        )

    level = building["level"] if building else 0
    next_level = level + 1

    cost = get_upgrade_cost(
        building_type,
        next_level
    )

    duration = get_upgrade_time(
        building_type,
        next_level
    )

    action = "Construcción" if level == 0 else "Mejora"

    lines = [
        f"{info['icon']} <b>{info['name'].upper()}</b>",
        "",
        info["description"],
        "",
        f"Nivel actual: {level}",
        f"Nivel objetivo: {next_level}",
        "",
        f"<b>Coste de {action.lower()}</b>",
        format_cost(cost),
        "",
        f"Tiempo: {duration // 60} min {duration % 60} s"
    ]

    if pending:
        pending_info = BUILDINGS.get(
            pending["building_type"],
            {}
        )

        lines.extend([
            "",
            "<b>COLA DE CONSTRUCCIÓN</b>",
            f"Edificio: {pending_info.get('name', pending['building_type'])}",
            f"Nivel objetivo: {pending['target_level']}",
            f"Tiempo restante: {format_remaining(pending['finishes_at'])}"
        ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=building_detail_keyboard(
            building_type,
            level,
            bool(pending)
        )
    )


@router.callback_query(F.data.startswith("upgrade:"))
async def upgrade_building_handler(callback: CallbackQuery):
    building_type = callback.data.split(":", 1)[1]

    if building_type not in BUILDINGS:
        await callback.answer(
            "Edificio desconocido.",
            show_alert=True
        )
        return

    pool = await get_pool()
    error_message = None
    target_level = None
    duration = None

    async with pool.acquire() as connection:
        async with connection.transaction():
            realm = await connection.fetchrow(
                """
                SELECT id
                FROM realms
                WHERE owner_id = $1
                FOR UPDATE
                """,
                callback.from_user.id
            )

            if not realm:
                error_message = "Primero debes fundar un reino."
            else:
                realm_id = realm["id"]

                pending = await connection.fetchrow(
                    """
                    SELECT building_type
                    FROM construction_queue
                    WHERE realm_id = $1
                    LIMIT 1
                    FOR UPDATE
                    """,
                    realm_id
                )

                if pending:
                    pending_name = BUILDINGS.get(
                        pending["building_type"],
                        {}
                    ).get("name", pending["building_type"])

                    error_message = (
                        f"Ya tienes una construcción activa: "
                        f"{pending_name}. "
                        "Espera a que termine antes de iniciar otra."
                    )

                else:
                    building = await connection.fetchrow(
                        """
                        SELECT level
                        FROM buildings
                        WHERE realm_id = $1
                          AND building_type = $2
                        FOR UPDATE
                        """,
                        realm_id,
                        building_type
                    )

                    current_level = (
                        building["level"] if building else 0
                    )

                    target_level = current_level + 1

                    cost = get_upgrade_cost(
                        building_type,
                        target_level
                    )

                    duration = get_upgrade_time(
                        building_type,
                        target_level
                    )

                    resources = await connection.fetchrow(
                        """
                        SELECT wood, stone, gold, food
                        FROM resources
                        WHERE realm_id = $1
                        FOR UPDATE
                        """,
                        realm_id
                    )

                    if not resources:
                        error_message = (
                            "No se encontraron los recursos del reino."
                        )

                    else:
                        insufficient = [
                            RESOURCE_LABELS[resource]
                            for resource, amount in cost.items()
                            if resources[resource] < amount
                        ]

                        if insufficient:
                            error_message = (
                                "Recursos insuficientes: "
                                + ", ".join(insufficient)
                            )

                        else:
                            await connection.execute(
                                """
                                UPDATE resources
                                SET wood = wood - $1,
                                    stone = stone - $2,
                                    gold = gold - $3,
                                    food = food - $4
                                WHERE realm_id = $5
                                """,
                                cost.get("wood", 0),
                                cost.get("stone", 0),
                                cost.get("gold", 0),
                                cost.get("food", 0),
                                realm_id
                            )

                            await connection.execute(
                                """
                                INSERT INTO construction_queue (
                                    realm_id,
                                    building_type,
                                    target_level,
                                    finishes_at
                                )
                                VALUES (
                                    $1,
                                    $2,
                                    $3,
                                    NOW() + $4 * INTERVAL '1 second'
                                )
                                """,
                                realm_id,
                                building_type,
                                target_level,
                                duration
                            )

    if error_message:
        await callback.answer(
            error_message,
            show_alert=True
        )
        return

    await callback.answer("Construcción iniciada.")

    await render_buildings(callback)

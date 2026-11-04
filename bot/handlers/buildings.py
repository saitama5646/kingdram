import math
from datetime import datetime, timezone
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.connection import get_pool
from bot.services.construction import (
    BUILDINGS,
    get_upgrade_cost,
    get_upgrade_time,
)
from bot.keyboards.buildings import (
    buildings_keyboard,
    building_detail_keyboard,
)
from bot.keyboards.main_menu import back_to_menu_keyboard


router = Router()


RESOURCE_LABELS = {
    "wood": "🪵 Madera",
    "stone": "🪨 Piedra",
    "gold": "🪙 Oro",
    "food": "🌾 Alimentos",
}


def format_cost(cost):
    """Devuelve el coste con el emoji correspondiente a cada recurso."""
    lines = []

    for resource, amount in cost.items():
        label = RESOURCE_LABELS.get(
            resource,
            resource.capitalize(),
        )
        lines.append(f"{label}: <b>{amount:,}</b>")

    return "\n".join(lines)


def format_duration(seconds):
    """Convierte segundos en un texto legible."""
    seconds = max(0, int(seconds))

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []

    if hours:
        parts.append(f"{hours} h")

    if minutes:
        parts.append(f"{minutes} min")

    if seconds or not parts:
        parts.append(f"{seconds} s")

    return " ".join(parts)


def format_remaining(finishes_at):
    """Calcula cuánto falta para terminar una construcción."""
    if finishes_at.tzinfo is None:
        finishes_at = finishes_at.replace(tzinfo=timezone.utc)

    remaining = math.ceil(
        (finishes_at - datetime.now(timezone.utc)).total_seconds()
    )

    return format_duration(remaining)


async def get_realm_building_data(user_id):
    """Obtiene el reino, sus edificios y la construcción pendiente."""
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            user_id,
        )

        if not realm:
            return None, [], None

        buildings = await connection.fetch(
            """
            SELECT building_type, level
            FROM buildings
            WHERE realm_id = $1
            """,
            realm["id"],
        )

        pending = await connection.fetchrow(
            """
            SELECT building_type, target_level, finishes_at
            FROM construction_queue
            WHERE realm_id = $1
            ORDER BY finishes_at
            LIMIT 1
            """,
            realm["id"],
        )

    return realm, buildings, pending


async def render_buildings(callback):
    realm, buildings, pending = await get_realm_building_data(
        callback.from_user.id
    )

    if not realm:
        await callback.message.edit_text(
            "🏰 <b>Aún no tienes un reino.</b>\n\n"
            "Funda tu dominio para comenzar a construir.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    levels = {
        item["building_type"]: item["level"]
        for item in buildings
    }

    lines = [
        "🏗 <b>INFRAESTRUCTURA DEL REINO</b>",
        "",
        f"🏰 Dominio: <b>{escape(realm['name'])}</b>",
        "",
        "Selecciona un edificio para consultar sus "
        "características, construirlo o mejorarlo.",
    ]

    if pending:
        pending_info = BUILDINGS.get(
            pending["building_type"],
            {},
        )

        pending_name = escape(
            pending_info.get(
                "name",
                pending["building_type"],
            )
        )

        pending_icon = pending_info.get("icon", "🏗")

        lines.extend([
            "",
            "⏳ <b>CONSTRUCCIÓN EN CURSO</b>",
            f"{pending_icon} {pending_name}",
            f"Nivel objetivo: <b>{pending['target_level']}</b>",
            (
                "Tiempo restante: "
                f"<b>{format_remaining(pending['finishes_at'])}</b>"
            ),
        ])
    else:
        lines.extend([
            "",
            "✅ No tienes construcciones pendientes.",
        ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=buildings_keyboard(
            levels=levels,
            pending_type=(
                pending["building_type"] if pending else None
            ),
        ),
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
            show_alert=True,
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
            callback.from_user.id,
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True,
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
            building_type,
        )

        pending = await connection.fetchrow(
            """
            SELECT building_type, target_level, finishes_at
            FROM construction_queue
            WHERE realm_id = $1
            ORDER BY finishes_at
            LIMIT 1
            """,
            realm["id"],
        )

    level = building["level"] if building else 0
    next_level = level + 1

    cost = get_upgrade_cost(
        building_type,
        next_level,
    )

    duration = get_upgrade_time(
        building_type,
        next_level,
    )

    action = "construcción" if level == 0 else "mejora"

    lines = [
        f"{info['icon']} <b>{escape(info['name'].upper())}</b>",
        "",
        escape(info["description"]),
        "",
        f"Nivel actual: <b>{level}</b>",
        f"Nivel objetivo: <b>{next_level}</b>",
        "",
        f"<b>Coste de {action}</b>",
        format_cost(cost),
        "",
        f"⏱ Tiempo: <b>{format_duration(duration)}</b>",
    ]

    if pending:
        pending_info = BUILDINGS.get(
            pending["building_type"],
            {},
        )

        pending_name = escape(
            pending_info.get(
                "name",
                pending["building_type"],
            )
        )

        pending_icon = pending_info.get("icon", "🏗")

        lines.extend([
            "",
            "⏳ <b>COLA DE CONSTRUCCIÓN</b>",
            f"{pending_icon} Edificio: <b>{pending_name}</b>",
            f"Nivel objetivo: <b>{pending['target_level']}</b>",
            (
                "Tiempo restante: "
                f"<b>{format_remaining(pending['finishes_at'])}</b>"
            ),
        ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=building_detail_keyboard(
            building_type=building_type,
            level=level,
            pending=bool(pending),
        ),
    )


@router.callback_query(F.data.startswith("upgrade:"))
async def upgrade_building_handler(callback: CallbackQuery):
    building_type = callback.data.split(":", 1)[1]

    if building_type not in BUILDINGS:
        await callback.answer(
            "Edificio desconocido.",
            show_alert=True,
        )
        return

    pool = await get_pool()
    error_message = None

    async with pool.acquire() as connection:
        async with connection.transaction():
            realm = await connection.fetchrow(
                """
                SELECT id
                FROM realms
                WHERE owner_id = $1
                FOR UPDATE
                """,
                callback.from_user.id,
            )

            if not realm:
                error_message = "Primero debes fundar tu reino."

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
                    realm_id,
                )

                if pending:
                    pending_name = BUILDINGS.get(
                        pending["building_type"],
                        {},
                    ).get(
                        "name",
                        pending["building_type"],
                    )

                    error_message = (
                        f"Ya tienes una construcción activa: "
                        f"{pending_name}. Espera a que termine."
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
                        building_type,
                    )

                    current_level = (
                        building["level"] if building else 0
                    )

                    target_level = current_level + 1

                    cost = get_upgrade_cost(
                        building_type,
                        target_level,
                    )

                    duration = get_upgrade_time(
                        building_type,
                        target_level,
                    )

                    resources = await connection.fetchrow(
                        """
                        SELECT wood, stone, gold, food
                        FROM resources
                        WHERE realm_id = $1
                        FOR UPDATE
                        """,
                        realm_id,
                    )

                    if not resources:
                        error_message = (
                            "No se encontraron los recursos del reino."
                        )

                    else:
                        insufficient = [
                            RESOURCE_LABELS.get(
                                resource,
                                resource.capitalize(),
                            )
                            for resource, amount in cost.items()
                            if resources[resource] < amount
                        ]

                        if insufficient:
                            error_message = (
                                "Recursos insuficientes:\n"
                                + "\n".join(insufficient)
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
                                realm_id,
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
                                duration,
                            )

    if error_message:
        await callback.answer(
            error_message,
            show_alert=True,
        )
        return

    await callback.answer("Construcción iniciada.")
    await render_buildings(callback)

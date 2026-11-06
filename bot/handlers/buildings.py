
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
from bot.services.research import get_research_effects
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
    return "\n".join(
        f"{RESOURCE_LABELS.get(resource, resource.capitalize())}: "
        f"<b>{amount:,}</b>"
        for resource, amount in cost.items()
    )


def format_duration(seconds):
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
    if finishes_at.tzinfo is None:
        finishes_at = finishes_at.replace(tzinfo=timezone.utc)

    remaining = math.ceil(
        (
            finishes_at - datetime.now(timezone.utc)
        ).total_seconds()
    )

    return format_duration(remaining)


async def get_realm_research_effects(connection, realm_id):
    rows = await connection.fetch(
        """
        SELECT research_type, level
        FROM realm_research
        WHERE realm_id = $1
        """,
        realm_id,
    )

    levels = {
        row["research_type"]: row["level"]
        for row in rows
    }

    return get_research_effects(levels)


def apply_construction_speed(base_duration, effects):
    bonus = max(
        0,
        float(effects.get("construction_speed", 0)),
    )

    return max(
        1,
        math.ceil(base_duration / (1 + bonus)),
    )


async def get_realm_building_data(user_id):
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
            return None, None, [], []

        buildings = await connection.fetch(
            """
            SELECT
                building_type,
                level,
                damaged_levels,
                rebuild_at
            FROM buildings
            WHERE realm_id = $1
            """,
            realm["id"],
        )

        queue = await connection.fetch(
            """
            SELECT
                building_type,
                target_level,
                queue_position,
                finishes_at
            FROM construction_queue
            WHERE realm_id = $1
            ORDER BY queue_position, finishes_at, id
            """,
            realm["id"],
        )

        resources = await connection.fetchrow(
            """
            SELECT wood, stone, gold, food
            FROM resources
            WHERE realm_id = $1
            """,
            realm["id"],
        )

    return realm, resources, buildings, queue


async def render_buildings(callback):
    realm, resources, buildings, queue = await get_realm_building_data(
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
        "━━━━━━━━━━━━━━━━━━",
        "📦 <b>RECURSOS DISPONIBLES</b>",
        "",
        *[
            (
                f"{icon} <b>{name}:</b> "
                f"{(resources[resource] if resources else 0):,}"
            )
            for resource, icon, name in (
                ("wood", "🪵", "Madera"),
                ("stone", "🪨", "Piedra"),
                ("gold", "🪙", "Oro"),
                ("food", "🌾", "Alimentos"),
            )
        ],
        "",
        "━━━━━━━━━━━━━━━━━━",
        "Selecciona un edificio para consultar "
        "sus características y mejorarlo.",
    ]

    damaged_buildings = [
        item for item in buildings
        if int(item.get("damaged_levels", 0) or 0) > 0
    ]

    if damaged_buildings:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            "🛠 <b>EDIFICIOS DAÑADOS</b>",
            "",
            "<i>Los niveles dañados no producen ni aportan "
            "capacidad hasta que termine su reconstrucción.</i>",
        ])

        for item in damaged_buildings:
            info = BUILDINGS.get(
                item["building_type"],
                {},
            )

            name = info.get(
                "name",
                item["building_type"],
            )

            icon = info.get("icon", "🏗")
            original_level = int(item["level"])
            damaged = int(item.get("damaged_levels", 0) or 0)
            effective_level = max(0, original_level - damaged)
            rebuild_at = item.get("rebuild_at")

            remaining = (
                format_remaining(rebuild_at)
                if rebuild_at
                else "Pendiente de programación"
            )

            lines.extend([
                f"{icon} <b>{escape(name)}</b>",
                f"   Nivel original: {original_level}",
                f"   Nivel operativo: <b>{effective_level}</b>",
                f"   Niveles dañados: <b>{damaged}</b>",
                f"   Reconstrucción: <b>{remaining}</b>",
            ])

    if queue:
        lines.extend([
            "",
            "⏳ <b>COLA DE CONSTRUCCIÓN</b>",
        ])

        for item in queue:
            info = BUILDINGS.get(
                item["building_type"],
                {},
            )

            name = info.get(
                "name",
                item["building_type"],
            )

            icon = info.get("icon", "🏗")

            lines.append(
                f"{item['queue_position']}. "
                f"{icon} <b>{escape(name)}</b> "
                f"→ nivel {item['target_level']}"
            )

            if item["queue_position"] == 1:
                lines.append(
                    "   Tiempo restante: "
                    f"<b>{format_remaining(item['finishes_at'])}</b>"
                )
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
                queue[0]["building_type"] if queue else None
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

        realm_id = realm["id"]

        building = await connection.fetchrow(
            """
            SELECT
                level,
                damaged_levels,
                rebuild_at
            FROM buildings
            WHERE realm_id = $1
              AND building_type = $2
            """,
            realm_id,
            building_type,
        )

        queued = await connection.fetch(
            """
            SELECT target_level, queue_position, finishes_at
            FROM construction_queue
            WHERE realm_id = $1
              AND building_type = $2
            ORDER BY queue_position, finishes_at, id
            """,
            realm_id,
            building_type,
        )

        full_queue = await connection.fetch(
            """
            SELECT
                building_type,
                target_level,
                queue_position,
                finishes_at
            FROM construction_queue
            WHERE realm_id = $1
            ORDER BY queue_position, finishes_at, id
            """,
            realm_id,
        )

        effects = await get_realm_research_effects(
            connection,
            realm_id,
        )

        resources = await connection.fetchrow(
            """
            SELECT wood, stone, gold, food
            FROM resources
            WHERE realm_id = $1
            """,
            realm_id,
        )

    level = building["level"] if building else 0
    damaged_levels = (
        int(building["damaged_levels"] or 0)
        if building else 0
    )
    rebuild_at = (
        building["rebuild_at"]
        if building else None
    )
    effective_level = max(0, level - damaged_levels)

    next_level = (
        max(item["target_level"] for item in queued) + 1
        if queued
        else level + 1
    )

    cost = get_upgrade_cost(
        building_type,
        next_level,
    )

    base_duration = get_upgrade_time(
        building_type,
        next_level,
    )

    duration = apply_construction_speed(
        base_duration,
        effects,
    )

    construction_bonus = (
        float(effects.get("construction_speed", 0)) * 100
    )

    action = (
        "construcción"
        if level == 0 and not queued
        else "mejora"
    )

    resource_emojis = {
        "wood": "🪵",
        "stone": "🪨",
        "gold": "🪙",
        "food": "🌾",
    }

    resource_names = {
        "wood": "Madera",
        "stone": "Piedra",
        "gold": "Oro",
        "food": "Alimentos",
    }

    available_lines = []
    cost_lines = []
    sufficient = resources is not None

    for resource in ("wood", "stone", "gold", "food"):
        available = resources[resource] if resources else 0
        required = cost.get(resource, 0)

        available_lines.append(
            f"{resource_emojis[resource]} "
            f"{resource_names[resource]}: "
            f"<b>{available:,}</b>"
        )

        if required:
            cost_lines.append(
                f"{resource_emojis[resource]} "
                f"{resource_names[resource]}: "
                f"<b>{available:,} / {required:,}</b>"
            )

            if available < required:
                sufficient = False

    lines = [
        f"{info['icon']} <b>{escape(info['name'].upper())}</b>",
        "",
        escape(info["description"]),
        "",
        f"Nivel actual: <b>{level}</b>",
        f"Nivel operativo: <b>{effective_level}</b>",
        f"Nivel objetivo: <b>{next_level}</b>",
        *(
            [
                "",
                "📦 <b>CAPACIDAD ADICIONAL</b>",
                "Por este nivel: <b>+10.000</b> madera y piedra.",
            ]
            if building_type == "warehouse"
            else [
                "",
                "📦 <b>CAPACIDAD ADICIONAL</b>",
                "Por este nivel: <b>+10.000</b> de oro.",
            ]
            if building_type == "treasury"
            else [
                "",
                "📦 <b>CAPACIDAD ADICIONAL</b>",
                "Por este nivel: <b>+15.000</b> alimentos.",
            ]
            if building_type == "granary"
            else []
        ),
        "",
        "💰 <b>RECURSOS DISPONIBLES</b>",
        *available_lines,
        "",
        f"<b>Coste de {action}</b>",
        *cost_lines,
        "",
        (
            "✅ <b>Recursos suficientes</b>"
            if sufficient
            else "❌ <b>Recursos insuficientes</b>"
        ),
        "",
        f"⏱ Tiempo base: <b>{format_duration(base_duration)}</b>",
        (
            "🏛️ Bonificación de Arquitectura: "
            f"<b>{construction_bonus:.0f}%</b>"
        ),
        f"⏱ Tiempo efectivo: <b>{format_duration(duration)}</b>",
    ]

    if damaged_levels > 0:
        remaining = (
            format_remaining(rebuild_at)
            if rebuild_at
            else "Pendiente de programación"
        )

        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            "🛠 <b>ESTADO DE RECONSTRUCCIÓN</b>",
            "",
            f"⚠️ Niveles dañados: <b>{damaged_levels}</b>",
            f"🏗 Niveles operativos: <b>{effective_level}</b>",
            f"⏳ Tiempo restante: <b>{remaining}</b>",
            "",
            "<i>Los niveles dañados no aportan producción, "
            "capacidad ni otros efectos mientras se reconstruyen. "
            "Al finalizar el plazo, el edificio recuperará "
            "automáticamente sus niveles.</i>",
        ])

    if queued:
        lines.extend([
            "",
            "⏳ <b>EDIFICIO EN COLA</b>",
        ])

        for item in queued:
            lines.append(
                f"Posición {item['queue_position']}: "
                f"nivel {item['target_level']}"
            )

    if full_queue:
        lines.extend([
            "",
            "🏗 <b>COLA GENERAL</b>",
        ])

        for item in full_queue:
            pending_info = BUILDINGS.get(
                item["building_type"],
                {},
            )

            pending_name = pending_info.get(
                "name",
                item["building_type"],
            )

            lines.append(
                f"{item['queue_position']}. "
                f"{escape(pending_name)} "
                f"→ nivel {item['target_level']}"
            )

        lines.append(
            "Tiempo restante de la primera tarea: "
            f"<b>{format_remaining(full_queue[0]['finishes_at'])}</b>"
        )

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=building_detail_keyboard(
            building_type=building_type,
            level=level,
            pending=False,
            can_start=sufficient,
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
    target_level = None

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

                queued_level = await connection.fetchval(
                    """
                    SELECT MAX(target_level)
                    FROM construction_queue
                    WHERE realm_id = $1
                      AND building_type = $2
                    """,
                    realm_id,
                    building_type,
                )

                target_level = (
                    max(current_level, queued_level) + 1
                    if queued_level is not None
                    else current_level + 1
                )

                cost = get_upgrade_cost(
                    building_type,
                    target_level,
                )

                base_duration = get_upgrade_time(
                    building_type,
                    target_level,
                )

                effects = await get_realm_research_effects(
                    connection,
                    realm_id,
                )

                duration = apply_construction_speed(
                    base_duration,
                    effects,
                )

                queue_data = await connection.fetchrow(
                    """
                    SELECT
                        COALESCE(MAX(queue_position), 0)
                            AS last_position,
                        MAX(finishes_at) AS last_finish
                    FROM construction_queue
                    WHERE realm_id = $1
                    """,
                    realm_id,
                )

                next_position = (
                    queue_data["last_position"] + 1
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

                if not error_message:
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
                            queue_position,
                            started_at,
                            finishes_at
                        )
                        VALUES (
                            $1,
                            $2,
                            $3,
                            $4,
                            GREATEST(
                                NOW(),
                                COALESCE($5, NOW())
                            ),
                            GREATEST(
                                NOW(),
                                COALESCE($5, NOW())
                            ) + $6 * INTERVAL '1 second'
                        )
                        """,
                        realm_id,
                        building_type,
                        target_level,
                        next_position,
                        queue_data["last_finish"],
                        duration,
                    )

    if error_message:
        await callback.answer(
            error_message,
            show_alert=True,
        )
        return

    await callback.answer(
        f"Edificio añadido a la cola: nivel {target_level}."
    )

    await render_buildings(callback)

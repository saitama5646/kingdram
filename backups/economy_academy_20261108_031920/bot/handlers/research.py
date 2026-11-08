
from datetime import datetime, timezone
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.connection import get_pool
from bot.services.research import (
    RESEARCH,
    RESOURCE_LABELS,
    get_research_cost,
    get_research_time,
    get_research_effects,
    format_cost,
)
from bot.keyboards.research import (
    research_keyboard,
    research_detail_keyboard,
    research_queue_keyboard,
)


router = Router()


EFFECT_LABELS = {
    "wood_production": "Producción de madera",
    "stone_production": "Producción de piedra",
    "gold_production": "Producción de oro",
    "food_production": "Producción de alimentos",
    "military_attack": "Ataque militar",
    "military_defense": "Defensa militar",
    "construction_speed": "Velocidad de construcción",
    "training_speed": "Velocidad de entrenamiento",
}


def format_remaining(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    seconds = max(
        0,
        int((value - datetime.now(timezone.utc)).total_seconds()),
    )

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours} h {minutes} min"

    if minutes:
        return f"{minutes} min {seconds} s"

    return f"{seconds} s"


def format_effects(effects):
    lines = []

    for effect, value in effects.items():
        label = EFFECT_LABELS.get(
            effect,
            effect.replace("_", " ").capitalize(),
        )

        percentage = value * 100

        lines.append(
            f"• {label}: <b>+{percentage:.0f}%</b>"
        )

    return "\n".join(lines) or "Sin efectos definidos."


async def get_realm_research(connection, realm_id):
    rows = await connection.fetch(
        """
        SELECT research_type, level
        FROM realm_research
        WHERE realm_id = $1
        """,
        realm_id,
    )

    return {
        row["research_type"]: row["level"]
        for row in rows
    }


async def get_realm_buildings(connection, realm_id):
    rows = await connection.fetch(
        """
        SELECT building_type, level
        FROM buildings
        WHERE realm_id = $1
        """,
        realm_id,
    )

    return {
        row["building_type"]: row["level"]
        for row in rows
    }


async def get_research_queue(connection, realm_id):
    return await connection.fetch(
        """
        SELECT
            id,
            research_type,
            target_level,
            queue_position,
            started_at,
            finishes_at
        FROM research_queue
        WHERE realm_id = $1
        ORDER BY queue_position, finishes_at, id
        """,
        realm_id,
    )


def get_projected_levels(levels, queue):
    projected = dict(levels)

    for item in queue:
        research_type = item["research_type"]

        projected[research_type] = max(
            projected.get(research_type, 0),
            item["target_level"],
        )

    return projected


async def render_research(callback):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id,
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar un reino.",
                show_alert=True,
            )
            return

        levels = await get_realm_research(
            connection,
            realm["id"],
        )

        queue = await get_research_queue(
            connection,
            realm["id"],
        )

    pending_types = {
        item["research_type"]: item["target_level"]
        for item in queue
    }

    lines = [
        "🔬 <b>ACADEMIA REAL</b>",
        "",
        f"🏰 Dominio: <b>{escape(realm['name'])}</b>",
        "",
        "Las tecnologías mejoran de forma permanente "
        "la economía, la ingeniería y el ejército.",
        "",
        "<b>PROGRESO TECNOLÓGICO</b>",
    ]

    for key, research in RESEARCH.items():
        level = levels.get(key, 0)

        status = (
            f"Nivel {level}"
            if key not in pending_types
            else (
                f"Nivel {level} "
                f"→ en cola: {pending_types[key]}"
            )
        )

        lines.append(
            f"{research['icon']} {research['name']}: "
            f"<b>{status}</b>"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=research_keyboard(
            levels,
            pending_types,
        ),
    )


@router.callback_query(F.data == "research")
async def research_handler(callback: CallbackQuery):
    await callback.answer()
    await render_research(callback)


@router.callback_query(F.data == "research:queue")
async def research_queue_handler(callback: CallbackQuery):
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
                "Primero debes fundar un reino.",
                show_alert=True,
            )
            return

        queue = await get_research_queue(
            connection,
            realm["id"],
        )

    await callback.answer()

    if not queue:
        text = (
            "🔬 <b>COLA DE INVESTIGACIÓN</b>\n\n"
            "No tienes investigaciones pendientes."
        )
    else:
        lines = [
            "🔬 <b>COLA DE INVESTIGACIÓN</b>",
            "",
        ]

        for item in queue:
            research = RESEARCH.get(
                item["research_type"],
                {},
            )

            name = research.get(
                "name",
                item["research_type"],
            )

            lines.append(
                f"{item['queue_position']}. "
                f"📚 <b>{escape(name)}</b> "
                f"→ nivel {item['target_level']}"
            )

            if item["queue_position"] == 1:
                lines.append(
                    "   Tiempo restante: "
                    f"<b>{format_remaining(item['finishes_at'])}</b>"
                )

        lines.extend([
            "",
            "Las investigaciones se completan "
            "automáticamente en orden.",
        ])

        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=research_queue_keyboard(),
    )


@router.callback_query(F.data.startswith("research:tech:"))
async def research_detail_handler(callback: CallbackQuery):
    research_type = callback.data.split(":")[-1]
    research = RESEARCH.get(research_type)

    if not research:
        await callback.answer(
            "Tecnología desconocida.",
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
                "Primero debes fundar un reino.",
                show_alert=True,
            )
            return

        realm_id = realm["id"]

        levels = await get_realm_research(
            connection,
            realm_id,
        )

        buildings = await get_realm_buildings(
            connection,
            realm_id,
        )

        queue = await get_research_queue(
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

    projected = get_projected_levels(
        levels,
        queue,
    )

    current_level = levels.get(research_type, 0)

    queued_targets = [
        item["target_level"]
        for item in queue
        if item["research_type"] == research_type
    ]

    target_level = (
        max(queued_targets) + 1
        if queued_targets
        else current_level + 1
    )

    cost = get_research_cost(
        research_type,
        target_level,
    )

    duration = get_research_time(
        research_type,
        target_level,
    )

    missing = []

    for requirement, required_level in (
        research["requirements"].items()
    ):
        current = projected.get(requirement, 0)

        if current < required_level:
            required_name = RESEARCH[requirement]["name"]

            missing.append(
                f"📚 {required_name}: "
                f"nivel {required_level}"
            )

    for building_type, required_level in (
        research["building_requirements"].items()
    ):
        current = buildings.get(building_type, 0)

        if current < required_level:
            missing.append(
                f"🏗 {building_type}: "
                f"nivel {required_level}"
            )

    effect_text = format_effects(
        research["effects"]
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
        f"{research['icon']} "
        f"<b>{escape(research['name'].upper())}</b>",
        "",
        escape(research["description"]),
        "",
        f"Rama: <b>{research['branch']}</b>",
        f"Nivel actual: <b>{current_level}</b>",
        f"Próximo nivel: <b>{target_level}</b>",
        "",
        "💰 <b>RECURSOS DISPONIBLES</b>",
        *available_lines,
        "",
        "<b>Coste de investigación</b>",
        *cost_lines,
        "",
        (
            "✅ <b>Recursos suficientes</b>"
            if sufficient
            else "❌ <b>Recursos insuficientes</b>"
        ),
        "",
        f"⏱ Duración: <b>{duration // 60} min "
        f"{duration % 60} s</b>",
        "",
        "<b>EFECTOS POR NIVEL</b>",
        effect_text,
        "",
        "<b>Requisitos tecnológicos</b>",
    ]

    if research["requirements"]:
        for requirement, required_level in (
            research["requirements"].items()
        ):
            name = RESEARCH[requirement]["name"]
            current = projected.get(requirement, 0)

            lines.append(
                f"📚 {name}: "
                f"{current}/{required_level}"
            )
    else:
        lines.append("Sin requisitos tecnológicos.")

    lines.extend([
        "",
        "<b>Requisitos de edificios</b>",
    ])

    if research["building_requirements"]:
        for building_type, required_level in (
            research["building_requirements"].items()
        ):
            current = buildings.get(building_type, 0)

            lines.append(
                f"🏗 {building_type}: "
                f"{current}/{required_level}"
            )
    else:
        lines.append("Sin requisitos de edificios.")

    if missing:
        lines.extend([
            "",
            "🔒 <b>Requisitos pendientes</b>",
            *missing,
        ])

    can_start = not missing and sufficient

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=research_detail_keyboard(
            research_type,
            can_start,
            bool(queued_targets),
        ),
    )


@router.callback_query(F.data.startswith("research:start:"))
async def start_research_handler(callback: CallbackQuery):
    research_type = callback.data.split(":")[-1]
    research = RESEARCH.get(research_type)

    if not research:
        await callback.answer(
            "Tecnología desconocida.",
            show_alert=True,
        )
        return

    pool = await get_pool()
    error = None
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
                error = "Primero debes fundar un reino."

            else:
                realm_id = realm["id"]

                levels = await get_realm_research(
                    connection,
                    realm_id,
                )

                buildings = await get_realm_buildings(
                    connection,
                    realm_id,
                )

                queue = await get_research_queue(
                    connection,
                    realm_id,
                )

                projected = get_projected_levels(
                    levels,
                    queue,
                )

                queued_targets = [
                    item["target_level"]
                    for item in queue
                    if item["research_type"] == research_type
                ]

                target_level = (
                    max(queued_targets) + 1
                    if queued_targets
                    else levels.get(research_type, 0) + 1
                )

                for requirement, required_level in (
                    research["requirements"].items()
                ):
                    if projected.get(requirement, 0) < required_level:
                        name = RESEARCH[requirement]["name"]

                        error = (
                            f"Necesitas {name} "
                            f"nivel {required_level}."
                        )
                        break

                if not error:
                    for building_type, required_level in (
                        research["building_requirements"].items()
                    ):
                        if buildings.get(building_type, 0) < required_level:
                            error = (
                                f"Necesitas {building_type} "
                                f"nivel {required_level}."
                            )
                            break

                if not error:
                    cost = get_research_cost(
                        research_type,
                        target_level,
                    )

                    duration = get_research_time(
                        research_type,
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
                        error = (
                            "No se encontraron los recursos del reino."
                        )

                    else:
                        insufficient = [
                            RESOURCE_LABELS[resource]
                            for resource, amount in cost.items()
                            if resources[resource] < amount
                        ]

                        if insufficient:
                            error = (
                                "Recursos insuficientes: "
                                + ", ".join(insufficient)
                            )

                if not error:
                    queue_data = await connection.fetchrow(
                        """
                        SELECT
                            COALESCE(MAX(queue_position), 0)
                                AS last_position,
                            MAX(finishes_at) AS last_finish
                        FROM research_queue
                        WHERE realm_id = $1
                        """,
                        realm_id,
                    )

                    next_position = (
                        queue_data["last_position"] + 1
                    )

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
                        INSERT INTO research_queue (
                            realm_id,
                            research_type,
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
                        research_type,
                        target_level,
                        next_position,
                        queue_data["last_finish"],
                        duration,
                    )

    if error:
        await callback.answer(
            error,
            show_alert=True,
        )
        return

    await callback.answer(
        f"Investigación añadida: nivel {target_level}."
    )

    await render_research(callback)

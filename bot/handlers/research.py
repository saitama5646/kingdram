
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
    format_cost
)
from bot.keyboards.research import (
    research_keyboard,
    research_detail_keyboard,
    research_queue_keyboard
)


router = Router()


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


async def get_realm_research(connection, realm_id):
    rows = await connection.fetch(
        """
        SELECT research_type, level
        FROM realm_research
        WHERE realm_id = $1
        """,
        realm_id
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
        realm_id
    )

    return {
        row["building_type"]: row["level"]
        for row in rows
    }


async def render_research(callback):
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
                "Primero debes fundar un reino.",
                show_alert=True
            )
            return

        levels = await get_realm_research(
            connection,
            realm["id"]
        )

        pending = await connection.fetchrow(
            """
            SELECT research_type
            FROM research_queue
            WHERE realm_id = $1
            """,
            realm["id"]
        )

    lines = [
        "🔬 <b>ACADEMIA REAL</b>",
        "",
        f"🏰 Dominio: <b>{escape(realm['name'])}</b>",
        "",
        "Desarrolla nuevas tecnologías para fortalecer "
        "la economía, la ingeniería y el ejército.",
        "",
        "<b>PROGRESO TECNOLÓGICO</b>"
    ]

    for key, research in RESEARCH.items():
        level = levels.get(key, 0)

        status = (
            "En investigación"
            if pending and pending["research_type"] == key
            else f"Nivel {level}"
        )

        lines.append(
            f"{research['icon']} {research['name']}: "
            f"<b>{status}</b>"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=research_keyboard(
            levels,
            pending["research_type"] if pending else None
        )
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
            callback.from_user.id
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar un reino.",
                show_alert=True
            )
            return

        queue = await connection.fetchrow(
            """
            SELECT research_type, target_level, started_at, finishes_at
            FROM research_queue
            WHERE realm_id = $1
            """,
            realm["id"]
        )

    await callback.answer()

    if not queue:
        text = (
            "🔬 <b>COLA DE INVESTIGACIÓN</b>\n\n"
            "No tienes investigaciones en curso."
        )
    else:
        research = RESEARCH.get(queue["research_type"], {})
        name = research.get("name", queue["research_type"])

        text = (
            "🔬 <b>COLA DE INVESTIGACIÓN</b>\n\n"
            f"📚 Tecnología: <b>{escape(name)}</b>\n"
            f"Nivel objetivo: <b>{queue['target_level']}</b>\n"
            f"Tiempo restante: <b>{format_remaining(queue['finishes_at'])}</b>\n\n"
            "La investigación se completará automáticamente."
        )

    await callback.message.edit_text(
        text,
        reply_markup=research_queue_keyboard()
    )


@router.callback_query(F.data.startswith("research:tech:"))
async def research_detail_handler(callback: CallbackQuery):
    research_type = callback.data.split(":")[-1]
    research = RESEARCH.get(research_type)

    if not research:
        await callback.answer(
            "Tecnología desconocida.",
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

        realm_id = realm["id"]

        levels = await get_realm_research(
            connection,
            realm_id
        )

        buildings = await get_realm_buildings(
            connection,
            realm_id
        )

        pending = await connection.fetchrow(
            """
            SELECT research_type, target_level, finishes_at
            FROM research_queue
            WHERE realm_id = $1
            """,
            realm_id
        )

    level = levels.get(research_type, 0)
    target_level = level + 1

    cost = get_research_cost(
        research_type,
        target_level
    )

    duration = get_research_time(
        research_type,
        target_level
    )

    missing = []

    for requirement, required_level in research["requirements"].items():
        current = levels.get(requirement, 0)

        if current < required_level:
            required_name = RESEARCH[requirement]["name"]
            missing.append(
                f"📚 {required_name}: nivel {required_level}"
            )

    for building_type, required_level in research["building_requirements"].items():
        current = buildings.get(building_type, 0)

        if current < required_level:
            missing.append(
                f"🏗 {building_type}: nivel {required_level}"
            )

    is_pending = bool(pending)
    can_start = not missing and not is_pending

    lines = [
        f"{research['icon']} <b>{escape(research['name'].upper())}</b>",
        "",
        research["description"],
        "",
        f"Rama: <b>{research['branch']}</b>",
        f"Nivel actual: <b>{level}</b>",
        f"Próximo nivel: <b>{target_level}</b>",
        "",
        "<b>Coste de investigación</b>",
        format_cost(cost),
        "",
        f"Duración: <b>{duration // 60} min {duration % 60} s</b>",
        "",
        "<b>Requisitos tecnológicos</b>"
    ]

    if research["requirements"]:
        for requirement, required_level in research["requirements"].items():
            name = RESEARCH[requirement]["name"]
            current = levels.get(requirement, 0)

            lines.append(
                f"📚 {name}: {current}/{required_level}"
            )
    else:
        lines.append("Sin requisitos tecnológicos.")

    lines.extend([
        "",
        "<b>Requisitos de edificios</b>"
    ])

    if research["building_requirements"]:
        for building_type, required_level in research["building_requirements"].items():
            current = buildings.get(building_type, 0)

            lines.append(
                f"🏗 {building_type}: {current}/{required_level}"
            )
    else:
        lines.append("Sin requisitos de edificios.")

    if missing:
        lines.extend([
            "",
            "🔒 <b>Requisitos pendientes</b>",
            *missing
        ])

    if pending:
        pending_name = RESEARCH.get(
            pending["research_type"], {}
        ).get("name", pending["research_type"])

        lines.extend([
            "",
            f"⏳ Ya investigas: <b>{escape(pending_name)}</b>",
            f"Tiempo restante: {format_remaining(pending['finishes_at'])}"
        ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=research_detail_keyboard(
            research_type,
            can_start,
            is_pending
        )
    )


@router.callback_query(F.data.startswith("research:start:"))
async def start_research_handler(callback: CallbackQuery):
    research_type = callback.data.split(":")[-1]
    research = RESEARCH.get(research_type)

    if not research:
        await callback.answer(
            "Tecnología desconocida.",
            show_alert=True
        )
        return

    pool = await get_pool()
    error = None

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
                error = "Primero debes fundar un reino."
            else:
                realm_id = realm["id"]

                pending = await connection.fetchval(
                    """
                    SELECT id
                    FROM research_queue
                    WHERE realm_id = $1
                    FOR UPDATE
                    """,
                    realm_id
                )

                if pending:
                    error = "Ya tienes una investigación en curso."

                else:
                    levels = await get_realm_research(
                        connection,
                        realm_id
                    )

                    buildings = await get_realm_buildings(
                        connection,
                        realm_id
                    )

                    for requirement, required_level in research["requirements"].items():
                        if levels.get(requirement, 0) < required_level:
                            name = RESEARCH[requirement]["name"]
                            error = (
                                f"Necesitas {name} "
                                f"nivel {required_level}."
                            )
                            break

                    if not error:
                        for building_type, required_level in research["building_requirements"].items():
                            if buildings.get(building_type, 0) < required_level:
                                error = (
                                    f"Necesitas {building_type} "
                                    f"nivel {required_level}."
                                )
                                break

                    if not error:
                        target_level = levels.get(research_type, 0) + 1

                        cost = get_research_cost(
                            research_type,
                            target_level
                        )

                        duration = get_research_time(
                            research_type,
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
                            error = "No se encontraron los recursos del reino."

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
                                INSERT INTO research_queue (
                                    realm_id,
                                    research_type,
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
                                research_type,
                                target_level,
                                duration
                            )

    if error:
        await callback.answer(
            error,
            show_alert=True
        )
        return

    await callback.answer("Investigación iniciada.")
    await render_research(callback)

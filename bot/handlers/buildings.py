
from datetime import timedelta

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


def format_cost(cost):
    labels = {
        "wood": "🪵 Madera",
        "stone": "🪨 Piedra",
        "gold": "🪙 Oro",
        "food": "🌾 Alimentos"
    }

    return "\n".join(
        f"{labels[resource]}: {amount:,}"
        for resource, amount in cost.items()
    )


@router.callback_query(F.data == "buildings")
async def buildings_handler(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            "SELECT id FROM realms WHERE owner_id = $1",
            callback.from_user.id
        )

        if not realm:
            await callback.answer(
                "Debes fundar tu reino primero.",
                show_alert=True
            )
            return

        buildings = await connection.fetch(
            """
            SELECT
                b.building_type,
                b.level,
                q.target_level,
                q.finishes_at
            FROM buildings b
            LEFT JOIN construction_queue q
                ON q.realm_id = b.realm_id
                AND q.building_type = b.building_type
            WHERE b.realm_id = $1
            ORDER BY b.building_type
            """,
            realm["id"]
        )

    lines = ["🏗 <b>Edificios de tu reino</b>\n"]

    for building in buildings:
        info = BUILDINGS.get(building["building_type"])

        if not info:
            continue

        line = (
            f"{info['icon']} <b>{info['name']}</b>\n"
            f"Nivel: {building['level']}"
        )

        if building["target_level"]:
            line += (
                f"\n⏳ Mejorando al nivel "
                f"{building['target_level']}"
            )

        lines.append(line)

    await callback.answer()

    await callback.message.edit_text(
        "\n\n".join(lines),
        reply_markup=buildings_keyboard()
    )


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
            "SELECT id FROM realms WHERE owner_id = $1",
            callback.from_user.id
        )

        if not realm:
            await callback.answer(
                "No posees un reino.",
                show_alert=True
            )
            return

        building = await connection.fetchrow(
            """
            SELECT level
            FROM buildings
            WHERE realm_id = $1 AND building_type = $2
            """,
            realm["id"],
            building_type
        )

        queue = await connection.fetchrow(
            """
            SELECT target_level, finishes_at
            FROM construction_queue
            WHERE realm_id = $1 AND building_type = $2
            """,
            realm["id"],
            building_type
        )

    level = building["level"] if building else 0
    next_level = level + 1
    cost = get_upgrade_cost(building_type, next_level)
    duration = get_upgrade_time(building_type, next_level)

    text = (
        f"{info['icon']} <b>{info['name']}</b>\n\n"
        f"{info['description']}\n\n"
        f"Nivel actual: {level}\n"
        f"Próximo nivel: {next_level}\n\n"
        f"<b>Coste de mejora</b>\n"
        f"{format_cost(cost)}\n\n"
        f"⏳ Tiempo: {duration // 60} min "
        f"{duration % 60} s"
    )

    if queue:
        text += (
            "\n\n🚧 <b>Construcción activa</b>\n"
            f"Nivel objetivo: {queue['target_level']}\n"
            f"Finaliza: {queue['finishes_at'].strftime('%H:%M:%S UTC')}"
        )

    await callback.answer()

    await callback.message.edit_text(
        text,
        reply_markup=building_detail_keyboard(building_type)
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
                await callback.answer(
                    "No posees un reino.",
                    show_alert=True
                )
                return

            realm_id = realm["id"]

            building = await connection.fetchrow(
                """
                SELECT level
                FROM buildings
                WHERE realm_id = $1 AND building_type = $2
                FOR UPDATE
                """,
                realm_id,
                building_type
            )

            if not building:
                await callback.answer(
                    "Este edificio aún no está construido.",
                    show_alert=True
                )
                return

            pending = await connection.fetchrow(
                """
                SELECT id
                FROM construction_queue
                WHERE realm_id = $1 AND building_type = $2
                """,
                realm_id,
                building_type
            )

            if pending:
                await callback.answer(
                    "Este edificio ya está mejorándose.",
                    show_alert=True
                )
                return

            target_level = building["level"] + 1

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
                await callback.answer(
                    "No se encontraron recursos.",
                    show_alert=True
                )
                return

            for resource, amount in cost.items():
                if resources[resource] < amount:
                    await callback.answer(
                        f"No tienes suficiente {resource}.",
                        show_alert=True
                    )
                    return

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

    await callback.answer("Construcción iniciada.")

    await callback.message.edit_text(
        f"🏗 <b>Mejora iniciada</b>\n\n"
        f"{BUILDINGS[building_type]['icon']} "
        f"{BUILDINGS[building_type]['name']}\n"
        f"Nivel objetivo: {target_level}\n\n"
        f"⏳ Duración: {duration // 60} min "
        f"{duration % 60} s\n\n"
        "Los recursos han sido descontados. "
        "El edificio mejorará automáticamente "
        "cuando termine el tiempo.",
        reply_markup=buildings_keyboard()
    )

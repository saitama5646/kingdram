
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.connection import get_pool
from bot.keyboards.main_menu import (
    main_menu_keyboard,
    create_realm_keyboard
)

router = Router()


@router.callback_query(F.data == "create_realm")
async def create_realm_handler(callback: CallbackQuery):
    pool = await get_pool()
    user = callback.from_user

    async with pool.acquire() as connection:
        async with connection.transaction():
            player = await connection.fetchrow(
                """
                SELECT id
                FROM players
                WHERE id = $1
                """,
                user.id
            )

            if not player:
                await callback.answer(
                    "Usa /start primero.",
                    show_alert=True
                )
                return

            realm = await connection.fetchrow(
                """
                SELECT id, name
                FROM realms
                WHERE owner_id = $1
                """,
                user.id
            )

            if realm:
                await callback.answer(
                    "Ya posees un reino.",
                    show_alert=True
                )

                await callback.message.edit_text(
                    f"🏰 <b>Reino de {realm['name']}</b>\n\n"
                    "Tu dominio ya ha sido fundado.",
                    reply_markup=main_menu_keyboard()
                )
                return

            realm_name = f"Reino de {user.first_name}"

            realm = await connection.fetchrow(
                """
                INSERT INTO realms (
                    owner_id,
                    name
                )
                VALUES ($1, $2)
                RETURNING id, name
                """,
                user.id,
                realm_name
            )

            realm_id = realm["id"]

            await connection.execute(
                """
                INSERT INTO resources (
                    realm_id,
                    wood,
                    stone,
                    gold,
                    food
                )
                VALUES ($1, 1250, 850, 2400, 1600)
                """,
                realm_id
            )

            await connection.execute(
                """
                INSERT INTO buildings (
                    realm_id,
                    building_type,
                    level
                )
                VALUES
                    ($1, 'sawmill', 1),
                    ($1, 'quarry', 1),
                    ($1, 'farm', 1)
                """,
                realm_id
            )

            await connection.execute(
                """
                INSERT INTO provinces (
                    realm_id,
                    name,
                    province_number
                )
                VALUES ($1, 'Tierras de la Corona', 1)
                """,
                realm_id
            )

    await callback.answer("¡Tu reino ha sido fundado!")

    await callback.message.edit_text(
        "👑 <b>¡Tu reino ha sido fundado!</b>\n\n"
        f"🏰 Nombre: <b>{realm_name}</b>\n"
        "🗺 Provincia inicial: Tierras de la Corona\n\n"
        "Tus tierras están listas para desarrollarse.\n"
        "Administra tus recursos y comienza a construir "
        "tu imperio.",
        reply_markup=main_menu_keyboard()
    )


@router.callback_query(F.data == "kingdom")
async def kingdom_handler(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT
                r.name,
                r.level,
                r.population,
                r.power,
                p.wood,
                p.stone,
                p.gold,
                p.food
            FROM realms r
            JOIN resources p ON p.realm_id = r.id
            WHERE r.owner_id = $1
            """,
            callback.from_user.id
        )

    if not realm:
        await callback.answer(
            "Primero debes fundar tu reino.",
            show_alert=True
        )

        await callback.message.edit_text(
            "🏰 <b>Aún no posees un reino.</b>",
            reply_markup=create_realm_keyboard()
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        f"🏰 <b>{realm['name']}</b>\n\n"
        f"⭐ Nivel: {realm['level']}\n"
        f"👥 Población: {realm['population']}\n"
        f"⚔ Poder: {realm['power']}\n\n"
        "<b>Recursos disponibles</b>\n"
        f"🪵 Madera: {realm['wood']:,}\n"
        f"🪨 Piedra: {realm['stone']:,}\n"
        f"🪙 Oro: {realm['gold']:,}\n"
        f"🌾 Alimentos: {realm['food']:,}",
        reply_markup=main_menu_keyboard()
    )

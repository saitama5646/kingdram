
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.connection import get_pool
from bot.keyboards.main_menu import (
    main_menu_keyboard,
    create_realm_keyboard
)

router = Router()


async def ensure_realm_resources(connection, realm_id):
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
        ON CONFLICT (realm_id) DO NOTHING
        """,
        realm_id
    )


async def show_kingdom(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT
                id,
                name,
                level,
                population,
                power
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
                "Funda tu primer dominio para comenzar "
                "a desarrollar tus tierras.",
                reply_markup=create_realm_keyboard()
            )
            return

        await ensure_realm_resources(
            connection,
            realm["id"]
        )

        resources = await connection.fetchrow(
            """
            SELECT wood, stone, gold, food
            FROM resources
            WHERE realm_id = $1
            """,
            realm["id"]
        )

    await callback.answer()

    await callback.message.edit_text(
        f"🏰 <b>{realm['name']}</b>\n\n"
        f"⭐ Nivel: {realm['level']}\n"
        f"👥 Población: {realm['population']:,}\n"
        f"⚔ Poder: {realm['power']:,}\n\n"
        "<b>Recursos disponibles</b>\n"
        f"🪵 Madera: {resources['wood']:,}\n"
        f"🪨 Piedra: {resources['stone']:,}\n"
        f"🪙 Oro: {resources['gold']:,}\n"
        f"🌾 Alimentos: {resources['food']:,}",
        reply_markup=main_menu_keyboard()
    )


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
                await ensure_realm_resources(
                    connection,
                    realm["id"]
                )

            else:
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

                await ensure_realm_resources(
                    connection,
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
                    ON CONFLICT (realm_id, building_type)
                    DO NOTHING
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
                    VALUES (
                        $1,
                        'Tierras de la Corona',
                        1
                    )
                    ON CONFLICT (realm_id, province_number)
                    DO NOTHING
                    """,
                    realm_id
                )

    await callback.answer(
        "Tu reino ya está disponible."
    )

    await show_kingdom(callback)


@router.callback_query(F.data == "kingdom")
async def kingdom_handler(callback: CallbackQuery):
    await show_kingdom(callback)


from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.connection import get_pool
from bot.keyboards.main_menu import (
    main_menu_keyboard,
    create_realm_keyboard
)

router = Router()


class RealmCreation(StatesGroup):
    waiting_for_name = State()


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
async def create_realm_handler(
    callback: CallbackQuery,
    state: FSMContext
):
    pool = await get_pool()

    async with pool.acquire() as connection:
        existing = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id
        )

    if existing:
        await state.clear()
        await callback.answer(
            "Ya tienes un reino fundado.",
            show_alert=True
        )
        await show_kingdom(callback)
        return

    await state.set_state(
        RealmCreation.waiting_for_name
    )

    await callback.answer()

    await callback.message.edit_text(
        "🏰 <b>Fundación de un nuevo reino</b>\n\n"
        "Escribe el nombre que llevará tu reino.\n\n"
        "El nombre tendrá entre <b>3 y 24 caracteres</b>.\n"
        "No se añadirá ningún prefijo automáticamente.\n\n"
        "Ejemplo: <b>Valyria</b>"
    )


@router.message(RealmCreation.waiting_for_name)
async def receive_realm_name(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "Escribe un nombre válido para tu reino."
        )
        return

    realm_name = " ".join(message.text.split())

    if len(realm_name) < 3 or len(realm_name) > 24:
        await message.answer(
            "El nombre debe tener entre "
            "<b>3 y 24 caracteres</b>.\n\n"
            "Inténtalo de nuevo."
        )
        return

    if any(ord(char) < 32 for char in realm_name):
        await message.answer(
            "El nombre contiene caracteres no válidos."
        )
        return

    pool = await get_pool()
    user_id = message.from_user.id

    async with pool.acquire() as connection:
        async with connection.transaction():
            player = await connection.fetchrow(
                """
                SELECT id
                FROM players
                WHERE id = $1
                FOR UPDATE
                """,
                user_id
            )

            if not player:
                await state.clear()
                await message.answer(
                    "No se encontró tu perfil. "
                    "Ejecuta /start e inténtalo de nuevo."
                )
                return

            existing = await connection.fetchrow(
                """
                SELECT id, name
                FROM realms
                WHERE owner_id = $1
                """,
                user_id
            )

            if existing:
                realm = existing
                already_exists = True

            else:
                realm = await connection.fetchrow(
                    """
                    INSERT INTO realms (
                        owner_id,
                        name
                    )
                    VALUES ($1, $2)
                    RETURNING id, name
                    """,
                    user_id,
                    realm_name
                )

                already_exists = False

                await ensure_realm_resources(
                    connection,
                    realm["id"]
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
                    realm["id"]
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
                    realm["id"]
                )

    await state.clear()

    if already_exists:
        await message.answer(
            "Ya habías fundado un reino anteriormente.\n\n"
            f"🏰 Tu dominio actual es <b>{realm['name']}</b>.",
            reply_markup=main_menu_keyboard()
        )
        return

    await message.answer(
        "👑 <b>¡Tu reino ha sido fundado!</b>\n\n"
        f"🏰 Nombre del reino: <b>{realm['name']}</b>\n\n"
        "Tus tierras ya están listas. "
        "Comienza a construir tu legado.",
        reply_markup=main_menu_keyboard()
    )


@router.callback_query(F.data == "kingdom")
async def kingdom_handler(callback: CallbackQuery):
    await show_kingdom(callback)

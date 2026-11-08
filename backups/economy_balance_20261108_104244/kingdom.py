
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import get_pool
from bot.services.world import assign_world_position
from bot.keyboards.main_menu import (
    main_menu_keyboard,
    create_realm_keyboard,
)


router = Router()


class RealmCreation(StatesGroup):
    waiting_for_name = State()


class RealmRename(StatesGroup):
    waiting_for_name = State()


def validate_realm_name(value):
    if not value:
        return None, "Escribe un nombre válido para tu reino."

    name = " ".join(value.split())

    if len(name) < 3 or len(name) > 24:
        return None, (
            "El nombre debe tener entre "
            "<b>3 y 24 caracteres</b>."
        )

    if any(ord(char) < 32 for char in name):
        return None, "El nombre contiene caracteres no válidos."

    if not any(char.isalnum() for char in name):
        return None, "El nombre debe contener letras o números."

    return name, None


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
        VALUES ($1, 1800, 1200, 500, 1600)
        ON CONFLICT (realm_id) DO NOTHING
        """,
        realm_id,
    )


def kingdom_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✏️ Cambiar nombre",
        callback_data="kingdom:rename",
    )
    builder.button(
        text="🔄 Actualizar",
        callback_data="kingdom",
    )
    builder.button(
        text="📦 Recursos",
        callback_data="economy",
    )
    builder.button(
        text="🏗 Edificios",
        callback_data="buildings",
    )
    builder.button(
        text="⚔ Ejército",
        callback_data="army",
    )
    builder.button(
        text="↩ Menú principal",
        callback_data="main_menu",
    )

    builder.adjust(1, 2, 2, 1)

    return builder.as_markup()


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
                power,
                continent,
                region,
                position
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

            await callback.message.edit_text(
                "🏰 <b>Aún no posees un reino.</b>\n\n"
                "Funda tu primer dominio para comenzar "
                "a desarrollar tus tierras.",
                reply_markup=create_realm_keyboard(),
            )
            return

        await ensure_realm_resources(
            connection,
            realm["id"],
        )

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

        resources = await connection.fetchrow(
            """
            SELECT wood, stone, gold, food
            FROM resources
            WHERE realm_id = $1
            """,
            realm["id"],
        )

    await callback.answer()

    await callback.message.edit_text(
        f"🏰 <b>{escape(realm['name'])}</b>\n\n"
        f"⭐ Nivel: <b>{realm['level']}</b>\n"
        f"👥 Población: <b>{realm['population']:,}</b>\n"
        f"⚔ Poder: <b>{realm['power']:,}</b>\n"
        f"🗺 Coordenadas: "
        f"<code>{coordinates[0]}:{coordinates[1]}:{coordinates[2]}</code>\n\n"
        "<b>Recursos disponibles</b>\n"
        f"🪵 Madera: <b>{resources['wood']:,}</b>\n"
        f"🪨 Piedra: <b>{resources['stone']:,}</b>\n"
        f"🪙 Oro: <b>{resources['gold']:,}</b>\n"
        f"🌾 Alimentos: <b>{resources['food']:,}</b>",
        reply_markup=kingdom_keyboard(),
    )


@router.callback_query(F.data == "create_realm")
async def create_realm_handler(
    callback: CallbackQuery,
    state: FSMContext,
):
    pool = await get_pool()

    async with pool.acquire() as connection:
        existing = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id,
        )

    if existing:
        await state.clear()
        await callback.answer(
            "Ya tienes un reino fundado.",
            show_alert=True,
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
    state: FSMContext,
):
    realm_name, error = validate_realm_name(message.text)

    if error:
        await message.answer(error)
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
                user_id,
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
                user_id,
            )

            if existing:
                realm = existing
                already_exists = True
                coordinates = None

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
                    realm_name,
                )

                already_exists = False

                await ensure_realm_resources(
                    connection,
                    realm["id"],
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
                    realm["id"],
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
                    realm["id"],
                )

                coordinates = await assign_world_position(
                    connection,
                    realm["id"],
                )

    await state.clear()

    if already_exists:
        await message.answer(
            "Ya habías fundado un reino anteriormente.\n\n"
            f"🏰 Tu dominio actual es <b>{escape(realm['name'])}</b>.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "👑 <b>¡Tu reino ha sido fundado!</b>\n\n"
        f"🏰 Nombre: <b>{escape(realm['name'])}</b>\n"
        f"🗺 Coordenadas: "
        f"<code>{coordinates[0]}:{coordinates[1]}:{coordinates[2]}</code>\n\n"
        "Tus tierras ya están listas. "
        "Comienza a construir tu legado.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "kingdom")
async def kingdom_handler(callback: CallbackQuery):
    await show_kingdom(callback)


@router.callback_query(F.data == "kingdom:rename")
async def rename_realm_handler(
    callback: CallbackQuery,
    state: FSMContext,
):
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
            "No tienes un reino que puedas renombrar.",
            show_alert=True,
        )
        return

    await state.set_state(
        RealmRename.waiting_for_name
    )

    await callback.answer()

    await callback.message.edit_text(
        "✏️ <b>Cambiar nombre del reino</b>\n\n"
        f"Nombre actual: <b>{escape(realm['name'])}</b>\n\n"
        "Escribe el nuevo nombre.\n"
        "Debe tener entre <b>3 y 24 caracteres</b>.\n\n"
        "El cambio no modificará tus edificios, "
        "recursos, ejército ni coordenadas."
    )


@router.message(RealmRename.waiting_for_name)
async def receive_new_realm_name(
    message: Message,
    state: FSMContext,
):
    realm_name, error = validate_realm_name(message.text)

    if error:
        await message.answer(error)
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            UPDATE realms
            SET name = $1
            WHERE owner_id = $2
            RETURNING id, name, continent, region, position
            """,
            realm_name,
            message.from_user.id,
        )

    await state.clear()

    if not realm:
        await message.answer(
            "No se encontró tu reino. "
            "No se pudo cambiar el nombre."
        )
        return

    await message.answer(
        "👑 <b>Nombre del reino actualizado.</b>\n\n"
        f"🏰 Nuevo nombre: <b>{escape(realm['name'])}</b>\n"
        f"🗺 Coordenadas: "
        f"<code>{realm['continent']}:{realm['region']}:{realm['position']}</code>\n\n"
        "Tu reino conserva todos sus edificios, "
        "recursos, tropas y territorios.",
        reply_markup=kingdom_keyboard(),
    )

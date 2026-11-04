from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.database.connection import get_pool
from bot.keyboards.main_menu import (
    persistent_menu_keyboard,
    create_realm_keyboard,
)


router = Router()


@router.message(CommandStart())
async def start_handler(message: Message):
    pool = await get_pool()
    user = message.from_user

    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO players (
                id,
                username,
                first_name
            )
            VALUES ($1, $2, $3)
            ON CONFLICT (id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name
            """,
            user.id,
            user.username,
            user.first_name or "Jugador",
        )

        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            user.id,
        )

    if realm:
        await message.answer(
            f"🏰 <b>Bienvenido de nuevo, {user.first_name or 'gobernante'}.</b>\n\n"
            f"Tu reino <b>{realm['name']}</b> continúa "
            "esperando tus órdenes.\n\n"
            "Utiliza el teclado inferior para acceder "
            "directamente a cada apartado de Kingdram.",
            reply_markup=persistent_menu_keyboard(),
        )

    else:
        await message.answer(
            "🏰 <b>Bienvenido a Kingdram.</b>\n\n"
            "Un mundo de reinos, ambición y leyenda.\n\n"
            "Todavía no posees tierras. Ha llegado el momento "
            "de fundar tu propio reino y comenzar tu legado.\n\n"
            "Después de fundarlo podrás utilizar el teclado "
            "inferior para administrar tu dominio.",
            reply_markup=persistent_menu_keyboard(),
        )

        await message.answer(
            "👑 <b>Comienza tu historia:</b>",
            reply_markup=create_realm_keyboard(),
        )

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.handlers.menu import build_main_menu
from bot.keyboards.main_menu import main_menu_keyboard


router = Router()


@router.callback_query(F.data == "dashboard:refresh")
async def refresh_dashboard(callback: CallbackQuery):
    await callback.answer("Actualizando reino...")

    text = await build_main_menu(
        callback.from_user.id
    )

    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )

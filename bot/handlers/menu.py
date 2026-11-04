
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import main_menu_keyboard

router = Router()

PAGES = {
    "buildings": (
        "🏗 Edificios",
        "Aquí podrás administrar las construcciones "
        "y mejorar la infraestructura de tu reino."
    ),
    "army": (
        "⚔ Ejército",
        "Aquí podrás reclutar, entrenar "
        "y administrar tus tropas."
    ),
    "diplomacy": (
        "👑 Diplomacia",
        "Aquí podrás establecer relaciones "
        "con otros reinos."
    ),
    "ranking": (
        "🏆 Clasificación",
        "Aquí podrás consultar los reinos "
        "más poderosos de Kingdram."
    )
}


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "🏰 <b>KINGDRAM</b>\n\n"
        "El destino de tu reino está en tus manos.\n"
        "Selecciona un apartado:",
        reply_markup=main_menu_keyboard()
    )


@router.callback_query(F.data.in_(PAGES.keys()))
async def page_handler(callback: CallbackQuery):
    page = PAGES.get(callback.data)

    if not page:
        await callback.answer(
            "Apartado no disponible.",
            show_alert=True
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        f"<b>{page[0]}</b>\n\n"
        f"{page[1]}\n\n"
        "<i>Este sistema será implementado "
        "en una próxima etapa.</i>",
        reply_markup=main_menu_keyboard()
    )

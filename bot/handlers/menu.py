from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.keyboards.main_menu import (
    main_menu_keyboard,
    back_to_menu_keyboard,
)

from bot.handlers.kingdom import show_kingdom
from bot.handlers.buildings import render_buildings
from bot.handlers.army import render_army
from bot.handlers.economy import render_economy
from bot.handlers.research import render_research
from bot.handlers.territory import render_territories
from bot.handlers.ranking import ranking_handler
from bot.handlers.battle import battle_menu


router = Router()


class MessageProxy:
    """Adapta una respuesta de mensaje al formato usado por las pantallas."""

    def __init__(self, message: Message):
        self.source = message

    async def edit_text(self, text, **kwargs):
        await self.source.answer(
            text,
            **kwargs,
        )


class MessageScreenContext:
    """Permite reutilizar los renderizadores de CallbackQuery desde mensajes."""

    def __init__(self, message: Message):
        self.from_user = message.from_user
        self.message = MessageProxy(message)
        self.source = message

    async def answer(self, text=None, show_alert=False, **kwargs):
        if text and show_alert:
            await self.source.answer(
                text,
                **kwargs,
            )


MENU_ACTIONS = {
    "🏰 Reino": "kingdom",
    "⚔ Ejército": "army",
    "🏗 Edificios": "buildings",
    "🔬 Investigaciones": "research",
    "📦 Recursos": "economy",
    "🗺 Territorios": "territory",
    "🛡 Guerra": "battle",
    "🏆 Clasificación": "ranking",
    "👑 Diplomacia": "diplomacy",
    "⌂ Menú principal": "main_menu",
}


async def show_main_menu_message(message: Message):
    await message.answer(
        "🏰 <b>KINGDRAM</b>\n\n"
        "El destino de tu reino está en tus manos.\n"
        "Selecciona el apartado que deseas administrar.",
        reply_markup=main_menu_keyboard(),
    )


async def show_diplomacy(context):
    await context.message.edit_text(
        "👑 <b>DIPLOMACIA REAL</b>\n\n"
        "Aquí se administrarán las relaciones entre reinos, "
        "las alianzas y los acuerdos diplomáticos.\n\n"
        "⚒ <b>Estado:</b> sistema diplomático pendiente "
        "de integración.\n\n"
        "Los apartados que todavía no están implementados "
        "no realizarán acciones ficticias.",
        reply_markup=back_to_menu_keyboard(),
    )


async def open_screen(context, destination):
    if destination == "kingdom":
        await show_kingdom(context)

    elif destination == "army":
        await render_army(context)

    elif destination == "buildings":
        await render_buildings(context)

    elif destination == "research":
        await render_research(context)

    elif destination == "economy":
        await render_economy(context)

    elif destination == "territory":
        await render_territories(context)

    elif destination == "battle":
        await battle_menu(context)

    elif destination == "ranking":
        await ranking_handler(context)

    elif destination == "diplomacy":
        await show_diplomacy(context)


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "🏰 <b>KINGDRAM</b>\n\n"
        "El destino de tu reino está en tus manos.\n"
        "Selecciona un apartado:",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "diplomacy")
async def diplomacy_handler(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "👑 <b>DIPLOMACIA REAL</b>\n\n"
        "Aquí se administrarán las relaciones entre reinos, "
        "las alianzas y los acuerdos diplomáticos.\n\n"
        "⚒ <b>Estado:</b> sistema diplomático pendiente "
        "de integración.\n\n"
        "Los apartados que todavía no están implementados "
        "no realizarán acciones ficticias.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(F.text.in_(set(MENU_ACTIONS.keys())))
async def persistent_menu_handler(
    message: Message,
    state: FSMContext,
):
    destination = MENU_ACTIONS.get(message.text)

    if not destination:
        return

    # Evita que un botón del menú se interprete como el nombre
    # del reino durante la fundación o el cambio de nombre.
    await state.clear()

    if destination == "main_menu":
        await show_main_menu_message(message)
        return

    context = MessageScreenContext(message)

    await open_screen(
        context,
        destination,
    )

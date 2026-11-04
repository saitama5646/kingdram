
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def territory_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Actualizar territorios",
                    callback_data="territory_refresh"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Consultar recursos",
                    callback_data="economy"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏰 Mi reino",
                    callback_data="kingdom"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⌂ Menú principal",
                    callback_data="main_menu"
                )
            ]
        ]
    )


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def economy_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Actualizar economía",
                    callback_data="economy_refresh"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏺 Bazar del Reino",
                    callback_data="bazaar"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏗 Administrar edificios",
                    callback_data="buildings"
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩ Volver al reino",
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

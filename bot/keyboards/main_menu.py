
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏰 Mi reino",
                    callback_data="kingdom"
                ),
                InlineKeyboardButton(
                    text="📦 Recursos",
                    callback_data="economy"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏗 Edificios",
                    callback_data="buildings"
                ),
                InlineKeyboardButton(
                    text="🗺 Territorios",
                    callback_data="territory"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚔ Ejército",
                    callback_data="army"
                ),
                InlineKeyboardButton(
                    text="👑 Diplomacia",
                    callback_data="diplomacy"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Clasificación",
                    callback_data="ranking"
                )
            ]
        ]
    )


def create_realm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚒ Fundar mi reino",
                    callback_data="create_realm"
                )
            ]
        ]
    )


def back_to_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩ Volver al menú",
                    callback_data="main_menu"
                )
            ]
        ]
    )

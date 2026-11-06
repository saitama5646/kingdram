from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


def persistent_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="⌂ Menú principal"),
                KeyboardButton(text="⚔ Ejército"),
            ],
            [
                KeyboardButton(text="🏗 Edificios"),
                KeyboardButton(text="🔬 Investigaciones"),
            ],
            [
                KeyboardButton(text="🕵 Espionaje"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="¿Qué deseas administrar?",
    )


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Actualizar panel",
                    callback_data="dashboard:refresh",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏰 Reino",
                    callback_data="kingdom",
                ),
                InlineKeyboardButton(
                    text="⚔ Ejército",
                    callback_data="army",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏗 Edificios",
                    callback_data="buildings",
                ),
                InlineKeyboardButton(
                    text="🔬 Investigaciones",
                    callback_data="research",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🕵 Espionaje",
                    callback_data="espionage",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📦 Recursos",
                    callback_data="economy",
                ),
                InlineKeyboardButton(
                    text="🗺 Territorios",
                    callback_data="territory",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛡 Guerra",
                    callback_data="battle",
                ),
                InlineKeyboardButton(
                    text="🏆 Clasificación",
                    callback_data="ranking",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👑 Diplomacia",
                    callback_data="diplomacy",
                ),
            ],
        ]
    )


def create_realm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚒ Fundar mi reino",
                    callback_data="create_realm",
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
                    callback_data="main_menu",
                )
            ]
        ]
    )

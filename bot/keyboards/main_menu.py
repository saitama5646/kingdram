from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


def persistent_menu_keyboard():
    """Teclado permanente con acceso directo a las pantallas del juego."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🏰 Reino"),
                KeyboardButton(text="⚔ Ejército"),
            ],
            [
                KeyboardButton(text="🏗 Edificios"),
                KeyboardButton(text="🔬 Investigaciones"),
            ],
            [
                KeyboardButton(text="📦 Recursos"),
                KeyboardButton(text="🗺 Territorios"),
            ],
            [
                KeyboardButton(text="🛡 Guerra"),
                KeyboardButton(text="🏆 Clasificación"),
            ],
            [
                KeyboardButton(text="👑 Diplomacia"),
                KeyboardButton(text="⌂ Menú principal"),
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
                    text="🏰 Mi reino",
                    callback_data="kingdom",
                ),
                InlineKeyboardButton(
                    text="📦 Recursos",
                    callback_data="economy",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏗 Edificios",
                    callback_data="buildings",
                ),
                InlineKeyboardButton(
                    text="🔬 Investigación",
                    callback_data="research",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚔ Ejército",
                    callback_data="army",
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
                    text="👑 Diplomacia",
                    callback_data="diplomacy",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Clasificación",
                    callback_data="ranking",
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

from aiogram.types import (
InlineKeyboardMarkup,
InlineKeyboardButton,
ReplyKeyboardMarkup,
KeyboardButton,
)

def persistent_menu_keyboard():
"""Teclado inferior permanente reducido a cuatro accesos."""
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
],
resize_keyboard=True,
is_persistent=True,
input_field_placeholder="¿Qué deseas administrar?",
)

def main_menu_keyboard():
"""Teclado emergente reducido a cuatro opciones."""
return InlineKeyboardMarkup(
inline_keyboard=[
[
InlineKeyboardButton(
text="⌂ Menú principal",
callback_data="main_menu",
)
],
[
InlineKeyboardButton(
text="⚔ Ejército",
callback_data="army",
),
InlineKeyboardButton(
text="🏗 Edificios",
callback_data="buildings",
),
],
[
InlineKeyboardButton(
text="🔬 Investigaciones",
callback_data="research",
)
],
]
)

def create_realm_keyboard():
"""Teclado para fundar un reino."""
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
"""Botón para regresar al menú principal."""
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

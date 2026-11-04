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
"""Teclado emergente reducido a las cuatro opciones principales."""
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

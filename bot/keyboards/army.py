from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.military import UNITS, QUANTITIES


def army_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Entrenar {unit['name']}",
                    callback_data=f"army:unit:{code}",
                )
            ]
            for code, unit in UNITS.items()
        ] + [
            [
                InlineKeyboardButton(
                    text="Actualizar",
                    callback_data="army",
                ),
                InlineKeyboardButton(
                    text="Menú principal",
                    callback_data="main_menu",
                ),
            ]
        ]
    )


def unit_keyboard(unit_type):
    unit = UNITS[unit_type]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Entrenar {quantity}",
                    callback_data=f"army:train:{unit_type}:{quantity}",
                )
            ]
            for quantity in QUANTITIES
        ] + [
            [
                InlineKeyboardButton(
                    text="Volver al ejército",
                    callback_data="army",
                )
            ]
        ]
    )

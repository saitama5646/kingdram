
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.construction import BUILDINGS


def buildings_keyboard():
    rows = []

    for building_type, building in BUILDINGS.items():
        rows.append([
            InlineKeyboardButton(
                text=f"{building['icon']} {building['name']}",
                callback_data=f"building:{building_type}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="↩ Menú principal",
            callback_data="main_menu"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def building_detail_keyboard(building_type):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬆ Mejorar edificio",
                    callback_data=f"upgrade:{building_type}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩ Volver a edificios",
                    callback_data="buildings"
                )
            ]
        ]
    )

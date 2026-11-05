
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from bot.services.construction import BUILDINGS


def buildings_keyboard(levels=None, pending_type=None):
    levels = levels or {}
    rows = []

    for building_type, building in BUILDINGS.items():
        level = levels.get(building_type, 0)

        if pending_type == building_type:
            status = " · ⏳ En cola"
        elif level > 0:
            status = f" · Nivel {level}"
        else:
            status = " · Construir"

        rows.append([
            InlineKeyboardButton(
                text=(
                    f"{building['icon']} "
                    f"{building['name']}{status}"
                ),
                callback_data=f"building:{building_type}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="↩ Menú principal",
            callback_data="main_menu",
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows,
    )


def building_detail_keyboard(
    building_type,
    level=0,
    pending=False,
):
    rows = []

    if level == 0:
        action = "⚒ Construir edificio"
    else:
        action = "⬆ Mejorar edificio"

    rows.append([
        InlineKeyboardButton(
            text=action,
            callback_data=f"upgrade:{building_type}",
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="↩ Volver a edificios",
            callback_data="buildings",
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="⌂ Menú principal",
            callback_data="main_menu",
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows,
    )

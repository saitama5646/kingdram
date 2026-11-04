
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.research import RESEARCH


def research_keyboard(levels=None, pending_type=None):
    levels = levels or {}
    rows = []

    branches = {}

    for key, research in RESEARCH.items():
        branches.setdefault(research["branch"], []).append(key)

    for branch, technologies in branches.items():
        rows.append([
            InlineKeyboardButton(
                text=f"━━ {branch.upper()} ━━",
                callback_data="research"
            )
        ])

        for key in technologies:
            research = RESEARCH[key]
            level = levels.get(key, 0)

            if pending_type == key:
                status = " · Investigando"
            else:
                status = f" · Nv. {level}"

            rows.append([
                InlineKeyboardButton(
                    text=f"{research['icon']} {research['name']}{status}",
                    callback_data=f"research:tech:{key}"
                )
            ])

    rows.extend([
        [
            InlineKeyboardButton(
                text="🔬 Cola de investigación",
                callback_data="research:queue"
            )
        ],
        [
            InlineKeyboardButton(
                text="↩ Menú principal",
                callback_data="main_menu"
            )
        ]
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def research_detail_keyboard(research_type, can_start, pending=False):
    rows = []

    if can_start and not pending:
        rows.append([
            InlineKeyboardButton(
                text="🔬 Investigar siguiente nivel",
                callback_data=f"research:start:{research_type}"
            )
        ])

    rows.extend([
        [
            InlineKeyboardButton(
                text="↩ Árbol tecnológico",
                callback_data="research"
            )
        ],
        [
            InlineKeyboardButton(
                text="⌂ Menú principal",
                callback_data="main_menu"
            )
        ]
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def research_queue_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩ Árbol tecnológico",
                    callback_data="research"
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

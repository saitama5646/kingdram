from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def battle_targets_keyboard(targets):
    rows = []

    for target in targets:
        rows.append([
            InlineKeyboardButton(
                text=(
                    f"🏰 {target['name']} "
                    f"· Poder {target['power']:,}"
                ),
                callback_data=f"battle:target:{target['id']}",
            )
        ])

    rows.extend([
        [
            InlineKeyboardButton(
                text="↩ Menú principal",
                callback_data="main_menu",
            )
        ],
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows,
    )


def battle_confirm_keyboard(realm_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔ Iniciar batalla",
                    callback_data=f"battle:confirm:{realm_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩ Cancelar",
                    callback_data="battle",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⌂ Menú principal",
                    callback_data="main_menu",
                )
            ],
        ]
    )


def battle_back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔ Buscar otro objetivo",
                    callback_data="battle",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏰 Mi ejército",
                    callback_data="army",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⌂ Menú principal",
                    callback_data="main_menu",
                )
            ],
        ]
    )

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
                text="🚩 Mis misiones",
                callback_data="missions",
            )
        ],
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
                    text="🪖 Seleccionar tropas",
                    callback_data=f"battle:prepare:{realm_id}",
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
                    text="🚩 Mis misiones",
                    callback_data="missions",
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


def mission_keyboard(missions):
    rows = []

    for mission in missions:
        if mission["status"] == "travelling":
            rows.append([
                InlineKeyboardButton(
                    text=f"↩ Retirar misión #{mission['id']}",
                    callback_data=f"mission:recall:{mission['id']}",
                )
            ])

    rows.extend([
        [
            InlineKeyboardButton(
                text="🔄 Actualizar",
                callback_data="missions",
            )
        ],
        [
            InlineKeyboardButton(
                text="⚔ Campañas militares",
                callback_data="battle",
            )
        ],
        [
            InlineKeyboardButton(
                text="⌂ Menú principal",
                callback_data="main_menu",
            )
        ],
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows,
    )

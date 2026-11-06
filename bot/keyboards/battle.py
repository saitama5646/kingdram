from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

UNIT_ORDER = (
    "spearman",
    "archer",
    "cavalry",
    "royal_guard",
)


def war_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Atacar desde el mapa", callback_data="world")],
        [InlineKeyboardButton(text="🚩 Expediciones activas", callback_data="missions")],
        [InlineKeyboardButton(text="📜 Resultados de batallas", callback_data="battle:history")],
        [InlineKeyboardButton(text="↩ Menú principal", callback_data="main_menu")],
    ])


def battle_targets_keyboard(targets):
    rows = []

    for target in targets:
        rows.append([
            InlineKeyboardButton(
                text=f"🏰 {target['name']} · Poder {target['power']:,}",
                callback_data=f"battle:target:{target['id']}",
            )
        ])

    rows.extend([
        [InlineKeyboardButton(text="🚩 Mis expediciones", callback_data="missions")],
        [InlineKeyboardButton(text="📜 Resultados anteriores", callback_data="battle:history")],
        [InlineKeyboardButton(text="↩ Menú de Guerra", callback_data="battle")],
        [InlineKeyboardButton(text="⌂ Menú principal", callback_data="main_menu")],
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def battle_confirm_keyboard(realm_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪖 Preparar ejército", callback_data=f"battle:prepare:{realm_id}")],
        [InlineKeyboardButton(text="↩ Cancelar", callback_data="battle")],
        [InlineKeyboardButton(text="⌂ Menú principal", callback_data="main_menu")],
    ])


def troop_selection_keyboard(quantities, available):
    rows = []

    for unit_type in UNIT_ORDER:
        quantity = int(quantities.get(unit_type, 0))
        maximum = int(available.get(unit_type, 0))

        rows.append([
            InlineKeyboardButton(
                text="−",
                callback_data=f"troops:change:{unit_type}:-1",
            ),
            InlineKeyboardButton(
                text=f"{quantity:,}".replace(",", "."),
                callback_data="troops:noop",
            ),
            InlineKeyboardButton(
                text="+",
                callback_data=f"troops:change:{unit_type}:1",
            ),
        ])

    rows.extend([
        [
            InlineKeyboardButton(
                text="✍️ Cantidades manuales",
                callback_data="troops:manual",
            )
        ],
        [
            InlineKeyboardButton(
                text="🚩 Enviar ejército",
                callback_data="troops:send",
            )
        ],
        [
            InlineKeyboardButton(
                text="↩ Cancelar",
                callback_data="troops:cancel",
            )
        ],
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def battle_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Volver al mapa", callback_data="world")],
        [InlineKeyboardButton(text="🚩 Mis expediciones", callback_data="missions")],
        [InlineKeyboardButton(text="📜 Resultados anteriores", callback_data="battle:history")],
        [InlineKeyboardButton(text="⚔ Menú de Guerra", callback_data="battle")],
        [InlineKeyboardButton(text="⌂ Menú principal", callback_data="main_menu")],
    ])


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
        [InlineKeyboardButton(text="🔄 Actualizar", callback_data="missions")],
        [InlineKeyboardButton(text="⚔ Menú de Guerra", callback_data="battle")],
        [InlineKeyboardButton(text="⌂ Menú principal", callback_data="main_menu")],
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def battle_history_keyboard(reports, offset, total):
    rows = []

    for report in reports:
        attacker_won = report["winner_realm_id"] == report["attacker_realm_id"]
        icon = "🏆" if attacker_won else "🛡"

        rows.append([
            InlineKeyboardButton(
                text=f"{icon} #{report['id']} {report['attacker_name']} vs {report['defender_name']}",
                callback_data=f"battle:report:{report['id']}",
            )
        ])

    navigation = []

    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅ Anterior",
                callback_data=f"battle:history:{max(0, offset - 10)}",
            )
        )

    if offset + 10 < total:
        navigation.append(
            InlineKeyboardButton(
                text="Siguiente ➡",
                callback_data=f"battle:history:{offset + 10}",
            )
        )

    if navigation:
        rows.append(navigation)

    rows.extend([
        [InlineKeyboardButton(text="⚔ Menú de Guerra", callback_data="battle")],
        [InlineKeyboardButton(text="⌂ Menú principal", callback_data="main_menu")],
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def battle_report_keyboard(battle_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Historial", callback_data="battle:history")],
        [InlineKeyboardButton(text="⚔ Menú de Guerra", callback_data="battle")],
        [InlineKeyboardButton(text="⌂ Menú principal", callback_data="main_menu")],
    ])

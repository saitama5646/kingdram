import json
from datetime import datetime, timezone
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot.database.connection import get_pool

from bot.services.battle import get_battle_targets
from bot.services.military import UNITS, get_military_data
from bot.services.missions import (
    create_mission,
    recall_mission,
    get_player_missions,
)

from bot.keyboards.battle import (
    battle_targets_keyboard,
    battle_confirm_keyboard,
    battle_back_keyboard,
    mission_keyboard,
    troop_selection_keyboard,
    war_menu_keyboard,
    battle_history_keyboard,
    battle_report_keyboard,
    UNIT_ORDER,
)

router = Router()


class MissionStates(StatesGroup):
    selecting_troops = State()
    manual_troops = State()


def number(value):
    return f"{int(value):,}".replace(",", ".")


def format_seconds(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


def format_remaining(value):
    if not value:
        return "Calculando..."

    seconds = max(
        0,
        int((value - datetime.now(timezone.utc)).total_seconds()),
    )

    return format_seconds(seconds)


async def render_troop_selection(message, state, edit=True):
    data = await state.get_data()

    quantities = data.get("troop_quantities", {})
    available = data.get("troop_available", {})

    total_selected = sum(
        int(quantities.get(unit_type, 0))
        for unit_type in UNIT_ORDER
    )

    lines = [
        "🛡️ <b>PREPARACIÓN DEL EJÉRCITO</b>",
        "",
        "Selecciona las tropas que formarán tu expedición.",
        "",
    ]

    for unit_type in UNIT_ORDER:
        unit = UNITS[unit_type]
        quantity = int(quantities.get(unit_type, 0))
        maximum = int(available.get(unit_type, 0))

        lines.extend([
            f"{unit['emoji']} <b>{unit['name']}</b>",
            f"Seleccionadas: <b>{number(quantity)}</b> / {number(maximum)} disponibles",
            "",
        ])

    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        f"🪖 Total seleccionado: <b>{number(total_selected)}</b> unidades",
        "",
        "Utiliza los botones para modificar las cantidades.",
        "También puedes introducirlas manualmente.",
    ])

    text = "\n".join(lines)
    keyboard = troop_selection_keyboard(quantities, available)

    if edit:
        await message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


async def send_selected_army(user_id, state, message):
    data = await state.get_data()

    defender_realm_id = data.get("defender_realm_id")
    quantities = data.get("troop_quantities", {})

    troops = {
        unit_type: int(quantities.get(unit_type, 0))
        for unit_type in UNIT_ORDER
    }

    if sum(troops.values()) <= 0:
        await message.answer("Debes seleccionar al menos una unidad.")
        return

    success, result = await create_mission(
        user_id,
        defender_realm_id,
        troops,
    )

    if not success:
        await message.answer(
            "⚠️ <b>No se pudo iniciar la expedición</b>\n\n"
            f"{escape(str(result))}",
            parse_mode="HTML",
        )
        return

    await state.clear()

    lines = [
        "🏰 <b>EXPEDICIÓN MILITAR INICIADA</b>",
        "",
        f"🆔 Misión: <b>#{result['mission_id']}</b>",
        f"🏰 Objetivo: <b>{escape(result['defender_name'])}</b>",
        "",
        "🪖 <b>EJÉRCITO ENVIADO</b>",
    ]

    for unit_type, quantity in troops.items():
        if quantity <= 0:
            continue

        unit = UNITS[unit_type]
        lines.append(
            f"{unit['emoji']} {unit['name']}: <b>{number(quantity)}</b>"
        )

    lines.extend([
        "",
        f"📏 Distancia: <b>{number(result['distance'])}</b>",
        f"⏳ Tiempo de viaje: <b>{format_seconds(result['travel_seconds'])}</b>",
        "",
        "Puedes consultar tus expediciones y retirar las tropas mientras viajan.",
    ])

    await message.answer(
        "\n".join(lines),
        reply_markup=battle_back_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "battle")
async def war_menu(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "⚔ <b>GUERRA</b>\n\n"
        "Administra tus campañas militares, consulta las expediciones "
        "en curso y revisa los informes de batallas anteriores.\n\n"
        "📜 Los resultados quedan registrados para que puedas estudiar "
        "tus victorias y derrotas.",
        reply_markup=war_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "battle:campaigns")
async def open_campaigns(callback: CallbackQuery):
    await callback.answer()

    data = await get_battle_targets(callback.from_user.id)

    if not data:
        await callback.message.edit_text(
            "Primero debes fundar un reino.",
            reply_markup=war_menu_keyboard(),
        )
        return

    targets = data["targets"]

    if not targets:
        await callback.message.edit_text(
            "⚔ <b>CAMPAÑAS MILITARES</b>\n\n"
            "No hay reinos disponibles como objetivo.",
            reply_markup=war_menu_keyboard(),
            parse_mode="HTML",
        )
        return

    await callback.message.edit_text(
        "⚔ <b>CAMPAÑAS MILITARES</b>\n\n"
        "Selecciona un reino para preparar una expedición militar.\n\n"
        "Las tropas viajarán según la distancia y la velocidad "
        "de la unidad más lenta.",
        reply_markup=battle_targets_keyboard(targets),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("battle:target:"))
async def battle_target(callback: CallbackQuery):
    try:
        realm_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Objetivo no válido.", show_alert=True)
        return

    data = await get_battle_targets(callback.from_user.id)

    if not data:
        await callback.answer("No tienes un reino.", show_alert=True)
        return

    target = next(
        (item for item in data["targets"] if item["id"] == realm_id),
        None,
    )

    if not target:
        await callback.answer(
            "Este objetivo ya no está disponible.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "⚔ <b>PREPARAR CAMPAÑA</b>\n\n"
        f"🏰 Objetivo: <b>{escape(target['name'])}</b>\n"
        f"Nivel: {target['level']}\n"
        f"Poder general: {number(target['power'])}\n\n"
        "Elige exactamente cuántas unidades deseas enviar.\n"
        "Las tropas enviadas dejarán de estar disponibles "
        "en tu ejército mientras estén en misión.",
        reply_markup=battle_confirm_keyboard(realm_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("battle:prepare:"))
async def prepare_mission(callback: CallbackQuery, state: FSMContext):
    try:
        realm_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Objetivo no válido.", show_alert=True)
        return

    data = await get_military_data(callback.from_user.id)

    if not data:
        await callback.answer("Primero funda un reino.", show_alert=True)
        return

    available = {
        row["unit_type"]: int(row["quantity"])
        for row in data["troops"]
    }

    quantities = {
        unit_type: 0
        for unit_type in UNIT_ORDER
    }

    await state.clear()
    await state.set_state(MissionStates.selecting_troops)

    await state.update_data(
        defender_realm_id=realm_id,
        troop_available=available,
        troop_quantities=quantities,
    )

    await callback.answer()
    await render_troop_selection(callback.message, state)


@router.callback_query(
    MissionStates.selecting_troops,
    F.data == "troops:noop",
)
async def troop_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(
    MissionStates.selecting_troops,
    F.data.startswith("troops:change:"),
)
async def change_troop_quantity(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer("Selección no válida.", show_alert=True)
        return

    unit_type = parts[2]

    try:
        amount = int(parts[3])
    except ValueError:
        await callback.answer("Cantidad no válida.", show_alert=True)
        return

    if unit_type not in UNIT_ORDER:
        await callback.answer("Unidad no válida.", show_alert=True)
        return

    data = await state.get_data()

    quantities = dict(data.get("troop_quantities", {}))
    available = data.get("troop_available", {})

    current = int(quantities.get(unit_type, 0))
    maximum = int(available.get(unit_type, 0))

    updated = max(0, min(maximum, current + amount))
    quantities[unit_type] = updated

    await state.update_data(troop_quantities=quantities)

    await callback.answer(
        f"{UNITS[unit_type]['name']}: {number(updated)}"
    )

    await render_troop_selection(callback.message, state)


@router.callback_query(
    MissionStates.selecting_troops,
    F.data.startswith("troops:max:"),
)
async def troop_maximum(callback: CallbackQuery, state: FSMContext):
    unit_type = callback.data.split(":")[2]

    if unit_type not in UNIT_ORDER:
        await callback.answer("Unidad no válida.", show_alert=True)
        return

    data = await state.get_data()

    quantities = dict(data.get("troop_quantities", {}))
    available = data.get("troop_available", {})

    quantities[unit_type] = int(available.get(unit_type, 0))

    await state.update_data(troop_quantities=quantities)

    await callback.answer(f"{UNITS[unit_type]['name']}: máximo")
    await render_troop_selection(callback.message, state)


@router.callback_query(
    MissionStates.selecting_troops,
    F.data == "troops:manual",
)
async def manual_troop_selection(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MissionStates.manual_troops)
    await callback.answer()

    await callback.message.edit_text(
        "✍️ <b>SELECCIÓN MANUAL DEL EJÉRCITO</b>\n\n"
        "Escribe cuatro números separados por espacios, en este orden:\n\n"
        "Lancero · Arquero · Caballería · Guardia real\n\n"
        "<b>Ejemplo:</b>\n"
        "<code>20 10 3 1</code>\n\n"
        "Puedes escribir 0 para las unidades que no quieras enviar.\n"
        "Escribe <code>cancelar</code> para volver.",
        parse_mode="HTML",
    )


@router.message(MissionStates.manual_troops)
async def receive_manual_troops(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()

    if text == "cancelar":
        await state.set_state(MissionStates.selecting_troops)
        await message.answer("Selección manual cancelada.")
        await render_troop_selection(message, state, edit=False)
        return

    parts = text.split()

    if len(parts) != 4:
        await message.answer(
            "Debes escribir exactamente cuatro números.\n"
            "Ejemplo: <code>20 10 3 1</code>",
            parse_mode="HTML",
        )
        return

    try:
        values = [int(value) for value in parts]
    except ValueError:
        await message.answer("Todos los valores deben ser números enteros.")
        return

    if any(value < 0 for value in values):
        await message.answer("No puedes enviar cantidades negativas.")
        return

    data = await state.get_data()
    available = data.get("troop_available", {})

    for index, unit_type in enumerate(UNIT_ORDER):
        maximum = int(available.get(unit_type, 0))

        if values[index] > maximum:
            await message.answer(
                f"No tienes suficientes {UNITS[unit_type]['name']}.\n"
                f"Disponibles: {number(maximum)}\n"
                f"Seleccionados: {number(values[index])}"
            )
            return

    if sum(values) <= 0:
        await message.answer("Debes seleccionar al menos una unidad.")
        return

    selected = {
        unit_type: values[index]
        for index, unit_type in enumerate(UNIT_ORDER)
    }

    await state.update_data(troop_quantities=selected)
    await state.set_state(MissionStates.selecting_troops)

    await message.answer("Cantidades manuales cargadas.")
    await render_troop_selection(message, state, edit=False)


@router.callback_query(
    MissionStates.selecting_troops,
    F.data == "troops:send",
)
async def send_troops_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await send_selected_army(
        callback.from_user.id,
        state,
        callback.message,
    )


@router.callback_query(
    MissionStates.selecting_troops,
    F.data == "troops:cancel",
)
async def cancel_troop_selection(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Expedición cancelada.")

    await callback.message.edit_text(
        "Preparación de la expedición cancelada.",
        reply_markup=battle_back_keyboard(),
    )


@router.message(MissionStates.selecting_troops)
async def receive_troop_selection(message: Message):
    text = (message.text or "").strip().lower()

    if text == "cancelar":
        await message.answer("Utiliza el botón de cancelar la expedición.")
        return

    await message.answer(
        "La selección se realiza con los botones del panel.\n"
        "Pulsa «Introducir cantidades manualmente» si deseas escribirlas."
    )


@router.callback_query(F.data == "missions")
async def missions_menu(callback: CallbackQuery):
    missions = await get_player_missions(callback.from_user.id)

    await callback.answer()

    if not missions:
        await callback.message.edit_text(
            "🚩 <b>MI EJÉRCITO EN MISIÓN</b>\n\n"
            "No tienes expediciones militares activas.",
            reply_markup=mission_keyboard([]),
            parse_mode="HTML",
        )
        return

    lines = [
        "🚩 <b>MI EJÉRCITO EN MISIÓN</b>",
        "",
    ]

    for mission in missions:
        status = {
            "travelling": "🏇 En camino",
            "battling": "⚔️ En combate",
            "returning": "↩️ Regresando",
        }.get(mission["status"], mission["status"])

        lines.extend([
            f"🆔 <b>Misión #{mission['id']}</b>",
            f"🏰 Objetivo: <b>{escape(mission['defender_name'])}</b>",
            f"Estado: {status}",
            f"📏 Distancia: {number(mission['distance'])}",
            f"⏳ Tiempo restante: <b>{format_remaining(mission['arrival_at'])}</b>",
            "",
        ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=mission_keyboard(missions),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mission:recall:"))
async def recall_callback(callback: CallbackQuery):
    try:
        mission_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Misión no válida.", show_alert=True)
        return

    success, result = await recall_mission(
        callback.from_user.id,
        mission_id,
    )

    if not success:
        await callback.answer(result, show_alert=True)
        return

    await callback.answer("Retirada ordenada.")

    await callback.message.edit_text(
        "↩️ <b>RETIRADA ORDENADA</b>\n\n"
        f"Misión: <b>#{result['mission_id']}</b>\n"
        "Las tropas están regresando a tu reino.\n\n"
        "⏳ Tiempo estimado de retorno: "
        f"<b>{format_seconds(result['return_seconds'])}</b>",
        reply_markup=battle_back_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "battle:history")
@router.callback_query(F.data.startswith("battle:history:"))
async def battle_history_handler(callback: CallbackQuery):
    try:
        offset = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        offset = 0

    offset = max(0, offset)
    user_id = callback.from_user.id

    pool = await get_pool()

    async with pool.acquire() as connection:
        total = await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM battle_reports
            WHERE attacker_owner_id = $1
               OR defender_owner_id = $1
            """,
            user_id,
        )

        reports = await connection.fetch(
            """
            SELECT
                br.id,
                br.created_at,
                br.attacker_realm_id,
                br.defender_realm_id,
                br.winner_realm_id,
                a.name AS attacker_name,
                d.name AS defender_name
            FROM battle_reports br
            JOIN realms a ON a.id = br.attacker_realm_id
            JOIN realms d ON d.id = br.defender_realm_id
            WHERE br.attacker_owner_id = $1
               OR br.defender_owner_id = $1
            ORDER BY br.created_at DESC, br.id DESC
            LIMIT 10 OFFSET $2
            """,
            user_id,
            offset,
        )

    await callback.answer()

    if not reports:
        await callback.message.edit_text(
            "📜 <b>HISTORIAL DE BATALLAS</b>\n\n"
            "Todavía no tienes batallas registradas.\n\n"
            "Cuando participes en un combate, su informe aparecerá aquí.",
            reply_markup=war_menu_keyboard(),
            parse_mode="HTML",
        )
        return

    text = (
        "📜 <b>HISTORIAL DE BATALLAS</b>\n\n"
        f"⚔ Combates registrados: <b>{number(total)}</b>\n\n"
        "Selecciona una batalla para abrir su informe detallado."
    )

    await callback.message.edit_text(
        text,
        reply_markup=battle_history_keyboard(reports, offset, total),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("battle:report:"))
async def battle_report_handler(callback: CallbackQuery):
    try:
        battle_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Informe no válido.", show_alert=True)
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        report = await connection.fetchrow(
            """
            SELECT
                br.*,
                a.name AS attacker_name,
                d.name AS defender_name
            FROM battle_reports br
            JOIN realms a ON a.id = br.attacker_realm_id
            JOIN realms d ON d.id = br.defender_realm_id
            WHERE br.id = $1
              AND (
                  br.attacker_owner_id = $2
                  OR br.defender_owner_id = $2
              )
            """,
            battle_id,
            callback.from_user.id,
        )

        if not report:
            await callback.answer(
                "El informe no existe o no te pertenece.",
                show_alert=True,
            )
            return

        units = await connection.fetch(
            """
            SELECT
                realm_id,
                unit_type,
                initial_quantity,
                lost_quantity,
                remaining_quantity
            FROM battle_unit_results
            WHERE battle_id = $1
            ORDER BY realm_id, unit_type
            """,
            battle_id,
        )

    await callback.answer()

    outcome = report["outcome"]

    if outcome == "attacker_victory":
        result_title = (
            f"🏆 <b>VICTORIA: "
            f"{escape(report['attacker_name'])}</b>"
        )
    elif outcome == "defender_victory":
        result_title = (
            f"🛡 <b>DEFENSA EXITOSA: "
            f"{escape(report['defender_name'])}</b>"
        )
    elif outcome == "inconclusive":
        result_title = "⚖️ <b>COMBATE INCONCLUSO</b>"
    elif outcome == "mutual_destruction":
        result_title = "☠️ <b>ANIQUILACIÓN MUTUA</b>"
    else:
        result_title = "⚔️ <b>RESULTADO DEL COMBATE</b>"

    date_text = report["created_at"].strftime("%d/%m/%Y %H:%M")

    attacker_morale = float(report["attacker_morale"] or 1)
    defender_morale = float(report["defender_morale"] or 1)

    lines = [
        f"📜 <b>INFORME DE BATALLA #{report['id']}</b>",
        "",
        f"📅 Fecha: <b>{date_text}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        result_title,
        f"🔁 Rondas disputadas: <b>{number(report['rounds'])}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "⚔ <b>FUERZAS ENFRENTADAS</b>",
        "",
        f"🏰 Atacante: <b>{escape(report['attacker_name'])}</b>",
        f"⚔ Poder ofensivo: <b>{number(report['attacker_power'])}</b>",
        f"💀 Bajas: <b>{number(report['attacker_losses'])}</b>",
        f"🧭 Moral final: <b>{attacker_morale * 100:.1f}%</b>",
        "",
        f"🛡 Defensor: <b>{escape(report['defender_name'])}</b>",
        f"🛡 Poder defensivo: <b>{number(report['defender_power'])}</b>",
        f"💀 Bajas: <b>{number(report['defender_losses'])}</b>",
        f"🧭 Moral final: <b>{defender_morale * 100:.1f}%</b>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🪖 <b>DETALLE DE UNIDADES</b>",
        "",
    ]

    realms = [
        (report["attacker_realm_id"], report["attacker_name"]),
        (report["defender_realm_id"], report["defender_name"]),
    ]

    for realm_id, realm_name in realms:
        realm_units = [
            unit for unit in units
            if unit["realm_id"] == realm_id
        ]

        lines.extend([
            f"🏰 <b>{escape(realm_name)}</b>",
            "",
        ])

        if not realm_units:
            lines.extend(["No se registraron unidades.", ""])
            continue

        for result in realm_units:
            unit = UNITS.get(result["unit_type"])

            unit_name = unit["name"] if unit else result["unit_type"]
            emoji = unit["emoji"] if unit else "🪖"

            lines.extend([
                f"{emoji} <b>{escape(unit_name)}</b>",
                f"Iniciales: {number(result['initial_quantity'])}",
                f"Bajas: {number(result['lost_quantity'])}",
                f"Supervivientes: {number(result['remaining_quantity'])}",
                "",
            ])

    damage = float(report["infrastructure_damage"] or 0) * 100

    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        "🏰 <b>DAÑOS AL REINO</b>",
        "",
        f"📉 Infraestructura dañada: <b>{damage:.1f}%</b>",
    ])

    if report["vassalage_unlocked"]:
        lines.extend([
            "",
            "👑 <b>Se ha desbloqueado la posibilidad de someter al reino derrotado.</b>",
        ])

    round_log = report["round_log"] or []

    if isinstance(round_log, str):
        try:
            round_log = json.loads(round_log)
        except (TypeError, ValueError):
            round_log = []

    if round_log:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            "📖 <b>DESARROLLO DEL COMBATE</b>",
            "",
        ])

        for entry in round_log:
            lines.extend([
                f"<b>Ronda {number(entry.get('round', 0))}</b>",
                (
                    "⚔ Daño atacante: "
                    f"{number(round(entry.get('attacker_damage', 0)))}"
                ),
                (
                    "🛡 Daño defensor: "
                    f"{number(round(entry.get('defender_damage', 0)))}"
                ),
                (
                    "💀 Bajas atacante: "
                    f"{number(entry.get('attacker_losses', 0))}"
                ),
                (
                    "💀 Bajas defensor: "
                    f"{number(entry.get('defender_losses', 0))}"
                ),
                (
                    "🪖 Tropas atacantes restantes: "
                    f"{number(entry.get('attacker_remaining', 0))}"
                ),
                (
                    "🪖 Tropas defensoras restantes: "
                    f"{number(entry.get('defender_remaining', 0))}"
                ),
                "",
            ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=battle_report_keyboard(report["id"]),
        parse_mode="HTML",
    )

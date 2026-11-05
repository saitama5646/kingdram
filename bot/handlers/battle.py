from datetime import datetime, timezone
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

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
UNIT_ORDER,
)

router = Router()

class MissionStates(StatesGroup):
selecting_troops = State()
manual_troops = State()

def number(value):
return f"{int(value):,}".replace(",", ".")

def format_remaining(value):
if not value:
return "Calculando..."

seconds = max(
    0,
    int(
        (
            value - datetime.now(timezone.utc)
        ).total_seconds()
    ),
)

hours, remainder = divmod(seconds, 3600)
minutes, seconds = divmod(remainder, 60)

if hours:
    return f"{hours}h {minutes}m"

if minutes:
    return f"{minutes}m {seconds}s"

return f"{seconds}s"

def format_seconds(seconds):
seconds = max(0, int(seconds))

hours, remainder = divmod(seconds, 3600)
minutes, seconds = divmod(remainder, 60)

if hours:
    return f"{hours}h {minutes}m {seconds}s"

if minutes:
    return f"{minutes}m {seconds}s"

return f"{seconds}s"

async def render_troop_selection(
message,
state,
):
data = await state.get_data()

quantities = data.get(
    "troop_quantities",
    {},
)

available = data.get(
    "troop_available",
    {},
)

total_selected = sum(
    int(quantities.get(unit_type, 0))
    for unit_type in UNIT_ORDER
)

lines = [
    "🛡️ <b>PREPARACIÓN DEL EJÉRCITO</b>",
    "",
    "Selecciona las tropas que formarán",
    "tu expedición militar.",
    "",
]

for unit_type in UNIT_ORDER:
    unit = UNITS[unit_type]

    quantity = int(
        quantities.get(unit_type, 0)
    )

    maximum = int(
        available.get(unit_type, 0)
    )

    lines.extend([
        (
            f"{unit['emoji']} <b>{unit['name']}</b>"
        ),
        (
            f"Seleccionadas: <b>{number(quantity)}</b>"
            f" / {number(maximum)} disponibles"
        ),
        "",
    ])

lines.extend([
    "━━━━━━━━━━━━━━━━━━",
    (
        f"🪖 Total seleccionado: "
        f"<b>{number(total_selected)}</b> unidades"
    ),
    "",
    "Usa los botones para modificar las cantidades.",
    "También puedes introducirlas manualmente.",
])

await message.edit_text(
    "\n".join(lines),
    reply_markup=troop_selection_keyboard(
        quantities,
        available,
    ),
    parse_mode="HTML",
)

async def send_selected_army(
user_id,
state,
message,
):
data = await state.get_data()

defender_realm_id = data.get(
    "defender_realm_id"
)

quantities = data.get(
    "troop_quantities",
    {},
)

troops = {
    unit_type: int(
        quantities.get(unit_type, 0)
    )
    for unit_type in UNIT_ORDER
}

if sum(troops.values()) <= 0:
    await message.answer(
        "Debes seleccionar al menos una unidad."
    )
    return

success, result = await create_mission(
    user_id,
    defender_realm_id,
    troops,
)

if not success:
    await message.answer(
        "⚠️ <b>No se pudo iniciar la expedición</b>\n\n"
        f"{escape(result)}",
        parse_mode="HTML",
    )
    return

await state.clear()

lines = [
    "🏰 <b>EXPEDICIÓN MILITAR INICIADA</b>",
    "",
    f"🆔 Misión: <b>#{result['mission_id']}</b>",
    (
        f"🏰 Objetivo: "
        f"<b>{escape(result['defender_name'])}</b>"
    ),
    "",
    "🪖 <b>EJÉRCITO ENVIADO</b>",
]

for unit_type, quantity in troops.items():
    if quantity <= 0:
        continue

    unit = UNITS[unit_type]

    lines.append(
        f"{unit['emoji']} {unit['name']}: "
        f"<b>{number(quantity)}</b>"
    )

lines.extend([
    "",
    f"📏 Distancia: <b>{number(result['distance'])}</b>",
    (
        "⏳ Tiempo de viaje: "
        f"<b>{format_seconds(result['travel_seconds'])}</b>"
    ),
    "",
    "Puedes consultar tus expediciones militares",
    "y retirar las tropas mientras viajan.",
])

await message.answer(
    "\n".join(lines),
    reply_markup=battle_back_keyboard(),
    parse_mode="HTML",
)

@router.callback_query(F.data == "battle")
async def battle_menu(callback: CallbackQuery):
data = await get_battle_targets(
callback.from_user.id
)

if not data:
    await callback.answer(
        "Primero debes fundar un reino.",
        show_alert=True,
    )
    return

await callback.answer()

targets = data["targets"]

if not targets:
    await callback.message.edit_text(
        "⚔ <b>CAMPAÑAS MILITARES</b>\n\n"
        "No hay otros reinos disponibles como objetivo.",
        parse_mode="HTML",
    )
    return

await callback.message.edit_text(
    "⚔ <b>CAMPAÑAS MILITARES</b>\n\n"
    "Selecciona un reino para preparar una expedición.\n\n"
    "Las tropas viajarán según la distancia del mapa "
    "y la velocidad de la unidad más lenta.",
    reply_markup=battle_targets_keyboard(targets),
    parse_mode="HTML",
)

@router.callback_query(F.data.startswith("battle:target:"))
async def battle_target(callback: CallbackQuery):
try:
realm_id = int(
callback.data.split(":")[2]
)
except (ValueError, IndexError):
await callback.answer(
"Objetivo no válido.",
show_alert=True,
)
return

data = await get_battle_targets(
    callback.from_user.id
)

if not data:
    await callback.answer(
        "No tienes un reino.",
        show_alert=True,
    )
    return

target = next(
    (
        item for item in data["targets"]
        if item["id"] == realm_id
    ),
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
async def prepare_mission(
callback: CallbackQuery,
state: FSMContext,
):
try:
realm_id = int(
callback.data.split(":")[2]
)
except (ValueError, IndexError):
await callback.answer(
"Objetivo no válido.",
show_alert=True,
)
return

data = await get_military_data(
    callback.from_user.id
)

if not data:
    await callback.answer(
        "Primero funda un reino.",
        show_alert=True,
    )
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

await state.set_state(
    MissionStates.selecting_troops
)

await state.update_data(
    defender_realm_id=realm_id,
    troop_available=available,
    troop_quantities=quantities,
)

await callback.answer()

await render_troop_selection(
    callback.message,
    state,
)

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
async def change_troop_quantity(
callback: CallbackQuery,
state: FSMContext,
):
parts = callback.data.split(":")

if len(parts) != 4:
    await callback.answer(
        "Selección no válida.",
        show_alert=True,
    )
    return

unit_type = parts[2]

try:
    amount = int(parts[3])
except ValueError:
    await callback.answer(
        "Cantidad no válida.",
        show_alert=True,
    )
    return

if unit_type not in UNIT_ORDER:
    await callback.answer(
        "Unidad no válida.",
        show_alert=True,
    )
    return

data = await state.get_data()

quantities = dict(
    data.get("troop_quantities", {})
)

available = data.get(
    "troop_available",
    {},
)

current = int(
    quantities.get(unit_type, 0)
)

maximum = int(
    available.get(unit_type, 0)
)

updated = max(
    0,
    min(maximum, current + amount),
)

quantities[unit_type] = updated

await state.update_data(
    troop_quantities=quantities,
)

await callback.answer(
    f"{UNITS[unit_type]['name']}: {updated}"
)

await render_troop_selection(
    callback.message,
    state,
)

@router.callback_query(
MissionStates.selecting_troops,
F.data.startswith("troops:max:"),
)
async def troop_maximum(
callback: CallbackQuery,
state: FSMContext,
):
unit_type = callback.data.split(":")[2]

if unit_type not in UNIT_ORDER:
    await callback.answer(
        "Unidad no válida.",
        show_alert=True,
    )
    return

data = await state.get_data()

quantities = dict(
    data.get("troop_quantities", {})
)

available = data.get(
    "troop_available",
    {},
)

quantities[unit_type] = int(
    available.get(unit_type, 0)
)

await state.update_data(
    troop_quantities=quantities,
)

await callback.answer(
    f"{UNITS[unit_type]['name']}: máximo"
)

await render_troop_selection(
    callback.message,
    state,
)

@router.callback_query(
MissionStates.selecting_troops,
F.data == "troops:manual",
)
async def manual_troop_selection(
callback: CallbackQuery,
state: FSMContext,
):
await state.set_state(
MissionStates.manual_troops
)

await callback.answer()

await callback.message.edit_text(
    "✍️ <b>SELECCIÓN MANUAL DEL EJÉRCITO</b>\n\n"
    "Escribe cuatro números separados por espacios,\n"
    "en este orden:\n\n"
    "Lancero · Arquero · Caballería · Guardia real\n\n"
    "<b>Ejemplo:</b>\n"
    "<code>20 10 3 1</code>\n\n"
    "Puedes escribir <code>0</code> para una unidad "
    "que no quieras enviar.\n\n"
    "Escribe <code>cancelar</code> para volver.",
    parse_mode="HTML",
)

@router.message(MissionStates.manual_troops)
async def receive_manual_troops(
message: Message,
state: FSMContext,
):
text = (message.text or "").strip().lower()

if text == "cancelar":
    await state.set_state(
        MissionStates.selecting_troops
    )

    await render_troop_selection(
        await state.get_data_message(message),
        state,
    )
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
    quantities = [
        int(value)
        for value in parts
    ]
except ValueError:
    await message.answer(
        "Todos los valores deben ser números enteros."
    )
    return

if any(value < 0 for value in quantities):
    await message.answer(
        "No puedes enviar cantidades negativas."
    )
    return

data = await state.get_data()

available = data.get(
    "troop_available",
    {},
)

for index, unit_type in enumerate(UNIT_ORDER):
    maximum = int(
        available.get(unit_type, 0)
    )

    if quantities[index] > maximum:
        await message.answer(
            f"No tienes suficientes "
            f"{UNITS[unit_type]['name']}.\n"
            f"Disponibles: {number(maximum)}\n"
            f"Seleccionados: {number(quantities[index])}"
        )
        return

if sum(quantities) <= 0:
    await message.answer(
        "Debes seleccionar al menos una unidad."
    )
    return

selected = {
    unit_type: quantities[index]
    for index, unit_type in enumerate(UNIT_ORDER)
}

await state.update_data(
    troop_quantities=selected,
)

await state.set_state(
    MissionStates.selecting_troops
)

await message.answer(
    "Cantidades manuales cargadas."
)

await render_troop_selection(
    message,
    state,
)

@router.callback_query(
MissionStates.selecting_troops,
F.data == "troops:send",
)
async def send_troops_callback(
callback: CallbackQuery,
state: FSMContext,
):
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
async def cancel_troop_selection(
callback: CallbackQuery,
state: FSMContext,
):
await state.clear()

await callback.answer(
    "Expedición cancelada."
)

await callback.message.edit_text(
    "Preparación de la expedición cancelada.",
    reply_markup=battle_back_keyboard(),
)

@router.message(MissionStates.selecting_troops)
async def receive_troop_selection(
message: Message,
state: FSMContext,
):
text = (message.text or "").strip().lower()

if text == "cancelar":
    await state.clear()

    await message.answer(
        "Selección cancelada."
    )
    return

await message.answer(
    "La selección se realiza con los botones del panel.\n"
    "Pulsa «Introducir cantidades manualmente» "
    "si deseas escribirlas."
)

@router.callback_query(F.data == "missions")
async def missions_menu(callback: CallbackQuery):
missions = await get_player_missions(
callback.from_user.id
)

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
    }.get(
        mission["status"],
        mission["status"],
    )

    lines.extend([
        f"🆔 <b>Misión #{mission['id']}</b>",
        (
            f"🏰 Objetivo: "
            f"<b>{escape(mission['defender_name'])}</b>"
        ),
        f"Estado: {status}",
        (
            "📏 Distancia: "
            f"{number(mission['distance'])}"
        ),
        (
            "⏳ Tiempo restante: "
            f"<b>{format_remaining(mission['arrival_at'])}</b>"
        ),
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
mission_id = int(
callback.data.split(":")[2]
)
except (ValueError, IndexError):
await callback.answer(
"Misión no válida.",
show_alert=True,
)
return

success, result = await recall_mission(
    callback.from_user.id,
    mission_id,
)

if not success:
    await callback.answer(
        result,
        show_alert=True,
    )
    return

await callback.answer(
    "Retirada ordenada."
)

await callback.message.edit_text(
    "↩️ <b>RETIRADA ORDENADA</b>\n\n"
    f"Misión: <b>#{result['mission_id']}</b>\n"
    "Las tropas están regresando a tu reino.\n\n"
    "⏳ Tiempo estimado de retorno: "
    f"<b>{format_seconds(result['return_seconds'])}</b>",
    reply_markup=battle_back_keyboard(),
    parse_mode="HTML",
)

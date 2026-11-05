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
)


router = Router()


class MissionStates(StatesGroup):
    selecting_troops = State()


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

    await state.set_state(
        MissionStates.selecting_troops
    )

    await state.update_data(
        defender_realm_id=realm_id,
    )

    lines = [
        "🪖 <b>SELECCIÓN MANUAL DEL EJÉRCITO</b>",
        "",
        "Escribe cuatro números separados por espacios,",
        "en este orden:",
        "",
    ]

    for unit_type in (
        "spearman",
        "archer",
        "cavalry",
        "royal_guard",
    ):
        unit = UNITS[unit_type]

        lines.append(
            f"{unit['emoji']} {unit['name']}: "
            f"<b>{available.get(unit_type, 0)}</b> disponibles"
        )

    lines.extend([
        "",
        "<b>Orden:</b>",
        "Lancero · Arquero · Caballería · Guardia real",
        "",
        "<b>Ejemplo:</b>",
        "<code>20 10 3 1</code>",
        "",
        "Puedes enviar cantidades exactas. "
        "No tienes que enviar todo tu ejército.",
        "",
        "Escribe <code>0</code> para no enviar "
        "una unidad de ese tipo.",
        "",
        "Escribe <code>cancelar</code> para abortar.",
    ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
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

    if sum(quantities) <= 0:
        await message.answer(
            "Debes seleccionar al menos una unidad."
        )
        return

    state_data = await state.get_data()

    defender_realm_id = state_data.get(
        "defender_realm_id"
    )

    troops = {
        "spearman": quantities[0],
        "archer": quantities[1],
        "cavalry": quantities[2],
        "royal_guard": quantities[3],
    }

    success, result = await create_mission(
        message.from_user.id,
        defender_realm_id,
        troops,
    )

    if not success:
        await message.answer(
            f"⚠️ <b>No se pudo iniciar la misión</b>\n\n"
            f"{escape(result)}",
            parse_mode="HTML",
        )
        return

    await state.clear()

    lines = [
        "🚩 <b>EXPEDICIÓN INICIADA</b>",
        "",
        f"🆔 Misión: <b>#{result['mission_id']}</b>",
        f"🏰 Objetivo: <b>{escape(result['defender_name'])}</b>",
        "",
        "🪖 <b>TROPAS ENVIADAS</b>",
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
        "Puedes consultar tus misiones y retirar "
        "las tropas mientras estén viajando.",
    ])

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=battle_back_keyboard(),
    )


def format_seconds(seconds):
    seconds = max(0, int(seconds))

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


@router.callback_query(F.data == "missions")
async def missions_menu(callback: CallbackQuery):
    missions = await get_player_missions(
        callback.from_user.id
    )

    await callback.answer()

    if not missions:
        await callback.message.edit_text(
            "🚩 <b>MI FLOTA EN MISIÓN</b>\n\n"
            "No tienes misiones militares activas.",
            reply_markup=mission_keyboard([]),
            parse_mode="HTML",
        )
        return

    lines = [
        "🚩 <b>MI FLOTA EN MISIÓN</b>",
        "",
    ]

    for mission in missions:
        status = {
            "travelling": "🚀 En camino",
            "battling": "⚔️ En combate",
            "returning": "↩️ Regresando",
        }.get(
            mission["status"],
            mission["status"],
        )

        lines.extend([
            (
                f"🆔 <b>Misión #{mission['id']}</b>"
            ),
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

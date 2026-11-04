
from datetime import datetime, timezone
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.services.military import (
    UNITS,
    RESOURCE_LABELS,
    format_costs,
    get_military_data,
    start_training,
)

from bot.keyboards.army import (
    army_keyboard,
    unit_keyboard,
)


router = Router()


def format_time(value):
    seconds = max(0, int(value.total_seconds()))

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


async def render_army(callback: CallbackQuery):
    data = await get_military_data(
        callback.from_user.id
    )

    if not data:
        await callback.message.edit_text(
            "🏰 <b>No tienes un reino todavía.</b>\n\n"
            "Funda tu reino antes de reclutar soldados."
        )
        return

    realm = data["realm"]

    lines = [
        "⚔️ <b>CUARTEL DEL REINO</b>",
        "",
        f"🏰 Reino: <b>{escape(realm['name'])}</b>",
        f"🏗 Cuartel: nivel <b>{data['barracks']}</b>",
        "",
        "🪖 <b>TROPAS DISPONIBLES</b>",
    ]

    total = 0
    total_attack = 0
    total_defense = 0

    for troop in data["troops"]:
        unit = UNITS.get(troop["unit_type"])

        if not unit:
            continue

        quantity = troop["quantity"]

        total += quantity
        total_attack += quantity * unit["attack"]
        total_defense += quantity * unit["defense"]

        lines.append(
            f"{unit['emoji']} {unit['name']}: "
            f"<b>{quantity:,}</b>"
        )

    if total == 0:
        lines.append(
            "<i>Todavía no tienes soldados reclutados.</i>"
        )

    lines.extend([
        "",
        "📊 <b>RESUMEN MILITAR</b>",
        f"🪖 Soldados: <b>{total:,}</b>",
        f"⚔️ Fuerza de ataque: <b>{total_attack:,}</b>",
        f"🛡️ Defensa: <b>{total_defense:,}</b>",
        "",
        "⏳ <b>ENTRENAMIENTOS</b>",
    ])

    if data["queue"]:
        now = datetime.now(timezone.utc)

        for item in data["queue"]:
            unit = UNITS.get(item["unit_type"])

            if unit:
                name = (
                    f"{unit['emoji']} {unit['name']}"
                )
            else:
                name = escape(item["unit_type"])

            remaining = item["finishes_at"] - now

            lines.append(
                f"• {name} x{item['quantity']}: "
                f"<b>{format_time(remaining)}</b>"
            )
    else:
        lines.append(
            "<i>No hay entrenamientos pendientes.</i>"
        )

    lines.extend([
        "",
        "Selecciona una unidad para consultar "
        "sus características y reclutarla.",
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=army_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "army")
async def army_handler(callback: CallbackQuery):
    await callback.answer()
    await render_army(callback)


@router.callback_query(F.data.startswith("army:unit:"))
async def unit_details(callback: CallbackQuery):
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "Solicitud incorrecta.",
            show_alert=True,
        )
        return

    unit_type = parts[2]
    unit = UNITS.get(unit_type)

    if not unit:
        await callback.answer(
            "Unidad no encontrada.",
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

    costs = {
        "wood": unit["wood"],
        "stone": unit["stone"],
        "gold": unit["gold"],
        "food": unit["food"],
    }

    text = (
        f"{unit['emoji']} <b>{unit['name'].upper()}</b>\n\n"
        f"{unit['description']}\n\n"
        f"⚔️ Ataque: <b>{unit['attack']}</b>\n"
        f"🛡️ Defensa: <b>{unit['defense']}</b>\n"
        f"🏗 Cuartel requerido: "
        f"<b>nivel {unit['barracks']}</b>\n\n"
        "<b>Coste por unidad</b>\n"
        f"{format_costs(costs)}\n\n"
        f"⏱ Tiempo base: <b>{unit['seconds']} segundos</b>"
    )

    await callback.answer()

    await callback.message.edit_text(
        text,
        reply_markup=unit_keyboard(unit_type),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("army:train:"))
async def train_units(callback: CallbackQuery):
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer(
            "Solicitud incorrecta.",
            show_alert=True,
        )
        return

    unit_type = parts[2]

    try:
        quantity = int(parts[3])
    except ValueError:
        await callback.answer(
            "Cantidad incorrecta.",
            show_alert=True,
        )
        return

    success, result_message = await start_training(
        callback.from_user.id,
        unit_type,
        quantity,
    )

    if not success:
        await callback.answer(
            "No se pudo iniciar el entrenamiento.",
            show_alert=True,
        )

        await callback.message.answer(
            result_message,
            parse_mode="HTML",
        )
        return

    await callback.answer(
        "Entrenamiento iniciado."
    )

    await render_army(callback)

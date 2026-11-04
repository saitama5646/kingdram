from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.services.military import (
    UNITS,
    get_military_data,
    start_training,
)
from bot.keyboards.army import army_keyboard, unit_keyboard


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


async def render_army(callback):
    data = await get_military_data(callback.from_user.id)

    if not data:
        await callback.message.edit_text(
            "No tienes un reino todavía.",
        )
        return

    realm = data["realm"]

    lines = [
        "<b>EJÉRCITO DEL REINO</b>",
        "",
        f"Reino: <b>{escape(realm['name'])}</b>",
        f"Cuartel: nivel {data['barracks']}",
        "",
        "<b>TROPAS DISPONIBLES</b>",
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
            f"• {unit['name']}: <b>{quantity:,}</b>"
        )

    if total == 0:
        lines.append("Todavía no tienes tropas.")

    lines.extend([
        "",
        "<b>RESUMEN MILITAR</b>",
        f"Soldados: {total:,}",
        f"Fuerza de ataque: {total_attack:,}",
        f"Defensa: {total_defense:,}",
        "",
        "<b>ENTRENAMIENTO</b>",
    ])

    if data["queue"]:
        for item in data["queue"]:
            unit = UNITS.get(item["unit_type"])
            name = unit["name"] if unit else item["unit_type"]

            remaining = item["finishes_at"] - __import__(
                "datetime"
            ).datetime.now(
                __import__("datetime").timezone.utc
            )

            lines.append(
                f"• {name} x{item['quantity']}: "
                f"{format_time(remaining)}"
            )
    else:
        lines.append("No hay entrenamientos pendientes.")

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
    unit_type = callback.data.split(":")[2]
    unit = UNITS.get(unit_type)

    if not unit:
        await callback.answer("Unidad no encontrada.", show_alert=True)
        return

    data = await get_military_data(callback.from_user.id)

    if not data:
        await callback.answer("Primero funda un reino.", show_alert=True)
        return

    costs = (
        f"Madera: {unit['wood']:,}\n"
        f"Piedra: {unit['stone']:,}\n"
        f"Oro: {unit['gold']:,}\n"
        f"Alimentos: {unit['food']:,}"
    )

    text = (
        f"<b>{unit['name'].upper()}</b>\n\n"
        f"{unit['description']}\n\n"
        f"Ataque: {unit['attack']}\n"
        f"Defensa: {unit['defense']}\n"
        f"Cuartel requerido: nivel {unit['barracks']}\n\n"
        f"<b>Coste por unidad</b>\n{costs}\n\n"
        f"Tiempo base: {unit['seconds']} segundos."
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
        await callback.answer("Solicitud incorrecta.", show_alert=True)
        return

    unit_type = parts[2]

    try:
        quantity = int(parts[3])
    except ValueError:
        await callback.answer("Cantidad incorrecta.", show_alert=True)
        return

    success, message = await start_training(
        callback.from_user.id,
        unit_type,
        quantity,
    )

    await callback.answer(
        message,
        show_alert=not success,
    )

    if success:
        await render_army(callback)

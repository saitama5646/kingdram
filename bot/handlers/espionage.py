
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.espionage import (
    MISSION_TYPES,
    get_spy_dashboard,
    recruit_spies,
    launch_spy_mission,
)


router = Router()


def espionage_keyboard(data):
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🕵 Entrenar 1 espía",
        callback_data="espionage:recruit:1",
    )

    builder.button(
        text="🕵 Entrenar 5 espías",
        callback_data="espionage:recruit:5",
    )

    builder.button(
        text="🕵 Entrenar 10 espías",
        callback_data="espionage:recruit:10",
    )

    for target in data["targets"]:
        builder.button(
            text=(
                f"🎯 {target['name']} "
                f"· Poder {target['power']}"
            )[:60],
            callback_data=f"espionage:target:{target['id']}",
        )

    builder.button(
        text="📜 Informes",
        callback_data="espionage:reports",
    )

    builder.button(
        text="↻ Actualizar",
        callback_data="espionage",
    )

    builder.button(
        text="⌂ Menú principal",
        callback_data="main_menu",
    )

    builder.adjust(1)

    return builder.as_markup()


def target_keyboard(target_id):
    builder = InlineKeyboardBuilder()

    for mission_type, label in MISSION_TYPES.items():
        builder.button(
            text=label,
            callback_data=(
                f"espionage:mission:{target_id}:{mission_type}"
            ),
        )

    builder.button(
        text="↩ Volver",
        callback_data="espionage",
    )

    builder.adjust(1)

    return builder.as_markup()


async def render_espionage(context):
    data = await get_spy_dashboard(
        context.from_user.id,
    )

    if not data:
        await context.answer(
            "Primero debes fundar un reino.",
            show_alert=True,
        )
        return

    lines = [
        "🕵 <b>INTELIGENCIA REAL</b>",
        "",
        f"🏰 Reino: <b>{escape(data['realm']['name'])}</b>",
        f"🕵 Espías disponibles: <b>{data['spies']}</b>",
        "",
        "<b>MISIONES EN CURSO</b>",
    ]

    if data["missions"]:
        for mission in data["missions"]:
            lines.append(
                f"• {MISSION_TYPES.get(mission['mission_type'], mission['mission_type'])}"
                f" — {mission['spies_sent']} espías"
            )
    else:
        lines.append("No hay misiones en curso.")

    lines.extend([
        "",
        "<b>REINOS OBJETIVO</b>",
        "Selecciona un reino para iniciar una misión.",
    ])

    await context.message.edit_text(
        "\n".join(lines),
        reply_markup=espionage_keyboard(data),
    )


@router.callback_query(F.data == "espionage")
async def espionage_handler(callback: CallbackQuery):
    await callback.answer()
    await render_espionage(callback)


@router.callback_query(F.data.startswith("espionage:recruit:"))
async def recruit_handler(callback: CallbackQuery):
    try:
        quantity = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer(
            "Cantidad inválida.",
            show_alert=True,
        )
        return

    success, message = await recruit_spies(
        callback.from_user.id,
        quantity,
    )

    await callback.answer(
        message,
        show_alert=not success,
    )

    if success:
        await render_espionage(callback)


@router.callback_query(F.data.startswith("espionage:target:"))
async def target_handler(callback: CallbackQuery):
    try:
        target_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer(
            "Objetivo inválido.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "🕵 <b>SELECCIONAR MISIÓN</b>\n\n"
        "Elige qué información deseas obtener.",
        reply_markup=target_keyboard(target_id),
    )


@router.callback_query(F.data.startswith("espionage:mission:"))
async def mission_handler(callback: CallbackQuery):
    try:
        _, _, target_id, mission_type = (
            callback.data.split(":")
        )

        target_id = int(target_id)

    except (ValueError, IndexError):
        await callback.answer(
            "Misión inválida.",
            show_alert=True,
        )
        return

    success, message = await launch_spy_mission(
        callback.from_user.id,
        target_id,
        mission_type,
        1,
    )

    await callback.answer(
        message,
        show_alert=not success,
    )

    if success:
        await render_espionage(callback)


@router.callback_query(F.data == "espionage:reports")
async def reports_handler(callback: CallbackQuery):
    data = await get_spy_dashboard(
        callback.from_user.id,
    )

    if not data:
        await callback.answer(
            "Primero debes fundar un reino.",
            show_alert=True,
        )
        return

    lines = [
        "📜 <b>INFORMES DE ESPIONAJE</b>",
        "",
    ]

    if not data["reports"]:
        lines.append("Todavía no tienes informes.")
    else:
        for report in data["reports"]:
            mission_name = MISSION_TYPES.get(
                report["mission_type"],
                report["mission_type"],
            )

            result = (
                "Éxito"
                if report["success"]
                else "Misión fallida"
            )

            lines.append(
                f"• <b>{mission_name}</b>\n"
                f"  Resultado: {result}\n"
                f"  Espías perdidos: {report['spies_lost']}\n"
            )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="↩ Espionaje",
        callback_data="espionage",
    )
    builder.button(
        text="⌂ Menú principal",
        callback_data="main_menu",
    )
    builder.adjust(1)

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
    )

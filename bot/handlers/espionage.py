
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import get_pool

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
                f"• <b>{escape(mission['target_name'])}</b>\n"
                f"  {MISSION_TYPES.get(mission['mission_type'], mission['mission_type'])}\n"
                f"  Espías enviados: {mission['spies_sent']}"
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


@router.callback_query(
    F.data.startswith("espionage:from_map:")
)
async def espionage_from_map_handler(
    callback: CallbackQuery,
):
    try:
        target_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer(
            "Objetivo inválido.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        own_realm = await connection.fetchrow(
            """
            SELECT id
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id,
        )

        if not own_realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True,
            )
            return

        target = await connection.fetchrow(
            """
            SELECT id, owner_id, name
            FROM realms
            WHERE id = $1
            """,
            target_id,
        )

    if not target:
        await callback.answer(
            "El reino objetivo ya no existe.",
            show_alert=True,
        )
        return

    if int(target["id"]) == int(own_realm["id"]):
        await callback.answer(
            "No puedes espiar tu propio reino.",
            show_alert=True,
        )
        return

    if int(target["owner_id"]) == int(callback.from_user.id):
        await callback.answer(
            "No puedes espiar tu propio reino.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "🕵 <b>ESPIONAJE DEL REINO</b>\\n\\n"
        f"🎯 Objetivo: <b>{escape(target['name'])}</b>\\n\\n"
        "Selecciona la información que deseas obtener.",
        reply_markup=target_keyboard(target_id),
        parse_mode="HTML",
    )


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
                f"• <b>{escape(report['target_name'])}</b>\n"
                f"  Misión: {mission_name}\n"
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

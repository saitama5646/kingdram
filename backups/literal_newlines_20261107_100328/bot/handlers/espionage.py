
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import get_pool

from bot.services.espionage import (
    MISSION_TYPES,
    get_spy_dashboard,
    get_spy_report,
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



def mission_quantity_keyboard(target_id, mission_type):
    builder = InlineKeyboardBuilder()

    for quantity in (1, 5, 10):
        builder.button(
            text=f"🕵 Enviar {quantity} espía(s)",
            callback_data=(
                f"espionage:quantity:{target_id}:"
                f"{mission_type}:{quantity}"
            ),
        )

    builder.button(
        text="↩ Volver a misiones",
        callback_data=f"espionage:target:{target_id}",
    )

    builder.button(
        text="⌂ Menú principal",
        callback_data="main_menu",
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
        "Selecciona un reino desde el mapa de navegación "
        "para iniciar una misión de espionaje.",
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
        _, _, target_id, mission_type = callback.data.split(":")
        target_id = int(target_id)
    except (ValueError, IndexError):
        await callback.answer(
            "Misión inválida.",
            show_alert=True,
        )
        return

    if mission_type not in MISSION_TYPES:
        await callback.answer(
            "Tipo de misión desconocido.",
            show_alert=True,
        )
        return

    data = await get_spy_dashboard(
        callback.from_user.id,
    )

    if not data:
        await callback.answer(
            "Primero debes fundar un reino.",
            show_alert=True,
        )
        return

    available_spies = int(data["spies"])
    mission_name = MISSION_TYPES[mission_type]

    await callback.answer()

    if available_spies < 1:
        message = (
            "🕵 <b>PREPARAR MISIÓN</b>\\n\\n"
            f"📋 Tipo: <b>{escape(mission_name)}</b>\\n\\n"
            "No tienes espías disponibles. "
            "Entrena agentes antes de iniciar la misión."
        )
    else:
        message = (
            "🕵 <b>PREPARAR MISIÓN</b>\\n\\n"
            f"📋 Tipo: <b>{escape(mission_name)}</b>\\n"
            f"🕵 Espías disponibles: <b>{available_spies}</b>\\n\\n"
            "Selecciona cuántos espías enviar."
        )

    await callback.message.edit_text(
        message,
        reply_markup=mission_quantity_keyboard(
            target_id,
            mission_type,
        ),
        parse_mode="HTML",
    )

@router.callback_query(
    F.data.startswith("espionage:quantity:")
)
async def mission_quantity_handler(
    callback: CallbackQuery,
):
    try:
        (
            _,
            _,
            target_id,
            mission_type,
            quantity,
        ) = callback.data.split(":")

        target_id = int(target_id)
        quantity = int(quantity)

    except (ValueError, IndexError):
        await callback.answer(
            "Cantidad o misión inválida.",
            show_alert=True,
        )
        return

    if quantity not in (1, 5, 10):
        await callback.answer(
            "Puedes enviar 1, 5 o 10 espías.",
            show_alert=True,
        )
        return

    if mission_type not in MISSION_TYPES:
        await callback.answer(
            "Tipo de misión desconocido.",
            show_alert=True,
        )
        return

    success, message = await launch_spy_mission(
        callback.from_user.id,
        target_id,
        mission_type,
        quantity,
    )

    await callback.answer(
        message,
        show_alert=not success,
    )

    if success:
        await render_espionage(callback)



@router.callback_query(
    F.data.startswith("espionage:reports")
)
async def reports_handler(callback: CallbackQuery):
    try:
        parts = callback.data.split(":")
        offset = int(parts[2]) if len(parts) > 2 else 0

    except (ValueError, IndexError):
        await callback.answer(
            "Página inválida.",
            show_alert=True,
        )
        return

    offset = max(0, offset)

    data = await get_spy_dashboard(
        callback.from_user.id,
        report_offset=offset,
    )

    if not data:
        await callback.answer(
            "Primero debes fundar un reino.",
            show_alert=True,
        )
        return

    reports = data["reports"]

    lines = [
        "📜 <b>HISTORIAL DE ESPIONAJE</b>",
        "",
        f"Página: <b>{offset // 10 + 1}</b>",
        "",
    ]

    builder = InlineKeyboardBuilder()

    if not reports:
        lines.append("No hay informes en esta página.")

    else:
        for report in reports:
            mission_name = MISSION_TYPES.get(
                report["mission_type"],
                report["mission_type"],
            )

            result = (
                "Éxito"
                if report["success"]
                else "Misión fallida"
            )

            spies_sent = int(
                report["spies_sent"] or 0
            )

            spies_lost = int(
                report["spies_lost"] or 0
            )

            spies_returned = max(
                0,
                spies_sent - spies_lost,
            )

            lines.append(
                f"• <b>{escape(report['target_name'])}</b>\n"
                f"  Misión: {escape(mission_name)}\n"
                f"  Resultado: {result}\n"
                f"  Enviados: {spies_sent}\n"
                f"  Perdidos: {spies_lost}\n"
                f"  Retornados: {spies_returned}\n"
            )

            builder.button(
                text=f"📄 Informe #{report['id']}",
                callback_data=(
                    f"espionage:report:{report['id']}"
                ),
            )

    if offset > 0:
        builder.button(
            text="⬅ Página anterior",
            callback_data=(
                f"espionage:reports:{max(0, offset - 10)}"
            ),
        )

    if len(reports) == 10:
        builder.button(
            text="➡ Página siguiente",
            callback_data=(
                f"espionage:reports:{offset + 10}"
            ),
        )

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
        parse_mode="HTML",
    )


@router.callback_query(
    F.data.startswith("espionage:report:")
)
async def report_detail_handler(
    callback: CallbackQuery,
):
    try:
        report_id = int(
            callback.data.split(":")[-1]
        )

    except (ValueError, IndexError):
        await callback.answer(
            "Informe inválido.",
            show_alert=True,
        )
        return

    report = await get_spy_report(
        callback.from_user.id,
        report_id,
    )

    if not report:
        await callback.answer(
            "El informe no existe o no te pertenece.",
            show_alert=True,
        )
        return

    mission_name = MISSION_TYPES.get(
        report["mission_type"],
        report["mission_type"],
    )

    spies_sent = int(
        report.get("spies_sent", 0) or 0
    )

    spies_lost = int(
        report.get("spies_lost", 0) or 0
    )

    spies_returned = max(
        0,
        spies_sent - spies_lost,
    )

    result = (
        "ÉXITO"
        if report["success"]
        else "MISIÓN FALLIDA"
    )

    lines = [
        "📜 <b>INFORME DETALLADO</b>",
        "",
        f"🏰 Objetivo: <b>{escape(report['target_name'])}</b>",
        f"📋 Misión: <b>{escape(mission_name)}</b>",
        f"🎯 Resultado: <b>{result}</b>",
        "",
        "<b>ESTADO DE LOS AGENTES</b>",
        f"🕵 Espías enviados: {spies_sent}",
        f"❌ Espías perdidos: {spies_lost}",
        f"↩ Espías retornados: {spies_returned}",
        "",
    ]

    intelligence = report.get("intelligence") or {}

    if isinstance(intelligence, str):
        import json

        try:
            intelligence = json.loads(intelligence)
        except (ValueError, TypeError):
            intelligence = {}

    if report["success"] and intelligence:
        lines.append("<b>INFORMACIÓN OBTENIDA</b>")

        labels = {
            "wood": "Madera",
            "stone": "Piedra",
            "gold": "Oro",
            "food": "Alimentos",
            "army": "Ejército",
            "buildings": "Edificios",
            "research": "Investigaciones",
        }

        for key, value in intelligence.items():
            label = labels.get(key, key.title())

            if isinstance(value, list):
                lines.append(
                    f"\n<b>{escape(label)}</b>"
                )

                if not value:
                    lines.append("• No se encontraron datos.")

                for item in value:
                    if isinstance(item, dict):
                        details = " — ".join(
                            f"{escape(str(k))}: "
                            f"{escape(str(v))}"
                            for k, v in item.items()
                        )

                        lines.append(f"• {details}")

                    else:
                        lines.append(
                            f"• {escape(str(item))}"
                        )

            elif isinstance(value, dict):
                lines.append(
                    f"\n<b>{escape(label)}</b>"
                )

                for subkey, subvalue in value.items():
                    lines.append(
                        f"• {escape(str(subkey))}: "
                        f"{escape(str(subvalue))}"
                    )

            else:
                lines.append(
                    f"• <b>{escape(label)}:</b> "
                    f"{escape(str(value))}"
                )

    elif not report["success"]:
        lines.append(
            "La misión no obtuvo información "
            "del reino objetivo."
        )

    else:
        lines.append(
            "No hay información registrada "
            "en este informe."
        )

    builder = InlineKeyboardBuilder()

    builder.button(
        text="↩ Volver a informes",
        callback_data="espionage:reports",
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
        parse_mode="HTML",
    )

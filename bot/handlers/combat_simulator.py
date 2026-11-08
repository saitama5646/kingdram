import asyncio
from html import escape

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import get_pool
from bot.services.combat_simulator import (
    parse_roster,
    simulate_battle,
)
from bot.services.military import UNITS
from bot.services.research import get_research_effects


router = Router()


class CombatSimulatorStates(StatesGroup):
    attacker = State()
    defender = State()
    battles = State()


def simulator_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(
        text="⚔️ Nueva simulación",
        callback_data="combat_simulator:start",
    )

    builder.button(
        text="⌂ Menú principal",
        callback_data="main_menu",
    )

    builder.adjust(1)

    return builder.as_markup()


def format_roster(roster):
    lines = []

    for troop in roster:
        unit_type = troop["unit_type"]
        quantity = int(troop["quantity"])
        unit = UNITS[unit_type]

        lines.append(
            f"• {unit['emoji']} {escape(unit['name'])}: "
            f"{quantity:,}"
        )

    return "\n".join(lines)


def format_result(result, title="SIMULACIÓN DE COMBATE"):
    outcomes = result["outcomes"]
    averages = result["averages"]

    lines = [
        f"⚔️ <b>{title}</b>",
        "",
        f"🔁 Simulaciones: <b>{result['battles']:,}</b>",
        f"🎲 Semilla: <code>{result['seed']}</code>",
        "",
        "<b>PROBABILIDADES</b>",
        (
            "🏆 Victoria atacante: "
            f"<b>{outcomes['attacker_victory']['percentage']}%</b>"
        ),
        (
            "🛡️ Victoria defensor: "
            f"<b>{outcomes['defender_victory']['percentage']}%</b>"
        ),
        (
            "⚖️ Inconclusas: "
            f"<b>{outcomes['inconclusive']['percentage']}%</b>"
        ),
        (
            "☠️ Destrucción mutua: "
            f"<b>{outcomes['mutual_destruction']['percentage']}%</b>"
        ),
        "",
        "<b>PROMEDIOS POR BATALLA</b>",
        f"🔁 Rondas: <b>{averages['rounds']}</b>",
        (
            "💀 Bajas atacante: "
            f"<b>{averages['attacker_losses']:,.2f}</b>"
        ),
        (
            "💀 Bajas defensor: "
            f"<b>{averages['defender_losses']:,.2f}</b>"
        ),
        (
            "🪖 Supervivientes atacante: "
            f"<b>{averages['attacker_survivors']:,.2f}</b>"
        ),
        (
            "🪖 Supervivientes defensor: "
            f"<b>{averages['defender_survivors']:,.2f}</b>"
        ),
        "",
        "<b>PORCENTAJE DE BAJAS</b>",
        (
            "Atacante: "
            f"<b>{averages['attacker_loss_percentage']}%</b>"
        ),
        (
            "Defensor: "
            f"<b>{averages['defender_loss_percentage']}%</b>"
        ),
    ]

    return "\n".join(lines)


@router.callback_query(F.data == "combat_simulator:start")
async def simulator_start_handler(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await state.set_state(CombatSimulatorStates.attacker)

    await callback.answer()

    await callback.message.edit_text(
        "⚔️ <b>SIMULADOR DE COMBATE</b>\n\n"
        "Introduce las tropas del atacante.\n\n"
        "Formato: <code>unidad=cantidad,unidad=cantidad</code>\n\n"
        "Ejemplo:\n"
        "<code>spearman=100,archer=50</code>\n\n"
        "Unidades disponibles:\n"
        "<code>spearman</code> — Lancero\n"
        "<code>archer</code> — Arquero\n"
        "<code>cavalry</code> — Caballería\n"
        "<code>royal_guard</code> — Guardia real",
        parse_mode="HTML",
    )


@router.message(CombatSimulatorStates.attacker)
async def simulator_attacker_handler(
    message: Message,
    state: FSMContext,
):
    try:
        roster = parse_roster(message.text.strip())

    except Exception as exc:
        await message.answer(
            "Roster inválido.\n\n"
            f"{escape(str(exc))}\n\n"
            "Ejemplo: <code>spearman=100,archer=50</code>",
            parse_mode="HTML",
        )
        return

    await state.update_data(attacker=roster)
    await state.set_state(CombatSimulatorStates.defender)

    await message.answer(
        "🛡️ <b>Ejército defensor</b>\n\n"
        "Introduce las tropas del defensor.\n\n"
        "Ejemplo:\n"
        "<code>spearman=80,royal_guard=10</code>",
        parse_mode="HTML",
    )


@router.message(CombatSimulatorStates.defender)
async def simulator_defender_handler(
    message: Message,
    state: FSMContext,
):
    try:
        roster = parse_roster(message.text.strip())

    except Exception as exc:
        await message.answer(
            "Roster inválido.\n\n"
            f"{escape(str(exc))}\n\n"
            "Ejemplo: <code>spearman=80,royal_guard=10</code>",
            parse_mode="HTML",
        )
        return

    await state.update_data(defender=roster)
    await state.set_state(CombatSimulatorStates.battles)

    await message.answer(
        "🔁 <b>Cantidad de simulaciones</b>\n\n"
        "Introduce cuántas batallas deseas ejecutar.\n"
        "No existe un límite artificial de ejecuciones.\n\n"
        "Ejemplo: <code>1000</code>",
        parse_mode="HTML",
    )


@router.message(CombatSimulatorStates.battles)
async def simulator_battles_handler(
    message: Message,
    state: FSMContext,
):
    try:
        battles = int(message.text.strip())

        if battles <= 0:
            raise ValueError(
                "La cantidad debe ser mayor que cero."
            )

    except (ValueError, AttributeError):
        await message.answer(
            "Introduce un número entero positivo."
        )
        return

    data = await state.get_data()

    await state.clear()

    await message.answer(
        "⚔️ Simulando batallas...\n"
        f"Cantidad: {battles:,}\n\n"
        "El proceso no modifica los ejércitos reales."
    )

    try:
        result = await asyncio.to_thread(
            simulate_battle,
            data["attacker"],
            data["defender"],
            battles,
            None,
        )

    except Exception as exc:
        await message.answer(
            "No se pudo completar la simulación.\n\n"
            f"<code>{escape(str(exc))}</code>",
            parse_mode="HTML",
        )
        return

    await message.answer(
        format_result(result),
        reply_markup=simulator_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(
    F.data.startswith("combat_simulator:spy:")
)
async def simulator_spy_handler(
    callback: CallbackQuery,
):
    try:
        report_id = int(callback.data.split(":")[-1])

    except (ValueError, IndexError):
        await callback.answer(
            "Informe inválido.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id,
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar un reino.",
                show_alert=True,
            )
            return

        report = await connection.fetchrow(
            """
            SELECT
                er.id,
                er.success,
                er.mission_type,
                er.intelligence,
                target.name AS target_name
            FROM espionage_reports er
            JOIN realms target
              ON target.id = er.target_realm_id
            WHERE er.id = $1
              AND er.attacker_realm_id = $2
            """,
            report_id,
            realm["id"],
        )

        if not report:
            await callback.answer(
                "El informe no existe o no te pertenece.",
                show_alert=True,
            )
            return

        if (
            not report["success"]
            or report["mission_type"] != "military"
        ):
            await callback.answer(
                "Este informe no contiene inteligencia militar válida.",
                show_alert=True,
            )
            return

        intelligence = report["intelligence"] or {}

        if isinstance(intelligence, str):
            import json
            try:
                intelligence = json.loads(intelligence)
            except (ValueError, TypeError):
                intelligence = {}

        defender_roster = intelligence.get("army") or []

        if not defender_roster:
            await callback.answer(
                "El informe indica que el reino no tiene tropas "
                "registradas para simular.",
                show_alert=True,
            )
            return

        own_rows = await connection.fetch(
            """
            SELECT unit_type, quantity
            FROM army
            WHERE realm_id = $1
              AND quantity > 0
            ORDER BY unit_type
            """,
            realm["id"],
        )

        own_research_rows = await connection.fetch(
            """
            SELECT research_type, level
            FROM realm_research
            WHERE realm_id = $1
            """,
            realm["id"],
        )

    attacker_roster = [
        {
            "unit_type": row["unit_type"],
            "quantity": int(row["quantity"]),
        }
        for row in own_rows
    ]

    attacker_research = get_research_effects({
        row["research_type"]: int(row["level"])
        for row in own_research_rows
    })

    try:
        from bot.services.combat_simulator import validate_roster

        attacker_roster = validate_roster(
            attacker_roster,
            "Atacante",
        )

        defender_roster = validate_roster(
            defender_roster,
            "Defensor",
        )

    except Exception as exc:
        await callback.answer(
            str(exc)[:180],
            show_alert=True,
        )
        return

    if not attacker_roster:
        await callback.answer(
            "Tu reino no tiene tropas disponibles para simular.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "⚔️ <b>SIMULACIÓN DESDE ESPIONAJE</b>\n\n"
        f"🏰 Atacante: <b>{escape(realm['name'])}</b>\n"
        f"🎯 Defensor: <b>{escape(report['target_name'])}</b>\n\n"
        "<b>TU EJÉRCITO</b>\n"
        f"{format_roster(attacker_roster)}\n\n"
        "<b>EJÉRCITO DETECTADO</b>\n"
        f"{format_roster(defender_roster)}\n\n"
        "🔁 Ejecutando 25 simulaciones...\n"
        "No se consumen tropas ni se modifican reinos.",
        parse_mode="HTML",
    )

    try:
        result = await asyncio.to_thread(
            simulate_battle,
            attacker_roster,
            defender_roster,
            25,
            None,
            attacker_research,
            {},
        )

    except Exception as exc:
        await callback.message.answer(
            "No se pudo completar la simulación.\n\n"
            f"<code>{escape(str(exc))}</code>",
            parse_mode="HTML",
        )
        return

    await callback.message.answer(
        format_result(
            result,
            title="SIMULACIÓN BASADA EN ESPIONAJE",
        ),
        reply_markup=simulator_keyboard(),
        parse_mode="HTML",
    )

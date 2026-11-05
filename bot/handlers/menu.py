from datetime import datetime, timezone
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.connection import get_pool
from bot.keyboards.main_menu import (
    main_menu_keyboard,
    back_to_menu_keyboard,
)

from bot.handlers.kingdom import show_kingdom
from bot.handlers.buildings import render_buildings
from bot.handlers.army import render_army
from bot.handlers.economy import render_economy
from bot.handlers.research import render_research
from bot.handlers.territory import render_territories
from bot.handlers.ranking import ranking_handler
from bot.handlers.battle import war_menu as battle_menu
from bot.handlers.diplomacy import render_diplomacy

from bot.services.construction import BUILDINGS
from bot.services.military import UNITS
from bot.services.research import RESEARCH, get_research_effects
from bot.workers.production import calculate_production, split_tribute


router = Router()


class MessageProxy:
    """Adapta una respuesta de mensaje al formato de las pantallas."""

    def __init__(self, message: Message):
        self.source = message

    async def edit_text(self, text, **kwargs):
        await self.source.answer(text, **kwargs)


class MessageScreenContext:
    """Permite reutilizar renderizadores desde el menú persistente."""

    def __init__(self, message: Message):
        self.from_user = message.from_user
        self.message = MessageProxy(message)
        self.source = message

    async def answer(self, text=None, show_alert=False, **kwargs):
        if text and show_alert:
            await self.source.answer(text, **kwargs)


MENU_ACTIONS = {
    "🏰 Reino": "kingdom",
    "⚔ Ejército": "army",
    "🏗 Edificios": "buildings",
    "🔬 Investigaciones": "research",
    "📦 Recursos": "economy",
    "🗺 Territorios": "territory",
    "🛡 Guerra": "battle",
    "🏆 Clasificación": "ranking",
    "👑 Diplomacia": "diplomacy",
    "⌂ Menú principal": "main_menu",
}


RESOURCE_INFO = {
    "wood": ("🪵", "Madera"),
    "stone": ("🪨", "Piedra"),
    "gold": ("🪙", "Oro"),
    "food": ("🌾", "Alimentos"),
}


def format_number(value):
    return f"{int(value):,}".replace(",", ".")


def format_remaining(value):
    if value is None:
        return "Sin actividad"

    seconds = max(
        0,
        int(
            (
                value - datetime.now(timezone.utc)
            ).total_seconds()
        ),
    )

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if days:
        return f"{days}d {hours}h"

    if hours:
        return f"{hours}h {minutes}m"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


async def build_main_menu(user_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT
                r.id,
                r.name,
                r.level,
                p.wood,
                p.stone,
                p.gold,
                p.food
            FROM realms r
            LEFT JOIN resources p
                ON p.realm_id = r.id
            WHERE r.owner_id = $1
            """,
            user_id,
        )

        if not realm:
            return (
                "🏰 <b>KINGDRAM</b>\n\n"
                "Todavía no has fundado tu reino.\n"
                "Funda tu primer dominio para comenzar "
                "a administrar tus tierras."
            )

        realm_id = realm["id"]

        resources = {
            resource: realm[resource] or 0
            for resource in RESOURCE_INFO
        }

        buildings = await connection.fetch(
            """
            SELECT building_type, level
            FROM buildings
            WHERE realm_id = $1
            """,
            realm_id,
        )

        research_rows = await connection.fetch(
            """
            SELECT research_type, level
            FROM realm_research
            WHERE realm_id = $1
            """,
            realm_id,
        )

        construction_queue = await connection.fetch(
            """
            SELECT
                building_type,
                target_level,
                queue_position,
                finishes_at
            FROM construction_queue
            WHERE realm_id = $1
            ORDER BY queue_position, finishes_at, id
            """,
            realm_id,
        )

        training_queue = await connection.fetch(
            """
            SELECT
                unit_type,
                quantity,
                finishes_at
            FROM training_queue
            WHERE realm_id = $1
            ORDER BY finishes_at, id
            """,
            realm_id,
        )

        research_queue = await connection.fetch(
            """
            SELECT
                research_type,
                target_level,
                queue_position,
                finishes_at
            FROM research_queue
            WHERE realm_id = $1
            ORDER BY queue_position, finishes_at, id
            """,
            realm_id,
        )

        vassalage = await connection.fetchrow(
            """
            SELECT tribute_rate
            FROM vassalage_relations
            WHERE vassal_realm_id = $1
              AND status = 'active'
            LIMIT 1
            """,
            realm_id,
        )

    research_levels = {
        row["research_type"]: row["level"]
        for row in research_rows
    }

    research_effects = get_research_effects(
        research_levels
    )

    production = calculate_production(
        buildings,
        research_effects,
    )

    if vassalage:
        _, production = split_tribute(
            production,
            vassalage["tribute_rate"],
        )

    lines = [
        f"🏰 <b>{escape(realm['name'])}</b>",
        f"⭐ Nivel {realm['level']}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📦 <b>RECURSOS DEL REINO</b>",
        "",
    ]

    for resource, (icon, name) in RESOURCE_INFO.items():
        amount = resources[resource]
        hourly = production[resource] * 60

        lines.append(
            f"{icon} <b>{name}:</b> "
            f"{format_number(amount)} "
            f"<i>(+{format_number(hourly)}/h)</i>"
        )

    if vassalage:
        tribute_percent = float(
            vassalage["tribute_rate"]
        ) * 100

        lines.extend([
            "",
            f"👑 Tributo feudal: <b>{tribute_percent:.0f}%</b>",
            "<i>Producción mostrada después del tributo.</i>",
        ])

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🏗 <b>COLA DE CONSTRUCCIÓN</b>",
    ])

    if construction_queue:
        for item in construction_queue:
            building = BUILDINGS.get(
                item["building_type"],
                {},
            )

            name = building.get(
                "name",
                item["building_type"],
            )

            icon = building.get("icon", "🏗")

            remaining = format_remaining(
                item["finishes_at"]
            )

            lines.append(
                f"{item['queue_position']}. "
                f"{icon} {escape(name)} "
                f"→ nivel {item['target_level']}"
            )

            lines.append(
                f"   ⏳ {remaining}"
            )
    else:
        lines.append(
            "<i>No hay construcciones pendientes.</i>"
        )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "⚔ <b>COLA DE ENTRENAMIENTO</b>",
    ])

    if training_queue:
        for index, item in enumerate(training_queue, start=1):
            unit = UNITS.get(
                item["unit_type"],
                {},
            )

            name = unit.get(
                "name",
                item["unit_type"],
            )

            icon = unit.get("emoji", "🪖")

            remaining = format_remaining(
                item["finishes_at"]
            )

            lines.append(
                f"{index}. {icon} {escape(name)} "
                f"x{item['quantity']}"
            )

            lines.append(
                f"   ⏳ {remaining}"
            )
    else:
        lines.append(
            "<i>No hay tropas entrenándose.</i>"
        )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🔬 <b>COLA DE INVESTIGACIÓN</b>",
    ])

    if research_queue:
        for item in research_queue:
            research = RESEARCH.get(
                item["research_type"],
                {},
            )

            name = research.get(
                "name",
                item["research_type"],
            )

            icon = research.get("icon", "📚")

            remaining = format_remaining(
                item["finishes_at"]
            )

            lines.append(
                f"{item['queue_position']}. "
                f"{icon} {escape(name)} "
                f"→ nivel {item['target_level']}"
            )

            lines.append(
                f"   ⏳ {remaining}"
            )
    else:
        lines.append(
            "<i>No hay investigaciones pendientes.</i>"
        )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "<i>Selecciona el apartado que deseas administrar.</i>",
    ])

    return "\n".join(lines)


async def show_main_menu_message(message: Message):
    text = await build_main_menu(
        message.from_user.id
    )

    await message.answer(
        text,
        reply_markup=main_menu_keyboard(),
    )


async def open_screen(context, destination):
    if destination == "kingdom":
        await show_kingdom(context)

    elif destination == "army":
        await render_army(context)

    elif destination == "buildings":
        await render_buildings(context)

    elif destination == "research":
        await render_research(context)

    elif destination == "economy":
        await render_economy(context)

    elif destination == "territory":
        await render_territories(context)

    elif destination == "battle":
        await battle_menu(context)

    elif destination == "ranking":
        await ranking_handler(context)

    elif destination == "diplomacy":
        await render_diplomacy(context)


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery):
    await callback.answer()

    text = await build_main_menu(
        callback.from_user.id
    )

    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text.in_(set(MENU_ACTIONS.keys())))
async def persistent_menu_handler(
    message: Message,
    state: FSMContext,
):
    destination = MENU_ACTIONS.get(message.text)

    if not destination:
        return

    await state.clear()

    if destination == "main_menu":
        await show_main_menu_message(message)
        return

    context = MessageScreenContext(message)

    await open_screen(
        context,
        destination,
    )

from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.connection import get_pool
from bot.services.construction import BUILDINGS, get_production
from bot.services.storage import get_storage_capacity
from bot.keyboards.economy import economy_keyboard
from bot.keyboards.main_menu import create_realm_keyboard


router = Router()


RESOURCE_INFO = {
    "wood": {
        "name": "Madera",
        "icon": "🪵",
    },
    "stone": {
        "name": "Piedra",
        "icon": "🪨",
    },
    "gold": {
        "name": "Oro",
        "icon": "🪙",
    },
    "food": {
        "name": "Alimentos",
        "icon": "🌾",
    },
}


def format_number(value):
    return f"{int(value):,}".replace(",", ".")


def format_remaining(value):
    if value is None:
        return "Pendiente de programación"

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    seconds = max(
        0,
        int(
            (value - datetime.now(timezone.utc)).total_seconds()
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


def calculate_production(buildings):
    production = {
        "wood": 0,
        "stone": 0,
        "gold": 0,
        "food": 0,
    }

    for building in buildings:
        building_type = building["building_type"]

        if building_type not in BUILDINGS:
            continue

        resource = BUILDINGS[building_type]["resource"]

        if resource not in production:
            continue

        production[resource] += get_production(
            building_type,
            building["level"],
        )

    return production


async def render_economy(callback):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT
                r.id,
                r.name,
                p.wood,
                p.stone,
                p.gold,
                p.food,
                p.updated_at
            FROM realms r
            JOIN resources p
              ON p.realm_id = r.id
            WHERE r.owner_id = $1
            """,
            callback.from_user.id,
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True,
            )

            await callback.message.edit_text(
                "🏰 <b>Aún no posees un reino.</b>\n\n"
                "Funda tu primer dominio para comenzar "
                "a desarrollar su economía.",
                reply_markup=create_realm_keyboard(),
            )
            return

        buildings = await connection.fetch(
            """
            SELECT
                building_type,
                GREATEST(level - damaged_levels, 0) AS level,
                level AS original_level,
                damaged_levels,
                rebuild_at
            FROM buildings
            WHERE realm_id = $1
            """,
            realm["id"],
        )

    production = calculate_production(buildings)
    capacity = get_storage_capacity(buildings)

    levels = {
        item["building_type"]: item["level"]
        for item in buildings
    }

    warehouse_level = levels.get("warehouse", 0)
    granary_level = levels.get("granary", 0)

    lines = [
        "📦 <b>ECONOMÍA DEL REINO</b>",
        "",
        f"🏰 Dominio: <b>{realm['name']}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📊 <b>RECURSOS DISPONIBLES</b>",
        "",
    ]

    for resource, info in RESOURCE_INFO.items():
        amount = realm[resource]
        limit = capacity[resource]

        percentage = (
            amount / limit * 100
            if limit > 0
            else 0
        )

        lines.append(
            f"{info['icon']} <b>{info['name']}</b>"
        )

        lines.append(
            f"   {format_number(amount)} / "
            f"{format_number(limit)}"
        )

        lines.append(
            f"   Almacenamiento: {percentage:.1f}%"
        )

    damaged_buildings = [
        building
        for building in buildings
        if int(building["damaged_levels"] or 0) > 0
    ]

    if damaged_buildings:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            "🛠 <b>EDIFICIOS DAÑADOS</b>",
            "",
            "<i>Los niveles dañados no producen ni aportan "
            "capacidad hasta terminar su reconstrucción.</i>",
            "",
        ])

        for building in damaged_buildings:
            info = BUILDINGS.get(
                building["building_type"],
                {},
            )

            name = info.get(
                "name",
                building["building_type"],
            )

            original = int(building["original_level"])
            effective = int(building["level"])
            damaged = int(building["damaged_levels"] or 0)

            lines.extend([
                f"{info.get('icon', '🏗')} <b>{name}</b>",
                f"   Nivel operativo: <b>{effective}/{original}</b>",
                f"   Niveles dañados: <b>{damaged}</b>",
                f"   Reconstrucción: <b>{format_remaining(building['rebuild_at'])}</b>",
                "",
            ])

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📈 <b>PRODUCCIÓN POR HORA</b>",
        "",
    ])

    for resource, info in RESOURCE_INFO.items():
        hourly = production[resource] * 60
        daily = hourly * 24

        lines.append(
            f"{info['icon']} {info['name']}: "
            f"<b>+{format_number(hourly)}/h</b>"
        )

        lines.append(
            f"   <i>+{format_number(daily)} al día</i>"
        )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🏗 <b>CAPACIDAD DE ALMACENAMIENTO</b>",
        "",
        f"🏚️ Almacén: nivel <b>{warehouse_level}</b>",
        f"🌾 Granero: nivel <b>{granary_level}</b>",
        "",
        "<i>El Almacén aumenta los límites de madera, "
        "piedra y oro. El Granero aumenta el límite "
        "de alimentos.</i>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🏭 <b>INFRAESTRUCTURA PRODUCTIVA</b>",
    ])

    productive_buildings = 0

    for building in buildings:
        building_type = building["building_type"]

        if building_type not in BUILDINGS:
            continue

        resource = BUILDINGS[building_type]["resource"]

        if not resource:
            continue

        productive_buildings += 1

        info = BUILDINGS[building_type]

        lines.append(
            f"{info['icon']} {info['name']}: "
            f"nivel {building['level']}"
        )

    if productive_buildings == 0:
        lines.append(
            "<i>No hay edificios productivos.</i>"
        )

    lines.extend([
        "",
        "<i>La producción se procesa automáticamente "
        "cada minuto. Los recursos no superarán "
        "la capacidad de almacenamiento.</i>",
    ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=economy_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(
    F.data.in_({"economy", "economy_refresh"})
)
async def economy_handler(callback: CallbackQuery):
    await render_economy(callback)

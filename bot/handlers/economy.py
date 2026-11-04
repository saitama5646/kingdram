
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.connection import get_pool
from bot.services.construction import BUILDINGS, get_production
from bot.keyboards.economy import economy_keyboard
from bot.keyboards.main_menu import create_realm_keyboard


router = Router()

RESOURCE_INFO = {
    "wood": {
        "name": "Madera",
        "icon": "🪵"
    },
    "stone": {
        "name": "Piedra",
        "icon": "🪨"
    },
    "gold": {
        "name": "Oro",
        "icon": "🪙"
    },
    "food": {
        "name": "Alimentos",
        "icon": "🌾"
    }
}


def format_number(value):
    return f"{int(value):,}".replace(",", ".")


def calculate_production(buildings):
    production = {
        "wood": 0,
        "stone": 0,
        "gold": 0,
        "food": 0
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
            building["level"]
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
            JOIN resources p ON p.realm_id = r.id
            WHERE r.owner_id = $1
            """,
            callback.from_user.id
        )

        if not realm:
            await callback.answer(
                "Primero debes fundar tu reino.",
                show_alert=True
            )

            await callback.message.edit_text(
                "🏰 <b>Aún no posees un reino.</b>\n\n"
                "Funda tu primer dominio para comenzar "
                "a desarrollar su economía.",
                reply_markup=create_realm_keyboard()
            )
            return

        buildings = await connection.fetch(
            """
            SELECT building_type, level
            FROM buildings
            WHERE realm_id = $1
            """,
            realm["id"]
        )

    production = calculate_production(buildings)

    lines = [
        "📦 <b>ECONOMÍA DEL REINO</b>",
        "",
        f"🏰 Dominio: <b>{realm['name']}</b>",
        "",
        "<b>RECURSOS DISPONIBLES</b>"
    ]

    for resource, info in RESOURCE_INFO.items():
        amount = realm[resource]

        lines.append(
            f"{info['icon']} {info['name']}: "
            f"<b>{format_number(amount)}</b>"
        )

    lines.extend([
        "",
        "📈 <b>PRODUCCIÓN</b>",
        "<i>Rendimiento según los edificios actuales.</i>"
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
        "🏗 <b>INFRAESTRUCTURA PRODUCTIVA</b>"
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
        lines.append("<i>No hay edificios productivos.</i>")

    lines.extend([
        "",
        "<i>Las tasas se calculan por hora a partir "
        "de la producción actual de tus edificios.</i>",
        "",
        "<i>El consumo y los límites de almacenamiento "
        "se incorporarán cuando estén implementados.</i>"
    ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=economy_keyboard()
    )


@router.callback_query(F.data.in_({"economy", "economy_refresh"}))
async def economy_handler(callback: CallbackQuery):
    await render_economy(callback)

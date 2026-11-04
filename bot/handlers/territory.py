
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.connection import get_pool
from bot.keyboards.territory import territory_keyboard
from bot.keyboards.main_menu import create_realm_keyboard


router = Router()


def format_date(value):
    if not value:
        return "Fecha desconocida"

    return value.strftime("%d/%m/%Y")


async def render_territories(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
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
                "Debes fundar tu dominio antes de "
                "administrar tus territorios.",
                reply_markup=create_realm_keyboard()
            )
            return

        provinces = await connection.fetch(
            """
            SELECT
                id,
                name,
                province_number,
                created_at
            FROM provinces
            WHERE realm_id = $1
            ORDER BY province_number ASC
            """,
            realm["id"]
        )

    lines = [
        "🗺 <b>TERRITORIOS DEL REINO</b>",
        "",
        f"🏰 Dominio: <b>{realm['name']}</b>",
        f"📍 Provincias controladas: <b>{len(provinces)}</b>",
        "",
        "<b>PROVINCIAS</b>"
    ]

    if provinces:
        for province in provinces:
            lines.extend([
                "",
                f"🏞 <b>{province['name']}</b>",
                f"   Posición: <b>{province['province_number']}</b>",
                f"   Fundada: {format_date(province['created_at'])}"
            ])
    else:
        lines.extend([
            "",
            "<i>Tu reino todavía no tiene provincias "
            "registradas.</i>"
        ])

    lines.extend([
        "",
        "⚒ <b>Expansión territorial</b>",
        "La colonización estará disponible cuando "
        "se incorporen las tecnologías, los requisitos "
        "y las posiciones de expansión."
    ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=territory_keyboard()
    )


@router.callback_query(
    F.data.in_({"territory", "territory_refresh"})
)
async def territory_handler(callback: CallbackQuery):
    await render_territories(callback)

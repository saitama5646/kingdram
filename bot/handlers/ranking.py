from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.services.scoring import (
    refresh_all_scores,
    get_ranking,
)

from bot.keyboards.main_menu import back_to_menu_keyboard


router = Router()


def format_number(value):
    return f"{int(value):,}".replace(",", ".")


@router.callback_query(F.data == "ranking")
async def ranking_handler(callback: CallbackQuery):
    await callback.answer("Calculando puntuaciones...")

    await refresh_all_scores()
    ranking = await get_ranking(10)

    if not ranking:
        await callback.message.edit_text(
            "🏆 <b>CLASIFICACIÓN DE KINGDRAM</b>\n\n"
            "Todavía no existen reinos clasificados.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    lines = [
        "🏆 <b>CLASIFICACIÓN DE KINGDRAM</b>",
        "",
        "<i>Los diez dominios más poderosos.</i>",
        "",
    ]

    medals = ("🥇", "🥈", "🥉")
    own_position = None

    for index, item in enumerate(ranking):
        position = index + 1
        medal = (
            medals[index]
            if index < 3
            else f"{position}."
        )

        name = escape(item["name"])

        lines.extend([
            f"{medal} <b>{name}</b>",
            (
                "   Puntos: "
                f"<b>{format_number(item['total_points'])}</b>"
            ),
            (
                f"   🏗 {format_number(item['building_points'])}"
                f" | ⚔ {format_number(item['military_points'])}"
                f" | 📚 {format_number(item['research_points'])}"
            ),
            "",
        ])

        if item["owner_id"] == callback.from_user.id:
            own_position = position

    if own_position:
        lines.append(
            f"📍 Tu posición: <b>#{own_position}</b>"
        )

    lines.extend([
        "",
        "<i>La puntuación se basa en la inversión "
        "acumulada en infraestructura y ejército, "
        "además del progreso tecnológico.</i>",
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )

from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.services.battle import (
    get_battle_targets,
    resolve_battle,
)

from bot.keyboards.battle import (
    battle_targets_keyboard,
    battle_confirm_keyboard,
    battle_back_keyboard,
)


router = Router()


def number(value):
    return f"{int(value):,}".replace(",", ".")


def format_battle_report(result):
    attacker = escape(result["attacker_name"])
    defender = escape(result["defender_name"])

    if result["attacker_wins"]:
        outcome = "🏆 <b>VICTORIA</b>"
        winner = attacker
    else:
        outcome = "🛡 <b>DERROTA</b>"
        winner = defender

    lines = [
        "📜 <b>INFORME DE BATALLA</b>",
        "",
        outcome,
        f"Vencedor: <b>{winner}</b>",
        "",
        "⚔ <b>FUERZAS ENFRENTADAS</b>",
        f"Atacante: {number(result['attacker_power'])}",
        f"Defensor: {number(result['defender_power'])}",
        "",
        "📉 <b>PÉRDIDAS</b>",
        (
            f"{attacker}: "
            f"{number(result['attacker_losses'])} unidades"
        ),
        (
            f"{defender}: "
            f"{number(result['defender_losses'])} unidades"
        ),
    ]

    if result["attacker_wins"]:
        damage = result["infrastructure_damage"] * 100

        lines.extend([
            "",
            "🏗 <b>DAÑOS A LA INFRAESTRUCTURA</b>",
            (
                f"Valor anterior: "
                f"{number(result['infrastructure_before'])}"
            ),
            (
                f"Valor posterior: "
                f"{number(result['infrastructure_after'])}"
            ),
            f"Daño total: <b>{damage:.2f}%</b>",
        ])

        if result["vassalage_unlocked"]:
            lines.extend([
                "",
                "👑 <b>REQUISITO DE VASALLAJE ALCANZADO</b>",
                (
                    "Has destruido al menos el 50% del valor "
                    "de la infraestructura inicial."
                ),
                (
                    "Ahora puedes solicitar que este reino "
                    "se convierta en tu vasallo."
                ),
                (
                    "La relación solo se establecerá si "
                    "el otro jugador acepta."
                ),
            ])

    lines.extend([
        "",
        f"Identificador de batalla: #{result['battle_id']}",
    ])

    return "\n".join(lines)


@router.callback_query(F.data == "battle")
async def battle_menu(callback: CallbackQuery):
    data = await get_battle_targets(callback.from_user.id)

    if not data:
        await callback.answer(
            "Primero debes fundar un reino.",
            show_alert=True,
        )
        return

    targets = data["targets"]

    await callback.answer()

    if not targets:
        await callback.message.edit_text(
            "⚔ <b>CAMPAÑAS MILITARES</b>\n\n"
            "No hay otros reinos disponibles como objetivo.",
        )
        return

    lines = [
        "⚔ <b>CAMPAÑAS MILITARES</b>",
        "",
        "Selecciona el reino al que deseas enfrentarte.",
        "",
        "<i>La batalla se resolverá automáticamente "
        "según la fuerza de ambos ejércitos.</i>",
    ]

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=battle_targets_keyboard(targets),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("battle:target:"))
async def battle_target(callback: CallbackQuery):
    try:
        realm_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer(
            "Objetivo no válido.",
            show_alert=True,
        )
        return

    data = await get_battle_targets(callback.from_user.id)

    if not data:
        await callback.answer(
            "No tienes un reino.",
            show_alert=True,
        )
        return

    target = next(
        (
            item for item in data["targets"]
            if item["id"] == realm_id
        ),
        None,
    )

    if not target:
        await callback.answer(
            "Este objetivo ya no está disponible.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "⚔ <b>CONFIRMAR CAMPAÑA</b>\n\n"
        f"Reino objetivo: <b>{escape(target['name'])}</b>\n"
        f"Nivel: {target['level']}\n"
        f"Poder general: {number(target['power'])}\n\n"
        "La resolución será automática.\n"
        "Las tropas podrán sufrir pérdidas y, "
        "si vences, podrás dañar su infraestructura.\n\n"
        "<b>¿Deseas iniciar la batalla?</b>",
        reply_markup=battle_confirm_keyboard(realm_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("battle:confirm:"))
async def battle_confirm(callback: CallbackQuery):
    try:
        defender_realm_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Objetivo no válido.",
            show_alert=True,
        )
        return

    await callback.answer("Resolviendo batalla...")

    success, result = await resolve_battle(
        callback.from_user.id,
        defender_realm_id,
    )

    if not success:
        await callback.message.edit_text(
            f"⚠️ <b>No se pudo iniciar la batalla</b>\n\n"
            f"{escape(result)}",
            parse_mode="HTML",
            reply_markup=battle_back_keyboard(),
        )
        return

    await callback.message.edit_text(
        format_battle_report(result),
        parse_mode="HTML",
        reply_markup=battle_back_keyboard(),
    )

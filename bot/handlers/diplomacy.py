from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import get_pool
from bot.services.vassalage import (
    get_vassalage_data,
    decide_vassalage_request,
)


router = Router()


def diplomacy_keyboard(data):
    builder = InlineKeyboardBuilder()

    for request in data["incoming"]:
        request_id = request["id"]

        builder.button(
            text=f"✓ Aceptar vasallaje #{request_id}",
            callback_data=f"diplomacy:vassal:accept:{request_id}",
        )

        builder.button(
            text=f"✕ Rechazar #{request_id}",
            callback_data=f"diplomacy:vassal:reject:{request_id}",
        )

    for invitation in data["alliance_invitations"]:
        invitation_id = invitation["id"]

        builder.button(
            text=f"✓ Unirse a {invitation['alliance_name']}",
            callback_data=f"diplomacy:alliance:accept:{invitation_id}",
        )

        builder.button(
            text=f"✕ Rechazar invitación #{invitation_id}",
            callback_data=f"diplomacy:alliance:reject:{invitation_id}",
        )

    builder.button(
        text="🔄 Actualizar diplomacia",
        callback_data="diplomacy",
    )

    builder.button(
        text="↩ Menú principal",
        callback_data="main_menu",
    )

    builder.adjust(1)

    return builder.as_markup()


async def get_alliance_data(connection, user_id):
    alliance = await connection.fetchrow(
        """
        SELECT
            a.id,
            a.name,
            a.leader_id,
            COUNT(am.player_id) AS member_count
        FROM alliances a
        LEFT JOIN alliance_members am
            ON am.alliance_id = a.id
        WHERE a.leader_id = $1
           OR am.player_id = $1
        GROUP BY a.id, a.name, a.leader_id
        LIMIT 1
        """,
        user_id,
    )

    invitations = await connection.fetch(
        """
        SELECT
            invitation.id,
            alliance.name AS alliance_name,
            inviter.first_name AS inviter_name
        FROM alliance_invitations invitation
        JOIN alliances alliance
            ON alliance.id = invitation.alliance_id
        JOIN players inviter
            ON inviter.id = invitation.invited_by
        WHERE invitation.player_id = $1
          AND invitation.status = 'pending'
        ORDER BY invitation.created_at DESC
        LIMIT 10
        """,
        user_id,
    )

    return alliance, invitations


async def render_diplomacy(
    callback: CallbackQuery,
    answer=True,
):
    pool = await get_pool()

    async with pool.acquire() as connection:
        data = await get_vassalage_data(
            callback.from_user.id
        )

        alliance, alliance_invitations = await get_alliance_data(
            connection,
            callback.from_user.id,
        )

    if data is None:
        if answer:
            await callback.answer()

        await callback.message.edit_text(
            "👑 <b>DIPLOMACIA REAL</b>\n\n"
            "Todavía no tienes un reino fundado.\n"
            "Funda tu dominio antes de establecer "
            "relaciones diplomáticas.",
            reply_markup=InlineKeyboardBuilder().button(
                text="↩ Menú principal",
                callback_data="main_menu",
            ).as_markup(),
        )
        return

    data["alliance_invitations"] = alliance_invitations

    lines = [
        "👑 <b>DIPLOMACIA REAL</b>",
        "",
        f"🏰 Reino: <b>{escape(data['realm']['name'])}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🤝 <b>ALIANZAS</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    if alliance:
        role = (
            "Líder"
            if alliance["leader_id"] == callback.from_user.id
            else "Miembro"
        )

        lines.extend([
            f"Nombre: <b>{escape(alliance['name'])}</b>",
            f"Tu posición: <b>{role}</b>",
            f"Integrantes registrados: <b>{alliance['member_count']}</b>",
        ])
    else:
        lines.append(
            "<i>No perteneces a ninguna alianza.</i>"
        )

    if alliance_invitations:
        lines.extend([
            "",
            "📨 <b>INVITACIONES A ALIANZAS</b>",
        ])

        for invitation in alliance_invitations:
            lines.append(
                f"• <b>{escape(invitation['alliance_name'])}</b>"
                f" — invitación de "
                f"{escape(invitation['inviter_name'])}"
            )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "⚜ <b>VASALLAJE</b>",
        "━━━━━━━━━━━━━━━━━━",
    ])

    if data["lord"]:
        lines.append(
            "Señor feudal: "
            f"<b>{escape(data['lord']['name'])}</b>"
        )
        lines.append(
            "<i>Tu reino forma parte de un dominio feudal.</i>"
        )
    else:
        lines.append(
            "<b>Tu reino es independiente.</b>"
        )

    lines.extend([
        "",
        f"🏰 <b>Vasallos: {len(data['vassals'])}</b>",
    ])

    if data["vassals"]:
        for vassal in data["vassals"]:
            lines.append(
                f"• {escape(vassal['name'])}"
            )
    else:
        lines.append(
            "<i>No tienes reinos vasallos.</i>"
        )

    if data["incoming"]:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            "📜 <b>SOLICITUDES DE VASALLAJE</b>",
            "━━━━━━━━━━━━━━━━━━",
        ])

        for request in data["incoming"]:
            percentage = int(
                float(request["destruction_ratio"]) * 100
            )

            lines.append(
                f"• <b>{escape(request['lord_name'])}</b>"
                f"\n  Destrucción acreditada: {percentage}%"
                f"\n  Solicitud #{request['id']}"
            )

    if data["outgoing"]:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            "📤 <b>SOLICITUDES ENVIADAS</b>",
            "━━━━━━━━━━━━━━━━━━",
        ])

        status_labels = {
            "pending": "Pendiente",
            "accepted": "Aceptada",
            "rejected": "Rechazada",
            "cancelled": "Cancelada",
        }

        for request in data["outgoing"]:
            status = status_labels.get(
                request["status"],
                request["status"],
            )

            lines.append(
                f"• {escape(request['vassal_name'])}: "
                f"<b>{status}</b>"
            )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "<i>Las relaciones feudales y las alianzas "
        "se administran desde este apartado.</i>",
    ])

    if answer:
        await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=diplomacy_keyboard(data),
    )


@router.callback_query(F.data == "diplomacy")
async def diplomacy_handler(callback: CallbackQuery):
    await render_diplomacy(callback)


@router.callback_query(
    F.data.startswith("diplomacy:vassal:")
)
async def vassalage_decision_handler(
    callback: CallbackQuery,
):
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer(
            "Solicitud no válida.",
            show_alert=True,
        )
        return

    action = parts[2]

    try:
        request_id = int(parts[3])
    except ValueError:
        await callback.answer(
            "Identificador no válido.",
            show_alert=True,
        )
        return

    if action not in {"accept", "reject"}:
        await callback.answer(
            "Acción no válida.",
            show_alert=True,
        )
        return

    success, message = await decide_vassalage_request(
        request_id,
        callback.from_user.id,
        action == "accept",
    )

    await callback.answer(
        message,
        show_alert=not success,
    )

    if success:
        await render_diplomacy(
            callback,
            answer=False,
        )


@router.callback_query(
    F.data.startswith("diplomacy:alliance:")
)
async def alliance_invitation_handler(
    callback: CallbackQuery,
):
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer(
            "Invitación no válida.",
            show_alert=True,
        )
        return

    action = parts[2]

    try:
        invitation_id = int(parts[3])
    except ValueError:
        await callback.answer(
            "Identificador no válido.",
            show_alert=True,
        )
        return

    if action not in {"accept", "reject"}:
        await callback.answer(
            "Acción no válida.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            invitation = await connection.fetchrow(
                """
                SELECT
                    id,
                    alliance_id
                FROM alliance_invitations
                WHERE id = $1
                  AND player_id = $2
                  AND status = 'pending'
                FOR UPDATE
                """,
                invitation_id,
                callback.from_user.id,
            )

            if not invitation:
                await callback.answer(
                    "La invitación ya no está disponible.",
                    show_alert=True,
                )
                return

            if action == "accept":
                membership = await connection.fetchrow(
                    """
                    SELECT alliance_id
                    FROM alliance_members
                    WHERE player_id = $1
                    """,
                    callback.from_user.id,
                )

                if membership:
                    await callback.answer(
                        "Ya perteneces a una alianza.",
                        show_alert=True,
                    )
                    return

                await connection.execute(
                    """
                    INSERT INTO alliance_members (
                        alliance_id,
                        player_id
                    )
                    VALUES ($1, $2)
                    """,
                    invitation["alliance_id"],
                    callback.from_user.id,
                )

                status = "accepted"
                result_message = (
                    "Te has unido a la alianza."
                )

            else:
                status = "rejected"
                result_message = (
                    "Has rechazado la invitación."
                )

            await connection.execute(
                """
                UPDATE alliance_invitations
                SET status = $1,
                    decided_at = NOW()
                WHERE id = $2
                """,
                status,
                invitation_id,
            )

    await callback.answer(
        result_message,
        show_alert=True,
    )

    await render_diplomacy(
        callback,
        answer=False,
    )

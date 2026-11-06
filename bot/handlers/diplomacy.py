from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.connection import get_pool
from bot.services.vassalage import (
    get_vassalage_data,
    decide_vassalage_request,
    grant_independence,
)


router = Router()


class AllianceCreation(StatesGroup):
    waiting_name = State()



def diplomacy_keyboard(data):
    builder = InlineKeyboardBuilder()

    for vassal in data["vassals"]:
        builder.button(
            text=(
                "⚖️ Independencia: "
                f"{vassal['name']}"
            ),
            callback_data=(
                "diplomacy:vassal:release:"
                f"{vassal['vassal_realm_id']}"
            ),
        )

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

    alliance = data.get("alliance")

    if alliance:
        builder.button(
            text="⚙️ Administrar alianza",
            callback_data="alliance:manage",
        )
    else:
        builder.button(
            text="🏰 Fundar alianza",
            callback_data="alliance:create",
        )

    if alliance:
        builder.button(
            text="📜 Tratados diplomáticos",
            callback_data="alliance:treaties",
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
    data["alliance"] = alliance

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

        members = await connection.fetch(
            """
            SELECT p.id, p.display_name
            FROM alliance_members am
            JOIN players p ON p.id = am.player_id
            WHERE am.alliance_id = $1
            ORDER BY CASE WHEN p.id = $2 THEN 0 ELSE 1 END, am.joined_at
            """,
            alliance["id"],
            alliance["leader_id"],
        )

        lines.append("")
        lines.append("<b>Integrantes:</b>")

        for member in members:
            label = " (Líder)" if member["id"] == alliance["leader_id"] else ""
            lines.append(f"• {escape(member['display_name'])}{label}")
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

            builder_button = InlineKeyboardBuilder()

            builder_button.button(
                text=(
                    "⚖️ Conceder independencia: "
                    f"{vassal['name']}"
                ),
                callback_data=(
                    "diplomacy:vassal:release:"
                    f"{vassal['vassal_realm_id']}"
                ),
            )

            builder_button.adjust(1)

            # Añadir el botón a la lista de acciones
            # de diplomacia existente.
            diplomacy_keyboard_builder = None
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
    F.data.regexp(
        r"^diplomacy:vassal:(accept|reject):\d+$"
    )
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
    F.data.startswith("diplomacy:vassal:release:")
)
async def vassalage_release_handler(
    callback: CallbackQuery,
):
    try:
        vassal_realm_id = int(
            callback.data.split(":")[3]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Reino vasallo no válido.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        lord_realm_id = await connection.fetchval(
            """
            SELECT id
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id,
        )

    if not lord_realm_id:
        await callback.answer(
            "No tienes un reino fundado.",
            show_alert=True,
        )
        return

    success, message = await grant_independence(
        lord_realm_id,
        vassal_realm_id,
        callback.from_user.id,
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


@router.callback_query(F.data == "alliance:create")
async def alliance_create_start(callback: CallbackQuery, state: FSMContext):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            "SELECT id FROM realms WHERE owner_id = $1",
            callback.from_user.id,
        )
        membership = await connection.fetchrow(
            "SELECT player_id FROM alliance_members WHERE player_id = $1",
            callback.from_user.id,
        )

    if not realm:
        await callback.answer("Primero funda un reino.", show_alert=True)
        return

    if membership:
        await callback.answer("Ya perteneces a una alianza.", show_alert=True)
        return

    await state.set_state(AllianceCreation.waiting_name)
    await callback.answer()
    await callback.message.answer(
        "Escribe el nombre de tu alianza (3–30 caracteres)."
    )


@router.message(AllianceCreation.waiting_name)
async def alliance_create_finish(message: Message, state: FSMContext):
    name = (message.text or "").strip()

    if not 3 <= len(name) <= 30:
        await message.answer("El nombre debe tener entre 3 y 30 caracteres.")
        return

    pool = await get_pool()

    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                member = await connection.fetchrow(
                    """
                    SELECT player_id
                    FROM alliance_members
                    WHERE player_id = $1
                    FOR UPDATE
                    """,
                    message.from_user.id,
                )

                if member:
                    await state.clear()
                    await message.answer("Ya perteneces a una alianza.")
                    return

                alliance = await connection.fetchrow(
                    """
                    INSERT INTO alliances (name, leader_id)
                    VALUES ($1, $2)
                    RETURNING id
                    """,
                    name,
                    message.from_user.id,
                )

                await connection.execute(
                    """
                    INSERT INTO alliance_members (alliance_id, player_id)
                    VALUES ($1, $2)
                    """,
                    alliance["id"],
                    message.from_user.id,
                )

                await connection.execute(
                    """
                    INSERT INTO alliance_events
                        (alliance_id, actor_id, event_type, details)
                    VALUES ($1, $2, 'created', $3)
                    """,
                    alliance["id"],
                    message.from_user.id,
                    name,
                )

    except Exception as exc:
        if "unique" in str(exc).lower():
            await message.answer(
                "El nombre está ocupado o ya perteneces a una alianza."
            )
            return
        raise

    await state.clear()
    await message.answer(
        "Alianza fundada correctamente. Abre Diplomacia para administrarla."
    )


@router.callback_query(F.data == "alliance:manage")
async def alliance_manage(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        alliance = await connection.fetchrow(
            """
            SELECT a.id, a.name, a.leader_id
            FROM alliances a
            JOIN alliance_members am ON am.alliance_id = a.id
            WHERE am.player_id = $1
            """,
            callback.from_user.id,
        )

        if not alliance:
            await callback.answer(
                "No perteneces a una alianza.",
                show_alert=True,
            )
            return

        members = await connection.fetch(
            """
            SELECT p.id, p.display_name
            FROM alliance_members am
            JOIN players p ON p.id = am.player_id
            WHERE am.alliance_id = $1
            ORDER BY CASE WHEN p.id = $2 THEN 0 ELSE 1 END, am.joined_at
            """,
            alliance["id"],
            alliance["leader_id"],
        )

        invites = await connection.fetch(
            """
            SELECT p.id, p.display_name
            FROM players p
            JOIN realms r ON r.owner_id = p.id
            WHERE p.id <> $1
              AND NOT EXISTS (
                  SELECT 1 FROM alliance_members am
                  WHERE am.player_id = p.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM alliance_invitations i
                  WHERE i.alliance_id = $2
                    AND i.player_id = p.id
                    AND i.status = 'pending'
              )
            ORDER BY p.display_name
            LIMIT 20
            """,
            callback.from_user.id,
            alliance["id"],
        )

    builder = InlineKeyboardBuilder()

    if callback.from_user.id == alliance["leader_id"]:
        for player in invites:
            builder.button(
                text=f"➕ Invitar {player['display_name']}",
                callback_data=f"alliance:invite:{player['id']}",
            )

        for member in members:
            if member["id"] != alliance["leader_id"]:
                builder.button(
                    text=f"🚪 Expulsar {member['display_name']}",
                    callback_data=f"alliance:kick:{member['id']}",
                )
                builder.button(
                    text=f"👑 Ceder liderazgo a {member['display_name']}",
                    callback_data=f"alliance:transfer:{member['id']}",
                )

        builder.button(
            text="🗑 Disolver alianza",
            callback_data="alliance:dissolve",
        )
    else:
        builder.button(
            text="🚶 Abandonar alianza",
            callback_data="alliance:leave",
        )

    builder.button(text="↩ Diplomacia", callback_data="diplomacy")
    builder.adjust(1)

    await callback.answer()
    await callback.message.edit_text(
        f"⚙️ <b>ADMINISTRACIÓN DE ALIANZA</b>\n\n"
        f"🏰 {escape(alliance['name'])}\n"
        f"👥 Miembros: {len(members)}\n\n"
        "Selecciona una acción:",
        reply_markup=builder.as_markup(),
    )


async def alliance_member_action(
    callback: CallbackQuery,
    target_id: int,
    action: str,
):
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            alliance = await connection.fetchrow(
                """
                SELECT a.id, a.leader_id
                FROM alliances a
                JOIN alliance_members am ON am.alliance_id = a.id
                WHERE am.player_id = $1
                FOR UPDATE OF a
                """,
                callback.from_user.id,
            )

            if not alliance:
                return False, "No perteneces a una alianza."

            if action in {"kick", "transfer"}:
                if alliance["leader_id"] != callback.from_user.id:
                    return False, "Solo el líder puede realizar esa acción."

            if action != "leave" and target_id == callback.from_user.id:
                return False, "No puedes realizar esa acción sobre ti mismo."

            target = await connection.fetchrow(
                """
                SELECT player_id
                FROM alliance_members
                WHERE alliance_id = $1 AND player_id = $2
                FOR UPDATE
                """,
                alliance["id"],
                target_id,
            )

            if not target:
                return False, "Ese jugador no pertenece a tu alianza."

            if action == "kick":
                await connection.execute(
                    """
                    DELETE FROM alliance_members
                    WHERE alliance_id = $1 AND player_id = $2
                    """,
                    alliance["id"],
                    target_id,
                )
                event = "member_kicked"

            elif action == "transfer":
                await connection.execute(
                    """
                    UPDATE alliances
                    SET leader_id = $1
                    WHERE id = $2
                    """,
                    target_id,
                    alliance["id"],
                )
                event = "leadership_transferred"

            else:
                await connection.execute(
                    """
                    DELETE FROM alliance_members
                    WHERE alliance_id = $1 AND player_id = $2
                    """,
                    alliance["id"],
                    callback.from_user.id,
                )
                event = "member_left"

            await connection.execute(
                """
                INSERT INTO alliance_events
                    (alliance_id, actor_id, event_type, details)
                VALUES ($1, $2, $3, $4)
                """,
                alliance["id"],
                callback.from_user.id,
                event,
                str(target_id),
            )

    messages = {
        "kick": "Jugador expulsado.",
        "transfer": "Liderazgo transferido.",
        "leave": "Has abandonado la alianza.",
    }

    return True, messages[action]


@router.callback_query(F.data.startswith("alliance:invite:"))
async def alliance_invite_player(callback: CallbackQuery):
    try:
        target_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Jugador inválido.", show_alert=True)
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            alliance = await connection.fetchrow(
                """
                SELECT a.id
                FROM alliances a
                JOIN alliance_members am ON am.alliance_id = a.id
                WHERE a.leader_id = $1 AND am.player_id = $1
                FOR UPDATE OF a
                """,
                callback.from_user.id,
            )

            if not alliance:
                await callback.answer(
                    "Solo el líder puede invitar.",
                    show_alert=True,
                )
                return

            realm = await connection.fetchrow(
                "SELECT id FROM realms WHERE owner_id = $1",
                target_id,
            )

            member = await connection.fetchrow(
                "SELECT player_id FROM alliance_members WHERE player_id = $1",
                target_id,
            )

            if not realm or member or target_id == callback.from_user.id:
                await callback.answer(
                    "Jugador no disponible para invitación.",
                    show_alert=True,
                )
                return

            await connection.execute(
                """
                INSERT INTO alliance_invitations
                    (alliance_id, player_id, invited_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (alliance_id, player_id)
                    WHERE status = 'pending'
                DO NOTHING
                """,
                alliance["id"],
                target_id,
                callback.from_user.id,
            )

            await connection.execute(
                """
                INSERT INTO alliance_events
                    (alliance_id, actor_id, event_type, details)
                VALUES ($1, $2, 'invitation_sent', $3)
                """,
                alliance["id"],
                callback.from_user.id,
                str(target_id),
            )

    await callback.answer("Invitación enviada.", show_alert=True)


@router.callback_query(F.data.startswith("alliance:kick:"))
async def alliance_kick(callback: CallbackQuery):
    try:
        target = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Jugador inválido.", show_alert=True)
        return

    ok, message = await alliance_member_action(callback, target, "kick")
    await callback.answer(message, show_alert=not ok)

    if ok:
        await alliance_manage(callback)


@router.callback_query(F.data.startswith("alliance:transfer:"))
async def alliance_transfer(callback: CallbackQuery):
    try:
        target = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Jugador inválido.", show_alert=True)
        return

    ok, message = await alliance_member_action(callback, target, "transfer")
    await callback.answer(message, show_alert=not ok)

    if ok:
        await alliance_manage(callback)


@router.callback_query(F.data == "alliance:leave")
async def alliance_leave(callback: CallbackQuery):
    ok, message = await alliance_member_action(
        callback,
        callback.from_user.id,
        "leave",
    )

    await callback.answer(message, show_alert=not ok)

    if ok:
        await render_diplomacy(callback, answer=False)


@router.callback_query(F.data == "alliance:dissolve")
async def alliance_dissolve(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            alliance = await connection.fetchrow(
                """
                SELECT a.id
                FROM alliances a
                JOIN alliance_members am ON am.alliance_id = a.id
                WHERE a.leader_id = $1 AND am.player_id = $1
                FOR UPDATE OF a
                """,
                callback.from_user.id,
            )

            if not alliance:
                await callback.answer(
                    "Solo el líder puede disolver la alianza.",
                    show_alert=True,
                )
                return

            await connection.execute(
                "DELETE FROM alliances WHERE id = $1",
                alliance["id"],
            )

    await callback.answer("Alianza disuelta.", show_alert=True)
    await render_diplomacy(callback, answer=False)


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

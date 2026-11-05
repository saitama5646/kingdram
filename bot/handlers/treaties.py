
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.connection import get_pool


router = Router()

TREATY_LABELS = {
    "non_aggression": "🕊️ Pacto de no agresión",
    "trade": "🤝 Tratado comercial",
    "defense": "🛡️ Defensa mutua",
}


async def get_player_alliance(connection, player_id):
    return await connection.fetchrow(
        """
        SELECT a.id, a.name, a.leader_id
        FROM alliances a
        JOIN alliance_members am
          ON am.alliance_id = a.id
        WHERE am.player_id = $1
        """,
        player_id,
    )


@router.callback_query(F.data == "alliance:treaties")
async def treaties_menu(callback: CallbackQuery):
    pool = await get_pool()

    async with pool.acquire() as connection:
        alliance = await get_player_alliance(
            connection,
            callback.from_user.id,
        )

        if not alliance:
            await callback.answer(
                "No perteneces a una alianza.",
                show_alert=True,
            )
            return

        treaties = await connection.fetch(
            """
            SELECT
                t.id,
                t.alliance_id,
                t.other_alliance_id,
                t.treaty_type,
                t.status,
                a.name AS alliance_name,
                b.name AS other_name
            FROM alliance_treaties t
            JOIN alliances a ON a.id = t.alliance_id
            JOIN alliances b ON b.id = t.other_alliance_id
            WHERE (
                t.alliance_id = $1
                OR t.other_alliance_id = $1
            )
            AND t.status IN ('pending', 'active')
            ORDER BY t.created_at DESC
            LIMIT 30
            """,
            alliance["id"],
        )

        other_alliances = await connection.fetch(
            """
            SELECT a.id, a.name
            FROM alliances a
            WHERE a.id <> $1
              AND NOT EXISTS (
                  SELECT 1
                  FROM alliance_treaties t
                  WHERE t.status IN ('pending', 'active')
                    AND (
                        (
                            t.alliance_id = $1
                            AND t.other_alliance_id = a.id
                        )
                        OR
                        (
                            t.other_alliance_id = $1
                            AND t.alliance_id = a.id
                        )
                    )
              )
            ORDER BY a.name
            LIMIT 20
            """,
            alliance["id"],
        )

    lines = [
        "📜 <b>TRATADOS DIPLOMÁTICOS</b>",
        "",
        f"🏰 Alianza: <b>{escape(alliance['name'])}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📋 <b>ACUERDOS Y SOLICITUDES</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    builder = InlineKeyboardBuilder()

    if treaties:
        for treaty in treaties:
            incoming = (
                treaty["other_alliance_id"] == alliance["id"]
                and treaty["status"] == "pending"
            )

            partner = (
                treaty["alliance_name"]
                if treaty["other_alliance_id"] == alliance["id"]
                else treaty["other_name"]
            )

            label = TREATY_LABELS.get(
                treaty["treaty_type"],
                treaty["treaty_type"],
            )

            status = (
                "📨 Pendiente de tu respuesta"
                if incoming
                else "⏳ Pendiente"
                if treaty["status"] == "pending"
                else "✅ Vigente"
            )

            lines.append(
                f"\n• <b>{escape(partner)}</b>\n"
                f"  {label}\n"
                f"  {status}"
            )

            if incoming:
                builder.button(
                    text=f"✓ Aceptar tratado #{treaty['id']}",
                    callback_data=(
                        f"treaty:accept:{treaty['id']}"
                    ),
                )
                builder.button(
                    text=f"✕ Rechazar #{treaty['id']}",
                    callback_data=(
                        f"treaty:reject:{treaty['id']}"
                    ),
                )

            elif treaty["status"] == "active":
                builder.button(
                    text=f"⛔ Finalizar tratado #{treaty['id']}",
                    callback_data=(
                        f"treaty:end:{treaty['id']}"
                    ),
                )
    else:
        lines.append(
            "<i>No hay tratados ni solicitudes diplomáticas.</i>"
        )

    if callback.from_user.id == alliance["leader_id"]:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            "✉️ <b>PROPONER UN TRATADO</b>",
            "━━━━━━━━━━━━━━━━━━",
            "Selecciona una alianza para enviar una propuesta.",
        ])

        for other in other_alliances:
            builder.button(
                text=f"🏰 {other['name']}",
                callback_data=(
                    f"treaty:target:{other['id']}"
                ),
            )
    else:
        lines.extend([
            "",
            "<i>Solo el líder de la alianza puede "
            "proponer nuevos tratados.</i>",
        ])

    builder.button(
        text="🔄 Actualizar",
        callback_data="alliance:treaties",
    )
    builder.button(
        text="↩ Diplomacia",
        callback_data="diplomacy",
    )

    builder.adjust(1)

    await callback.answer()
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("treaty:target:"))
async def treaty_choose_type(callback: CallbackQuery):
    try:
        target_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer(
            "Alianza inválida.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        alliance = await get_player_alliance(
            connection,
            callback.from_user.id,
        )

        target = await connection.fetchrow(
            "SELECT id, name FROM alliances WHERE id = $1",
            target_id,
        )

        if (
            not alliance
            or alliance["leader_id"] != callback.from_user.id
        ):
            await callback.answer(
                "Solo el líder puede proponer tratados.",
                show_alert=True,
            )
            return

        if not target or target_id == alliance["id"]:
            await callback.answer(
                "Alianza no válida.",
                show_alert=True,
            )
            return

    builder = InlineKeyboardBuilder()

    for treaty_type, label in TREATY_LABELS.items():
        builder.button(
            text=label,
            callback_data=(
                f"treaty:send:{target_id}:{treaty_type}"
            ),
        )

    builder.button(
        text="↩ Volver",
        callback_data="alliance:treaties",
    )
    builder.adjust(1)

    await callback.answer()
    await callback.message.edit_text(
        "📜 <b>PROPUESTA DE TRATADO</b>\n\n"
        f"Alianza destinataria: <b>{escape(target['name'])}</b>\n\n"
        "Selecciona el tipo de acuerdo:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("treaty:send:"))
async def treaty_send(callback: CallbackQuery):
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer(
            "Propuesta inválida.",
            show_alert=True,
        )
        return

    try:
        target_id = int(parts[2])
    except ValueError:
        await callback.answer(
            "Alianza inválida.",
            show_alert=True,
        )
        return

    treaty_type = parts[3]

    if treaty_type not in TREATY_LABELS:
        await callback.answer(
            "Tipo de tratado inválido.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            alliance = await get_player_alliance(
                connection,
                callback.from_user.id,
            )

            if (
                not alliance
                or alliance["leader_id"] != callback.from_user.id
            ):
                await callback.answer(
                    "Solo el líder puede proponer tratados.",
                    show_alert=True,
                )
                return

            target = await connection.fetchrow(
                "SELECT id FROM alliances WHERE id = $1",
                target_id,
            )

            if not target or target_id == alliance["id"]:
                await callback.answer(
                    "Alianza no válida.",
                    show_alert=True,
                )
                return

            existing = await connection.fetchrow(
                """
                SELECT id
                FROM alliance_treaties
                WHERE status IN ('pending', 'active')
                  AND (
                      (
                          alliance_id = $1
                          AND other_alliance_id = $2
                      )
                      OR
                      (
                          alliance_id = $2
                          AND other_alliance_id = $1
                      )
                  )
                """,
                alliance["id"],
                target_id,
            )

            if existing:
                await callback.answer(
                    "Ya existe un tratado o propuesta "
                    "entre ambas alianzas.",
                    show_alert=True,
                )
                return

            await connection.execute(
                """
                INSERT INTO alliance_treaties (
                    alliance_id,
                    other_alliance_id,
                    treaty_type,
                    status
                )
                VALUES ($1, $2, $3, 'pending')
                """,
                alliance["id"],
                target_id,
                treaty_type,
            )

    await callback.answer(
        "Propuesta diplomática enviada.",
        show_alert=True,
    )
    await treaties_menu(callback)


@router.callback_query(F.data.startswith("treaty:accept:"))
@router.callback_query(F.data.startswith("treaty:reject:"))
@router.callback_query(F.data.startswith("treaty:end:"))
async def treaty_decision(callback: CallbackQuery):
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "Acción inválida.",
            show_alert=True,
        )
        return

    action = parts[1]

    try:
        treaty_id = int(parts[2])
    except ValueError:
        await callback.answer(
            "Identificador inválido.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            alliance = await get_player_alliance(
                connection,
                callback.from_user.id,
            )

            if not alliance:
                await callback.answer(
                    "No perteneces a una alianza.",
                    show_alert=True,
                )
                return

            treaty = await connection.fetchrow(
                """
                SELECT *
                FROM alliance_treaties
                WHERE id = $1
                FOR UPDATE
                """,
                treaty_id,
            )

            if not treaty:
                await callback.answer(
                    "Tratado no encontrado.",
                    show_alert=True,
                )
                return

            if action in {"accept", "reject"}:
                if (
                    treaty["other_alliance_id"]
                    != alliance["id"]
                    or treaty["status"] != "pending"
                ):
                    await callback.answer(
                        "Esta propuesta no está disponible "
                        "para tu alianza.",
                        show_alert=True,
                    )
                    return

                if alliance["leader_id"] != callback.from_user.id:
                    await callback.answer(
                        "Solo el líder puede responder.",
                        show_alert=True,
                    )
                    return

                status = (
                    "active"
                    if action == "accept"
                    else "rejected"
                )

                await connection.execute(
                    """
                    UPDATE alliance_treaties
                    SET status = $1,
                        ended_at = CASE
                            WHEN $1 = 'rejected'
                            THEN NOW()
                            ELSE NULL
                        END
                    WHERE id = $2
                    """,
                    status,
                    treaty_id,
                )

            elif action == "end":
                if (
                    alliance["id"] not in (
                        treaty["alliance_id"],
                        treaty["other_alliance_id"],
                    )
                    or treaty["status"] != "active"
                ):
                    await callback.answer(
                        "No puedes finalizar este tratado.",
                        show_alert=True,
                    )
                    return

                if alliance["leader_id"] != callback.from_user.id:
                    await callback.answer(
                        "Solo el líder puede finalizar tratados.",
                        show_alert=True,
                    )
                    return

                await connection.execute(
                    """
                    UPDATE alliance_treaties
                    SET status = 'ended',
                        ended_at = NOW()
                    WHERE id = $1
                    """,
                    treaty_id,
                )

    messages = {
        "accept": "Tratado aceptado. El acuerdo está vigente.",
        "reject": "Propuesta rechazada.",
        "end": "Tratado finalizado.",
    }

    await callback.answer(
        messages[action],
        show_alert=True,
    )
    await treaties_menu(callback)

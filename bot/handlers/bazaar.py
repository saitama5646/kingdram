from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.connection import get_pool
from bot.services.storage import get_storage_capacity


router = Router()

from bot.services.bazaar import (
    RESOURCES,
    calculate_exchange_amount,
)

PRESET_AMOUNTS = (50, 250, 1000, 5000)


def fmt(value):
    return f"{int(value):,}".replace(",", ".")

def resource_name(resource):
    info = RESOURCES[resource]
    return f"{info['icon']} {info['name']}"


def button(text, callback):
    return InlineKeyboardButton(
        text=text,
        callback_data=callback,
    )


def home_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button(
                    "⚖️ Nuevo intercambio",
                    "bazaar:start",
                )
            ],
            [
                button(
                    "↩ Economía",
                    "economy",
                )
            ],
            [
                button(
                    "⌂ Menú principal",
                    "main_menu",
                )
            ],
        ]
    )


def source_keyboard():
    rows = [
        [
            button(
                resource_name(resource),
                f"bazaar:source:{resource}",
            )
        ]
        for resource in RESOURCES
    ]

    rows.append([
        button("✖ Cancelar", "bazaar:home")
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def target_keyboard(source):
    rows = [
        [
            button(
                resource_name(target),
                f"bazaar:target:{source}:{target}",
            )
        ]
        for target in RESOURCES
        if target != source
    ]

    rows.append([
        button("↩ Cambiar recurso", "bazaar:start")
    ])

    rows.append([
        button("✖ Cancelar", "bazaar:home")
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def amount_keyboard(source, target, available):
    amounts = [
        amount
        for amount in PRESET_AMOUNTS
        if amount <= available
    ]

    if available > 0 and available not in amounts:
        amounts.append(int(available))

    amounts = sorted(set(amounts))

    rows = []

    for amount in amounts:
        received = calculate_exchange_amount(amount, source, target)

        rows.append([
            button(
                f"📦 {fmt(amount)} → {fmt(received)}",
                f"bazaar:amount:{source}:{target}:{amount}",
            )
        ])

    rows.append([
        button("↩ Cambiar recurso", "bazaar:start")
    ])

    rows.append([
        button("✖ Cancelar", "bazaar:home")
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirmation_keyboard(source, target, amount):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button(
                    "✅ Confirmar intercambio",
                    f"bazaar:confirm:{source}:{target}:{amount}",
                )
            ],
            [
                button(
                    "↩ Cambiar cantidad",
                    f"bazaar:amountmenu:{source}:{target}",
                )
            ],
            [
                button(
                    "✖ Cancelar",
                    "bazaar:home",
                )
            ],
        ]
    )


async def get_realm_data(user_id):
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
                p.food
            FROM realms r
            JOIN resources p
              ON p.realm_id = r.id
            WHERE r.owner_id = $1
            """,
            user_id,
        )

        if not realm:
            return None, None

        buildings = await connection.fetch(
            """
            SELECT building_type, level
            FROM buildings
            WHERE realm_id = $1
            """,
            realm["id"],
        )

    return realm, buildings


async def show_bazaar(callback):
    realm, _ = await get_realm_data(
        callback.from_user.id
    )

    if not realm:
        await callback.answer(
            "Primero debes fundar tu reino.",
            show_alert=True,
        )
        return

    lines = [
        "🏺 <b>BAZAR DEL REINO</b>",
        "",
        f"🏰 Dominio: <b>{realm['name']}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📦 <b>EXISTENCIAS</b>",
        "",
    ]

    for resource in RESOURCES:
        lines.append(
            f"{resource_name(resource)}: "
            f"<b>{fmt(realm[resource])}</b>"
        )

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "⚖️ <b>INTERCAMBIO COMERCIAL</b>",
        "",
        "Intercambia excedentes por los recursos "
        "que necesitas.",
        "",
        "<i>La madera es abundante, la piedra tiene un valor intermedio, los alimentos son esenciales para las expediciones y el oro es el recurso más escaso.</i>",
    ])

    await callback.answer()

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=home_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(
    F.data.in_({"bazaar", "bazaar:home"})
)
async def bazaar_home(callback: CallbackQuery):
    await show_bazaar(callback)


@router.callback_query(F.data == "bazaar:start")
async def bazaar_start(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "🏺 <b>BAZAR DEL REINO</b>\n\n"
        "📤 <b>¿Qué recurso entregarás?</b>\n\n"
        "Selecciona uno de tus recursos.",
        reply_markup=source_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bazaar:source:"))
async def bazaar_source(callback: CallbackQuery):
    source = callback.data.split(":")[2]

    if source not in RESOURCES:
        await callback.answer(
            "Recurso inválido.",
            show_alert=True,
        )
        return

    realm, _ = await get_realm_data(
        callback.from_user.id
    )

    if not realm:
        await callback.answer(
            "No tienes un reino.",
            show_alert=True,
        )
        return

    if realm[source] <= 0:
        await callback.answer(
            "No tienes existencias de ese recurso.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "🏺 <b>BAZAR DEL REINO</b>\n\n"
        f"📤 Entregarás: <b>{resource_name(source)}</b>\n"
        f"📦 Disponible: <b>{fmt(realm[source])}</b>\n\n"
        "📥 <b>¿Qué recurso deseas recibir?</b>",
        reply_markup=target_keyboard(source),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bazaar:target:"))
async def bazaar_target(callback: CallbackQuery):
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer(
            "Selección inválida.",
            show_alert=True,
        )
        return

    source, target = parts[2], parts[3]

    if (
        source not in RESOURCES
        or target not in RESOURCES
        or source == target
    ):
        await callback.answer(
            "Intercambio inválido.",
            show_alert=True,
        )
        return

    realm, _ = await get_realm_data(
        callback.from_user.id
    )

    if not realm:
        await callback.answer(
            "No tienes un reino.",
            show_alert=True,
        )
        return

    available = int(realm[source])

    if available <= 0:
        await callback.answer(
            "No tienes recursos disponibles.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "🏺 <b>BAZAR DEL REINO</b>\n\n"
        f"📤 Entregar: <b>{resource_name(source)}</b>\n"
        f"📥 Recibir: <b>{resource_name(target)}</b>\n\n"
        f"📦 Existencias: <b>{fmt(available)}</b>\n\n"
        "📏 <b>Selecciona cuánto entregar:</b>\n"
        "<i>La cantidad recibida se muestra en cada botón.</i>",
        reply_markup=amount_keyboard(
            source,
            target,
            available,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bazaar:amount:"))
async def bazaar_amount(callback: CallbackQuery):
    parts = callback.data.split(":")

    if len(parts) != 5:
        await callback.answer(
            "Selección inválida.",
            show_alert=True,
        )
        return

    source, target = parts[2], parts[3]

    try:
        amount = int(parts[4])
    except ValueError:
        await callback.answer(
            "Cantidad inválida.",
            show_alert=True,
        )
        return

    if (
        source not in RESOURCES
        or target not in RESOURCES
        or source == target
        or amount <= 0
    ):
        await callback.answer(
            "Intercambio inválido.",
            show_alert=True,
        )
        return

    realm, _ = await get_realm_data(
        callback.from_user.id
    )

    if not realm:
        await callback.answer(
            "No tienes un reino.",
            show_alert=True,
        )
        return

    if amount > realm[source]:
        await callback.answer(
            "Tus existencias han cambiado. "
            "Selecciona una cantidad menor.",
            show_alert=True,
        )
        return

    received = calculate_exchange_amount(amount, source, target)

    if received <= 0:
        await callback.answer(
            "La cantidad no permite recibir "
            "una unidad del recurso elegido.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "🏺 <b>CONFIRMAR INTERCAMBIO</b>\n\n"
        f"📤 Entregarás:\n"
        f"<b>{fmt(amount)} {RESOURCES[source]['name']}</b>\n\n"
        f"📥 Recibirás:\n"
        f"<b>{fmt(received)} {RESOURCES[target]['name']}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "¿Confirmas esta operación?",
        reply_markup=confirmation_keyboard(
            source,
            target,
            amount,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bazaar:amountmenu:"))
async def bazaar_amount_menu(callback: CallbackQuery):
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer(
            "Selección inválida.",
            show_alert=True,
        )
        return

    source, target = parts[2], parts[3]

    if (
        source not in RESOURCES
        or target not in RESOURCES
        or source == target
    ):
        await callback.answer(
            "Intercambio inválido.",
            show_alert=True,
        )
        return

    realm, _ = await get_realm_data(
        callback.from_user.id
    )

    if not realm:
        await callback.answer(
            "No tienes un reino.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "🏺 <b>BAZAR DEL REINO</b>\n\n"
        f"📤 Entregar: <b>{resource_name(source)}</b>\n"
        f"📥 Recibir: <b>{resource_name(target)}</b>\n\n"
        f"📦 Disponible: <b>{fmt(realm[source])}</b>\n\n"
        "Selecciona la nueva cantidad:",
        reply_markup=amount_keyboard(
            source,
            target,
            int(realm[source]),
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bazaar:confirm:"))
async def bazaar_confirm(callback: CallbackQuery):
    parts = callback.data.split(":")

    if len(parts) != 5:
        await callback.answer(
            "Intercambio inválido.",
            show_alert=True,
        )
        return

    source, target = parts[2], parts[3]

    try:
        amount = int(parts[4])
    except ValueError:
        await callback.answer(
            "Cantidad inválida.",
            show_alert=True,
        )
        return

    if (
        source not in RESOURCES
        or target not in RESOURCES
        or source == target
        or amount <= 0
    ):
        await callback.answer(
            "Intercambio inválido.",
            show_alert=True,
        )
        return

    received = calculate_exchange_amount(amount, source, target)

    if received <= 0:
        await callback.answer(
            "Cantidad recibida inválida.",
            show_alert=True,
        )
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
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
                    "No tienes un reino.",
                    show_alert=True,
                )
                return

            resources = await connection.fetchrow(
                """
                SELECT wood, stone, gold, food
                FROM resources
                WHERE realm_id = $1
                FOR UPDATE
                """,
                realm["id"],
            )

            if not resources:
                await callback.answer(
                    "No se encontraron tus recursos.",
                    show_alert=True,
                )
                return

            if resources[source] < amount:
                await callback.answer(
                    "Existencias insuficientes.",
                    show_alert=True,
                )
                return

            buildings = await connection.fetch(
                """
                SELECT building_type, level
                FROM buildings
                WHERE realm_id = $1
                """,
                realm["id"],
            )

            capacity = get_storage_capacity(buildings)

            if resources[target] + received > capacity[target]:
                space = max(
                    0,
                    capacity[target] - resources[target],
                )

                await callback.answer(
                    "Almacenamiento insuficiente. "
                    f"Espacio: {fmt(space)}.",
                    show_alert=True,
                )
                return

            new_source = resources[source] - amount
            new_target = resources[target] + received

            await connection.execute(
                f"""
                UPDATE resources
                SET {source} = $1,
                    {target} = $2,
                    updated_at = NOW()
                WHERE realm_id = $3
                """,
                new_source,
                new_target,
                realm["id"],
            )

    await callback.answer(
        "Intercambio realizado correctamente."
    )

    await callback.message.edit_text(
        "🏺 <b>INTERCAMBIO COMPLETADO</b>\n\n"
        "⚖️ La operación se realizó correctamente.\n\n"
        f"📤 Entregaste:\n"
        f"<b>{fmt(amount)} {RESOURCES[source]['name']}</b>\n\n"
        f"📥 Recibiste:\n"
        f"<b>{fmt(received)} {RESOURCES[target]['name']}</b>\n\n"
        "Tus recursos han sido actualizados.",
        reply_markup=home_keyboard(),
        parse_mode="HTML",
    )

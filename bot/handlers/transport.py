from html import escape

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.connection import get_pool
from bot.services.transport import create_transport

router = Router()


class TransportStates(StatesGroup):
    selecting_target = State()
    entering_cargo = State()


def target_keyboard(rows):
    buttons = []

    for row in rows:
        buttons.append([
            InlineKeyboardButton(
                text=f"🏰 {row['name']}",
                callback_data=f"transport:target:{row['id']}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="↩ Menú principal",
            callback_data="main_menu",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "transport")
async def transport_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    pool = await get_pool()

    async with pool.acquire() as connection:
        own_realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            callback.from_user.id,
        )

        if not own_realm:
            await callback.message.edit_text(
                "Primero debes fundar tu reino."
            )
            return

        targets = await connection.fetch(
            """
            SELECT id, name
            FROM realms
            WHERE id <> $1
            ORDER BY name
            """,
            own_realm["id"],
        )

    if not targets:
        await callback.message.edit_text(
            "Todavía no existen otros reinos a los que enviar recursos."
        )
        return

    await state.clear()
    await state.set_state(TransportStates.selecting_target)

    await callback.message.edit_text(
        "📦 <b>TRANSPORTE DE RECURSOS</b>\n\n"
        f"🏰 Reino de origen: <b>{escape(own_realm['name'])}</b>\n\n"
        "Selecciona el reino que recibirá los recursos.",
        reply_markup=target_keyboard(targets),
        parse_mode="HTML",
    )


@router.callback_query(
    TransportStates.selecting_target,
    F.data.startswith("transport:target:"),
)
async def select_target(callback: CallbackQuery, state: FSMContext):
    try:
        target_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Destino incorrecto.", show_alert=True)
        return

    pool = await get_pool()

    async with pool.acquire() as connection:
        target = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE id = $1
            """,
            target_id,
        )

    if not target:
        await callback.answer("El reino ya no existe.", show_alert=True)
        return

    await state.update_data(target_realm_id=target_id)
    await state.set_state(TransportStates.entering_cargo)

    await callback.answer()

    await callback.message.edit_text(
        "📦 <b>CONFIGURAR CARGA</b>\n\n"
        f"🏰 Destino: <b>{escape(target['name'])}</b>\n\n"
        "Escribe cinco números separados por espacios:\n"
        "<code>caravanas madera piedra oro alimentos</code>\n\n"
        "Ejemplo:\n"
        "<code>2 500 300 100 200</code>\n\n"
        "Cada caravana transporta hasta 1.000 recursos "
        "en total.\n"
        "Escribe <code>cancelar</code> para abandonar.",
        parse_mode="HTML",
    )


@router.message(TransportStates.entering_cargo)
async def receive_cargo(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower()

    if raw == "cancelar":
        await state.clear()
        await message.answer("Transporte cancelado.")
        return

    parts = raw.split()

    if len(parts) != 5:
        await message.answer(
            "Formato incorrecto.\n"
            "Escribe: caravanas madera piedra oro alimentos\n"
            "Ejemplo: <code>2 500 300 100 200</code>",
            parse_mode="HTML",
        )
        return

    try:
        values = [int(value) for value in parts]
    except ValueError:
        await message.answer("Todos los valores deben ser enteros.")
        return

    if any(value < 0 for value in values):
        await message.answer("No puedes utilizar valores negativos.")
        return

    caravans, wood, stone, gold, food = values

    data = await state.get_data()
    target_id = data.get("target_realm_id")

    success, result = await create_transport(
        message.from_user.id,
        target_id,
        caravans,
        {
            "wood": wood,
            "stone": stone,
            "gold": gold,
            "food": food,
        },
    )

    if not success:
        await message.answer(
            f"⚠️ <b>No se pudo iniciar el transporte</b>\n\n"
            f"{escape(str(result))}",
            parse_mode="HTML",
        )
        return

    await state.clear()

    await message.answer(
        "📦 <b>TRANSPORTE INICIADO</b>\n\n"
        f"🆔 Misión: <b>#{result['mission_id']}</b>\n"
        f"🏰 Origen: <b>{escape(result['origin_name'])}</b>\n"
        f"🏰 Destino: <b>{escape(result['target_name'])}</b>\n"
        f"🚚 Caravanas: <b>{result['caravans']:,}</b>\n"
        f"📦 Capacidad: <b>{result['capacity']:,}</b>\n"
        f"📏 Distancia: <b>{result['distance']:,}</b>\n"
        f"⏳ Viaje de ida: <b>{result['travel_seconds']:,} segundos</b>\n\n"
        "Los recursos serán entregados automáticamente. "
        "Las caravanas regresarán a tu reino después de la entrega.",
        parse_mode="HTML",
    )

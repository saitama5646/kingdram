import asyncio
import logging

from aiogram import Bot

from bot.database.connection import get_pool
from bot.services.military import UNITS, finish_training


async def military_worker(bot: Bot):
    print("Sistema de entrenamiento militar iniciado.")

    while True:
        try:
            pool = await get_pool()
            notifications = []

            async with pool.acquire() as connection:
                due_realms = await connection.fetch(
                    """
                    SELECT DISTINCT realm_id
                    FROM training_queue
                    WHERE finishes_at <= NOW()
                    ORDER BY realm_id
                    """
                )

                for realm_entry in due_realms:
                    async with connection.transaction():
                        completed = await finish_training(
                            connection,
                            realm_entry["realm_id"],
                        )

                        notifications.extend(completed)

            for item in notifications:
                unit = UNITS.get(item["unit_type"])

                if not unit:
                    continue

                try:
                    await bot.send_message(
                        item["owner_id"],
                        "⚔️ <b>¡Entrenamiento finalizado!</b>\n\n"
                        f"En <b>{item['realm_name']}</b> "
                        f"se han incorporado "
                        f"<b>{item['quantity']}</b> "
                        f"{unit['name']}.\n\n"
                        "Las tropas ya están disponibles "
                        "en tu ejército."
                    )

                except Exception:
                    logging.exception(
                        "No se pudo enviar el aviso "
                        "de entrenamiento finalizado."
                    )

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "Error en el sistema de entrenamiento militar."
            )

        await asyncio.sleep(10)

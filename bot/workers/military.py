import asyncio
import logging

from bot.database.connection import get_pool
from bot.services.military import finish_training


async def military_worker():
    print("Sistema de entrenamiento militar iniciado.")

    while True:
        try:
            pool = await get_pool()

            async with pool.acquire() as connection:
                realm_ids = await connection.fetch(
                    """
                    SELECT DISTINCT realm_id
                    FROM training_queue
                    WHERE finishes_at <= NOW()
                    """
                )

                for row in realm_ids:
                    async with connection.transaction():
                        await finish_training(
                            connection,
                            row["realm_id"],
                        )

        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception(
                "Error en el sistema de entrenamiento militar."
            )

        await asyncio.sleep(10)

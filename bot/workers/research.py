
import asyncio
import logging

from bot.database.connection import get_pool
from bot.services.research import RESEARCH


async def finish_research():
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            completed = await connection.fetch(
                """
                SELECT
                    id,
                    realm_id,
                    research_type,
                    target_level
                FROM research_queue
                WHERE finishes_at <= NOW()
                ORDER BY finishes_at, id
                FOR UPDATE SKIP LOCKED
                """
            )

            for item in completed:
                research_type = item["research_type"]
                realm_id = item["realm_id"]
                target_level = item["target_level"]

                if research_type not in RESEARCH:
                    logging.error(
                        "Investigación desconocida en cola: %s",
                        research_type,
                    )

                    await connection.execute(
                        """
                        DELETE FROM research_queue
                        WHERE id = $1
                        """,
                        item["id"],
                    )

                    continue

                await connection.execute(
                    """
                    INSERT INTO realm_research (
                        realm_id,
                        research_type,
                        level,
                        updated_at
                    )
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (realm_id, research_type)
                    DO UPDATE SET
                        level = GREATEST(
                            realm_research.level,
                            EXCLUDED.level
                        ),
                        updated_at = NOW()
                    """,
                    realm_id,
                    research_type,
                    target_level,
                )

                await connection.execute(
                    """
                    INSERT INTO realm_event_log (
                        realm_id,
                        event_type,
                        description
                    )
                    VALUES ($1, 'research_completed', $2)
                    """,
                    realm_id,
                    (
                        f"Investigación completada: "
                        f"{RESEARCH[research_type]['name']} "
                        f"nivel {target_level}."
                    ),
                )

                await connection.execute(
                    """
                    DELETE FROM research_queue
                    WHERE id = $1
                    """,
                    item["id"],
                )


async def research_worker():
    print("Sistema de investigación iniciado.")

    while True:
        try:
            await finish_research()

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "Error finalizando investigaciones."
            )

        await asyncio.sleep(10)

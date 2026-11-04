
import asyncio

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
                ORDER BY finishes_at
                FOR UPDATE SKIP LOCKED
                """
            )

            for item in completed:
                research_type = item["research_type"]

                if research_type not in RESEARCH:
                    await connection.execute(
                        "DELETE FROM research_queue WHERE id = $1",
                        item["id"]
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
                    item["realm_id"],
                    research_type,
                    item["target_level"]
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
                    item["realm_id"],
                    (
                        f"Investigación completada: "
                        f"{RESEARCH[research_type]['name']} "
                        f"nivel {item['target_level']}."
                    )
                )

                await connection.execute(
                    """
                    DELETE FROM research_queue
                    WHERE id = $1
                    """,
                    item["id"]
                )


async def research_worker():
    while True:
        try:
            await finish_research()

        except asyncio.CancelledError:
            raise

        except Exception as error:
            print(f"Error finalizando investigaciones: {error}")

        await asyncio.sleep(10)

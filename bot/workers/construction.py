
import asyncio

from bot.database.connection import get_pool


async def finish_constructions():
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            completed = await connection.fetch(
                """
                SELECT
                    id,
                    realm_id,
                    building_type,
                    target_level
                FROM construction_queue
                WHERE finishes_at <= NOW()
                FOR UPDATE SKIP LOCKED
                """
            )

            for construction in completed:
                await connection.execute(
                    """
                    INSERT INTO buildings (
                        realm_id,
                        building_type,
                        level
                    )
                    VALUES ($1, $2, $3)
                    ON CONFLICT (realm_id, building_type)
                    DO UPDATE SET
                        level = EXCLUDED.level
                    """,
                    construction["realm_id"],
                    construction["building_type"],
                    construction["target_level"]
                )

                await connection.execute(
                    """
                    UPDATE realms
                    SET power = power + 25
                    WHERE id = $1
                    """,
                    construction["realm_id"]
                )

                await connection.execute(
                    """
                    DELETE FROM construction_queue
                    WHERE id = $1
                    """,
                    construction["id"]
                )


async def construction_worker():
    while True:
        try:
            await finish_constructions()

        except asyncio.CancelledError:
            raise

        except Exception as error:
            print(f"Error finalizando construcciones: {error}")

        await asyncio.sleep(10)



import asyncio

from bot.database.connection import get_pool
from bot.services.construction import BUILDINGS, get_production


async def produce_resources():
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            realms = await connection.fetch(
                """
                SELECT realm_id
                FROM resources
                FOR UPDATE
                """
            )

            for realm in realms:
                realm_id = realm["realm_id"]

                elapsed = await connection.fetchval(
                    """
                    SELECT GREATEST(
                        0,
                        FLOOR(
                            EXTRACT(
                                EPOCH FROM NOW() - updated_at
                            ) / 60
                        )
                    )
                    FROM resources
                    WHERE realm_id = $1
                    """,
                    realm_id
                )

                if not elapsed or elapsed <= 0:
                    continue

                buildings = await connection.fetch(
                    """
                    SELECT building_type, level
                    FROM buildings
                    WHERE realm_id = $1
                    """,
                    realm_id
                )

                production = {
                    "wood": 0,
                    "stone": 0,
                    "gold": 0,
                    "food": 0
                }

                for building in buildings:
                    building_type = building["building_type"]

                    if building_type not in BUILDINGS:
                        continue

                    resource = BUILDINGS[building_type]["resource"]

                    if not resource:
                        continue

                    production[resource] += get_production(
                        building_type,
                        building["level"]
                    )

                await connection.execute(
                    """
                    UPDATE resources
                    SET wood = wood + $1 * $5,
                        stone = stone + $2 * $5,
                        gold = gold + $3 * $5,
                        food = food + $4 * $5,
                        updated_at = NOW()
                    WHERE realm_id = $6
                    """,
                    production["wood"],
                    production["stone"],
                    production["gold"],
                    production["food"],
                    elapsed,
                    realm_id
                )


async def production_worker():
    while True:
        try:
            await produce_resources()

        except asyncio.CancelledError:
            raise

        except Exception as error:
            print(f"Error en producción: {error}")

        await asyncio.sleep(60)

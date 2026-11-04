import asyncio
import logging
from decimal import Decimal, ROUND_FLOOR

from bot.database.connection import get_pool
from bot.services.construction import BUILDINGS, get_production
from bot.services.research import get_research_effects


RESOURCES = ("wood", "stone", "gold", "food")

PRODUCTION_INTERVAL_SECONDS = 60


def calculate_production(buildings, research_effects=None):
    research_effects = research_effects or {}

    production = {
        resource: 0
        for resource in RESOURCES
    }

    for building in buildings:
        building_type = building["building_type"]

        if building_type not in BUILDINGS:
            continue

        resource = BUILDINGS[building_type]["resource"]

        if resource not in production:
            continue

        production[resource] += get_production(
            building_type,
            building["level"]
        )

    for resource in RESOURCES:
        bonus = research_effects.get(
            f"{resource}_production",
            0
        )

        multiplier = max(0, 1 + float(bonus))

        production[resource] = int(
            production[resource] * multiplier
        )

    return production


def split_tribute(production, rate):
    tribute = {}
    retained = {}

    rate = Decimal(str(rate))

    for resource in RESOURCES:
        amount = max(
            0,
            int(production.get(resource, 0))
        )

        tribute_amount = int(
            (
                Decimal(amount) * rate
            ).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )

        tribute[resource] = tribute_amount
        retained[resource] = amount - tribute_amount

    return tribute, retained


async def get_realm_research(connection, realm_id):
    rows = await connection.fetch(
        """
        SELECT research_type, level
        FROM realm_research
        WHERE realm_id = $1
        """,
        realm_id
    )

    return {
        row["research_type"]: row["level"]
        for row in rows
    }


async def produce_resources():
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            realms = await connection.fetch(
                """
                SELECT realm_id, updated_at
                FROM resources
                ORDER BY realm_id
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
                    )::BIGINT
                    FROM resources
                    WHERE realm_id = $1
                    """,
                    realm_id
                )

                if not elapsed:
                    continue

                buildings = await connection.fetch(
                    """
                    SELECT building_type, level
                    FROM buildings
                    WHERE realm_id = $1
                    """,
                    realm_id
                )

                research_levels = await get_realm_research(
                    connection,
                    realm_id
                )

                research_effects = get_research_effects(
                    research_levels
                )

                per_minute = calculate_production(
                    buildings,
                    research_effects
                )

                produced = {
                    resource: amount * elapsed
                    for resource, amount in per_minute.items()
                }

                relation = await connection.fetchrow(
                    """
                    SELECT
                        id,
                        lord_realm_id,
                        vassal_realm_id,
                        tribute_rate
                    FROM vassalage_relations
                    WHERE vassal_realm_id = $1
                      AND status = 'active'
                    FOR UPDATE
                    """,
                    realm_id
                )

                if relation:
                    tribute, retained = split_tribute(
                        produced,
                        relation["tribute_rate"]
                    )
                else:
                    tribute = {
                        resource: 0
                        for resource in RESOURCES
                    }

                    retained = produced

                await connection.execute(
                    """
                    UPDATE resources
                    SET wood = wood + $1,
                        stone = stone + $2,
                        gold = gold + $3,
                        food = food + $4,
                        updated_at = NOW()
                    WHERE realm_id = $5
                    """,
                    retained["wood"],
                    retained["stone"],
                    retained["gold"],
                    retained["food"],
                    realm_id
                )

                if relation and any(tribute.values()):
                    await connection.execute(
                        """
                        UPDATE resources
                        SET wood = wood + $1,
                            stone = stone + $2,
                            gold = gold + $3,
                            food = food + $4
                        WHERE realm_id = $5
                        """,
                        tribute["wood"],
                        tribute["stone"],
                        tribute["gold"],
                        tribute["food"],
                        relation["lord_realm_id"]
                    )

                    await connection.execute(
                        """
                        INSERT INTO vassalage_tribute_log (
                            relation_id,
                            lord_realm_id,
                            vassal_realm_id,
                            wood,
                            stone,
                            gold,
                            food
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        relation["id"],
                        relation["lord_realm_id"],
                        relation["vassal_realm_id"],
                        tribute["wood"],
                        tribute["stone"],
                        tribute["gold"],
                        tribute["food"]
                    )


async def production_worker():
    print("Sistema de producción iniciado.")

    while True:
        try:
            await produce_resources()

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "Error en el sistema de producción."
            )

        await asyncio.sleep(
            PRODUCTION_INTERVAL_SECONDS
        )


from bot.database.connection import get_pool


POSITIONS_PER_REGION = 50
REGIONS_PER_CONTINENT = 20
MAX_CONTINENTS = 100

# Distancias ponderadas para que cambiar de continente
# sea mucho más costoso que cambiar de región.
CONTINENT_DISTANCE = 1000
REGION_DISTANCE = 100
POSITION_DISTANCE = 1


def calculate_distance(origin, target):
    oc, ore, op = origin
    tc, tre, tp = target

    return (
        abs(tc - oc) * CONTINENT_DISTANCE
        + abs(tre - ore) * REGION_DISTANCE
        + abs(tp - op) * POSITION_DISTANCE
    )


def calculate_travel_time(distance, speed_bonus=0):
    speed_multiplier = max(0.25, 1 + speed_bonus)
    seconds = 60 + distance * 20

    return max(30, int(seconds / speed_multiplier))


async def assign_world_position(connection, realm_id):
    # Evita que dos fundaciones simultáneas reciban
    # la misma posición.
    await connection.execute(
        "SELECT pg_advisory_lock(4815162342)"
    )

    try:
        realm = await connection.fetchrow(
            """
            SELECT continent, region, position
            FROM realms
            WHERE id = $1
            FOR UPDATE
            """,
            realm_id,
        )

        if not realm:
            raise ValueError(
                f"No existe el reino {realm_id}."
            )

        if all(
            realm[key] is not None
            for key in ("continent", "region", "position")
        ):
            return (
                realm["continent"],
                realm["region"],
                realm["position"],
            )

        for continent in range(1, MAX_CONTINENTS + 1):
            for region in range(1, REGIONS_PER_CONTINENT + 1):
                occupied = await connection.fetch(
                    """
                    SELECT position
                    FROM realms
                    WHERE continent = $1
                      AND region = $2
                      AND position IS NOT NULL
                    """,
                    continent,
                    region,
                )

                occupied_positions = {
                    row["position"] for row in occupied
                }

                for position in range(
                    1,
                    POSITIONS_PER_REGION + 1,
                ):
                    if position in occupied_positions:
                        continue

                    await connection.execute(
                        """
                        UPDATE realms
                        SET continent = $1,
                            region = $2,
                            position = $3
                        WHERE id = $4
                        """,
                        continent,
                        region,
                        position,
                        realm_id,
                    )

                    return continent, region, position

        raise RuntimeError(
            "No quedan posiciones disponibles en el mapa."
        )

    finally:
        await connection.execute(
            "SELECT pg_advisory_unlock(4815162342)"
        )


async def get_realm_coordinates(realm_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT continent, region, position
            FROM realms
            WHERE id = $1
            """,
            realm_id,
        )


async def get_world_map(continent, region):
    pool = await get_pool()

    async with pool.acquire() as connection:
        return await connection.fetch(
            """
            SELECT
                position,
                id,
                name,
                level,
                power
            FROM realms
            WHERE continent = $1
              AND region = $2
            ORDER BY position
            """,
            continent,
            region,
        )


async def find_realm_at(continent, region, position):
    pool = await get_pool()

    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT id, owner_id, name, level, power
            FROM realms
            WHERE continent = $1
              AND region = $2
              AND position = $3
            """,
            continent,
            region,
            position,
        )

from bot.database.connection import get_pool


POSITIONS_PER_TERRITORY = 20
TERRITORIES_PER_CONTINENT = 3
MAX_CONTINENTS = 100

POSITIONS_PER_CONTINENT = (
    POSITIONS_PER_TERRITORY
    * TERRITORIES_PER_CONTINENT
)

TOTAL_WORLD_POSITIONS = (
    MAX_CONTINENTS
    * POSITIONS_PER_CONTINENT
)

CONTINENT_DISTANCE = 50000
REGION_DISTANCE = 250
POSITION_DISTANCE = 5

BASE_TRAVEL_SECONDS = 60
TRAVEL_TIME_FACTOR = 20


def normalize_coordinates(coordinates):
    if not coordinates:
        raise ValueError("No se recibieron coordenadas.")

    if len(coordinates) != 3:
        raise ValueError(
            "Las coordenadas deben contener continente, "
            "territorio y posición."
        )

    continent, territory, position = (
        int(coordinates[0]),
        int(coordinates[1]),
        int(coordinates[2]),
    )

    if not 1 <= continent <= MAX_CONTINENTS:
        raise ValueError("Continente fuera de los límites del mapa.")

    if not 1 <= territory <= TERRITORIES_PER_CONTINENT:
        raise ValueError("Territorio fuera de los límites del continente.")

    if not 1 <= position <= POSITIONS_PER_TERRITORY:
        raise ValueError("Posición fuera de los límites del territorio.")

    return continent, territory, position


def format_coordinates(coordinates):
    continent, territory, position = normalize_coordinates(
        coordinates
    )

    return f"{continent}:{territory}:{position}"


def calculate_distance(origin, target):
    oc, ot, op = normalize_coordinates(origin)
    tc, tt, tp = normalize_coordinates(target)

    return (
        abs(tc - oc) * CONTINENT_DISTANCE
        + abs(tt - ot) * REGION_DISTANCE
        + abs(tp - op) * POSITION_DISTANCE
    )


def calculate_travel_time(
    distance,
    unit_speed,
    speed_bonus=0,
):
    distance = max(0, float(distance))
    unit_speed = max(1, float(unit_speed))

    bonus_multiplier = max(
        0.25,
        1 + float(speed_bonus),
    )

    effective_speed = unit_speed * bonus_multiplier

    seconds = (
        BASE_TRAVEL_SECONDS
        + distance * TRAVEL_TIME_FACTOR / effective_speed
    )

    return max(60, int(seconds))


def calculate_mission_speed(troops):
    from bot.services.military import UNITS

    speeds = []

    for troop in troops:
        quantity = int(troop.get("quantity", 0))

        if quantity <= 0:
            continue

        unit = UNITS.get(troop["unit_type"])

        if not unit:
            continue

        speeds.append(
            float(unit.get("speed", 1))
        )

    if not speeds:
        return 0

    return min(speeds)


async def assign_world_position(connection, realm_id):
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
            return normalize_coordinates((
                realm["continent"],
                realm["region"],
                realm["position"],
            ))

        # Buscar el primer continente que todavía tenga
        # alguna posición libre. Nunca se salta a otro
        # continente mientras este no esté completo.
        selected = await connection.fetchrow(
            """
            WITH first_available AS (
                SELECT continents.continent
                FROM generate_series(1, $1) AS continents(continent)
                WHERE (
                    SELECT COUNT(*)
                    FROM realms occupied
                    WHERE occupied.continent =
                        continents.continent
                ) < $2
                ORDER BY continents.continent
                LIMIT 1
            ),
            free_positions AS (
                SELECT
                    first_available.continent,
                    territories.territory,
                    positions.position
                FROM first_available
                CROSS JOIN generate_series(
                    1, $3
                ) AS territories(territory)
                CROSS JOIN generate_series(
                    1, $4
                ) AS positions(position)
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM realms occupied
                    WHERE occupied.continent =
                        first_available.continent
                      AND occupied.region =
                        territories.territory
                      AND occupied.position =
                        positions.position
                )
            )
            SELECT
                continent,
                territory,
                position
            FROM free_positions
            ORDER BY random()
            LIMIT 1
            """,
            MAX_CONTINENTS,
            POSITIONS_PER_CONTINENT,
            TERRITORIES_PER_CONTINENT,
            POSITIONS_PER_TERRITORY,
        )

        if not selected:
            raise RuntimeError(
                "No quedan posiciones disponibles en el mundo."
            )

        coordinates = normalize_coordinates((
            selected["continent"],
            selected["territory"],
            selected["position"],
        ))

        await connection.execute(
            """
            UPDATE realms
            SET continent = $1,
                region = $2,
                position = $3
            WHERE id = $4
            """,
            coordinates[0],
            coordinates[1],
            coordinates[2],
            realm_id,
        )

        return coordinates

    finally:
        await connection.execute(
            "SELECT pg_advisory_unlock(4815162342)"
        )


async def get_realm_coordinates(realm_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT continent, region, position
            FROM realms
            WHERE id = $1
            """,
            realm_id,
        )

        if not row:
            return None

        if any(
            row[key] is None
            for key in ("continent", "region", "position")
        ):
            return None

        return normalize_coordinates((
            row["continent"],
            row["region"],
            row["position"],
        ))


async def get_world_map(continent, territory):
    continent, territory, _ = normalize_coordinates(
        (continent, territory, 1)
    )

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
            territory,
        )


async def find_realm_at(continent, territory, position):
    continent, territory, position = normalize_coordinates(
        (continent, territory, position)
    )

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
            territory,
            position,
        )

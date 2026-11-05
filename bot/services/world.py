
from bot.database.connection import get_pool


POSITIONS_PER_REGION = 50
REGIONS_PER_CONTINENT = 20
MAX_CONTINENTS = 100

# Distancia jerárquica del mapa.
# El salto entre continentes domina sobre regiones y posiciones.
CONTINENT_DISTANCE = 20000
REGION_DISTANCE = 95
POSITION_DISTANCE = 1

# Tiempo base de desplazamiento.
BASE_TRAVEL_SECONDS = 30

# Velocidad base del sistema de misiones.
# Distancia / velocidad = tiempo de viaje.
TRAVEL_TIME_FACTOR = 10


def normalize_coordinates(coordinates):
    if not coordinates:
        raise ValueError("No se recibieron coordenadas.")

    if len(coordinates) != 3:
        raise ValueError(
            "Las coordenadas deben contener continente, región y posición."
        )

    continent, region, position = (
        int(coordinates[0]),
        int(coordinates[1]),
        int(coordinates[2]),
    )

    if not 1 <= continent <= MAX_CONTINENTS:
        raise ValueError("Continente fuera de los límites del mapa.")

    if not 1 <= region <= REGIONS_PER_CONTINENT:
        raise ValueError("Región fuera de los límites del continente.")

    if not 1 <= position <= POSITIONS_PER_REGION:
        raise ValueError("Territorio fuera de los límites de la región.")

    return continent, region, position


def format_coordinates(coordinates):
    continent, region, position = normalize_coordinates(
        coordinates
    )

    return f"{continent}:{region}:{position}"


def calculate_distance(origin, target):
    oc, ore, op = normalize_coordinates(origin)
    tc, tre, tp = normalize_coordinates(target)

    return (
        abs(tc - oc) * CONTINENT_DISTANCE
        + abs(tre - ore) * REGION_DISTANCE
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

    return max(30, int(seconds))


def calculate_mission_speed(troops):
    """
    Devuelve la velocidad de la unidad más lenta
    presente en la expedición.
    """
    from bot.services.military import UNITS

    speeds = []

    for troop in troops:
        quantity = int(troop.get("quantity", 0))

        if quantity <= 0:
            continue

        unit = UNITS.get(troop["unit_type"])

        if not unit:
            continue

        speeds.append(float(unit.get("speed", 1)))

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
                    row["position"]
                    for row in occupied
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

        return normalize_coordinates((
            row["continent"],
            row["region"],
            row["position"],
        ))


async def get_world_map(continent, region):
    continent, region, _ = normalize_coordinates(
        (continent, region, 1)
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
            region,
        )


async def find_realm_at(continent, region, position):
    continent, region, position = normalize_coordinates(
        (continent, region, position)
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
            region,
            position,
        )

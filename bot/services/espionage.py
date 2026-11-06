
from math import ceil

from bot.database.connection import get_pool
from bot.services.world import (
    calculate_distance,
    calculate_travel_time,
)


SPY_COST = {
    "wood": 80,
    "stone": 30,
    "gold": 120,
    "food": 60,
}

SPY_TRAINING_SECONDS = 120

MISSION_TYPES = {
    "resources": "Reconocimiento económico",
    "military": "Inteligencia militar",
    "buildings": "Reconocimiento de edificios",
    "research": "Inteligencia tecnológica",
}


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, float(value)))


def calculate_spy_success(
    spies_sent,
    infiltration_bonus=0,
    counter_bonus=0,
):
    """
    Modelo determinista de probabilidad.
    El azar se aplica en el worker al resolver la misión.
    """
    spies_sent = max(1, int(spies_sent))

    base = 0.45
    quantity_bonus = min(0.25, (spies_sent - 1) * 0.025)

    chance = (
        base
        + quantity_bonus
        + max(0.0, float(infiltration_bonus))
        - max(0.0, float(counter_bonus))
    )

    return clamp(chance, 0.15, 0.90)


def calculate_mission_duration(distance, spy_speed=2, speed_bonus=0):
    return calculate_travel_time(
        distance,
        spy_speed,
        speed_bonus,
    )


async def get_spy_count(connection, realm_id):
    return int(
        await connection.fetchval(
            """
            SELECT quantity
            FROM realm_spies
            WHERE realm_id = $1
            """,
            realm_id,
        )
        or 0
    )


async def recruit_spies(user_id, quantity):
    if not isinstance(quantity, int) or quantity not in (1, 5, 10):
        return False, "Cantidad de espías no válida."

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            realm = await connection.fetchrow(
                """
                SELECT id
                FROM realms
                WHERE owner_id = $1
                FOR UPDATE
                """,
                user_id,
            )

            if not realm:
                return False, "Primero debes fundar un reino."

            realm_id = realm["id"]

            resources = await connection.fetchrow(
                """
                SELECT wood, stone, gold, food
                FROM resources
                WHERE realm_id = $1
                FOR UPDATE
                """,
                realm_id,
            )

            if not resources:
                return False, "No se encontraron los recursos del reino."

            costs = {
                resource: amount * quantity
                for resource, amount in SPY_COST.items()
            }

            missing = [
                resource
                for resource, amount in costs.items()
                if resources[resource] < amount
            ]

            if missing:
                return False, (
                    "No tienes recursos suficientes: "
                    + ", ".join(missing)
                )

            await connection.execute(
                """
                UPDATE resources
                SET wood = wood - $1,
                    stone = stone - $2,
                    gold = gold - $3,
                    food = food - $4
                WHERE realm_id = $5
                """,
                costs["wood"],
                costs["stone"],
                costs["gold"],
                costs["food"],
                realm_id,
            )

            await connection.execute(
                """
                INSERT INTO realm_spies (
                    realm_id,
                    quantity,
                    updated_at
                )
                VALUES ($1, $2, NOW())
                ON CONFLICT (realm_id)
                DO UPDATE SET
                    quantity = realm_spies.quantity
                        + EXCLUDED.quantity,
                    updated_at = NOW()
                """,
                realm_id,
                quantity,
            )

    return True, (
        f"Reclutamiento completado: {quantity} espía(s)."
    )


async def launch_spy_mission(user_id, target_realm_id, mission_type, spies_sent):
    if mission_type not in MISSION_TYPES:
        return False, "Tipo de misión desconocido."

    if not isinstance(spies_sent, int) or spies_sent < 1:
        return False, "Cantidad de espías no válida."

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            own_realm = await connection.fetchrow(
                """
                SELECT id, continent, region, position
                FROM realms
                WHERE owner_id = $1
                FOR UPDATE
                """,
                user_id,
            )

            if not own_realm:
                return False, "Primero debes fundar un reino."

            own_id = own_realm["id"]

            if own_id == target_realm_id:
                return False, "No puedes espiar tu propio reino."

            target = await connection.fetchrow(
                """
                SELECT id, owner_id, continent, region, position
                FROM realms
                WHERE id = $1
                FOR UPDATE
                """,
                target_realm_id,
            )

            if not target:
                return False, "El reino objetivo ya no existe."

            if target["owner_id"] == user_id:
                return False, "No puedes espiar tu propio reino."

            available = await get_spy_count(
                connection,
                own_id,
            )

            if available < spies_sent:
                return False, (
                    f"Espías disponibles: {available}. "
                    f"Necesitas {spies_sent}."
                )

            origin = (
                own_realm["continent"],
                own_realm["region"],
                own_realm["position"],
            )

            destination = (
                target["continent"],
                target["region"],
                target["position"],
            )

            if any(value is None for value in origin + destination):
                return False, "Uno de los reinos no tiene coordenadas."

            distance = calculate_distance(
                origin,
                destination,
            )

            duration = calculate_mission_duration(distance)

            await connection.execute(
                """
                UPDATE realm_spies
                SET quantity = quantity - $1,
                    updated_at = NOW()
                WHERE realm_id = $2
                """,
                spies_sent,
                own_id,
            )

            await connection.execute(
                """
                INSERT INTO espionage_missions (
                    attacker_realm_id,
                    target_realm_id,
                    mission_type,
                    spies_sent,
                    status,
                    departure_at,
                    arrival_at
                )
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4,
                    'travelling',
                    NOW(),
                    NOW() + $5 * INTERVAL '1 second'
                )
                """,
                own_id,
                target_realm_id,
                mission_type,
                spies_sent,
                duration,
            )

    return True, (
        f"Misión enviada: {MISSION_TYPES[mission_type]}.\n"
        f"Espías enviados: {spies_sent}.\n"
        f"Tiempo estimado: {duration} segundos."
    )


async def get_spy_dashboard(user_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm = await connection.fetchrow(
            """
            SELECT id, name
            FROM realms
            WHERE owner_id = $1
            """,
            user_id,
        )

        if not realm:
            return None

        spies = await get_spy_count(
            connection,
            realm["id"],
        )

        targets = await connection.fetch(
            """
            SELECT
                id,
                name,
                power,
                continent,
                region,
                position
            FROM realms
            WHERE owner_id <> $1
            ORDER BY power DESC, id
            LIMIT 30
            """,
            user_id,
        )

        missions = await connection.fetch(
            """
            SELECT
                mission_type,
                spies_sent,
                arrival_at
            FROM espionage_missions
            WHERE attacker_realm_id = $1
              AND status = 'travelling'
            ORDER BY arrival_at, id
            LIMIT 10
            """,
            realm["id"],
        )

        reports = await connection.fetch(
            """
            SELECT
                id,
                mission_type,
                success,
                spies_lost,
                created_at
            FROM espionage_reports
            WHERE attacker_realm_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 10
            """,
            realm["id"],
        )

    return {
        "realm": realm,
        "spies": spies,
        "targets": targets,
        "missions": missions,
        "reports": reports,
    }

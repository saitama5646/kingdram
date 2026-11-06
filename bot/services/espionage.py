
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

    return clamp(chance, 0.15, 0.80)


def calculate_spy_training_duration(
    quantity,
    speed_bonus=0,
    base_seconds=SPY_TRAINING_SECONDS,
):
    quantity = int(quantity)

    if quantity not in (1, 5, 10):
        raise ValueError("Cantidad de espías no válida.")

    speed_bonus = max(0.0, float(speed_bonus))
    speed_bonus = min(speed_bonus, 0.75)

    return max(
        1,
        ceil(
            int(base_seconds)
            * quantity
            / (1.0 + speed_bonus)
        ),
    )


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
                return False, (
                    "No se encontraron los recursos del reino."
                )

            research_rows = await connection.fetch(
                """
                SELECT research_type, level
                FROM realm_research
                WHERE realm_id = $1
                """,
                realm_id,
            )

            research_levels = {
                row["research_type"]: row["level"]
                for row in research_rows
            }

            from bot.services.research import get_research_effects

            effects = get_research_effects(research_levels)

            training_bonus = max(
                0.0,
                float(effects.get("spy_training_speed", 0)),
            )

            duration = calculate_spy_training_duration(
                quantity,
                training_bonus,
            )

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
                INSERT INTO spy_training_queue (
                    realm_id,
                    quantity,
                    status,
                    started_at,
                    ready_at
                )
                VALUES (
                    $1,
                    $2,
                    'queued',
                    NOW(),
                    NOW() + $3 * INTERVAL '1 second'
                )
                """,
                realm_id,
                quantity,
                duration,
            )

    return True, (
        f"Entrenamiento iniciado: {quantity} espía(s).\n"
        f"Tiempo estimado: {duration} segundos."
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

        missions = await connection.fetch(
            """
            SELECT
                em.mission_type,
                em.spies_sent,
                em.arrival_at,
                target.name AS target_name
            FROM espionage_missions em
            JOIN realms target
              ON target.id = em.target_realm_id
            WHERE em.attacker_realm_id = $1
              AND em.status = 'travelling'
            ORDER BY em.arrival_at, em.id
            LIMIT 10
            """,
            realm["id"],
        )

        reports = await connection.fetch(
            """
            SELECT
                er.id,
                er.mission_type,
                er.success,
                er.spies_lost,
                er.created_at,
                target.name AS target_name
            FROM espionage_reports er
            JOIN realms target
              ON target.id = er.target_realm_id
            WHERE er.attacker_realm_id = $1
            ORDER BY er.created_at DESC, er.id DESC
            LIMIT 10
            """,
            realm["id"],
        )

    return {
        "realm": realm,
        "spies": spies,
        "missions": missions,
        "reports": reports,
    }


from math import ceil

from bot.database.connection import get_pool


UNITS = {
    "spearman": {
        "name": "Lancero",
        "emoji": "🗡️",
        "description": "Infantería defensiva básica.",
        "attack": 8,
        "defense": 12,
        "wood": 35,
        "stone": 10,
        "gold": 15,
        "food": 20,
        "seconds": 20,
        "barracks": 1,
    },
    "archer": {
        "name": "Arquero",
        "emoji": "🏹",
        "description": "Unidad de ataque a distancia.",
        "attack": 15,
        "defense": 5,
        "wood": 50,
        "stone": 5,
        "gold": 25,
        "food": 25,
        "seconds": 30,
        "barracks": 2,
    },
    "cavalry": {
        "name": "Caballería",
        "emoji": "🐎",
        "description": "Unidad rápida y poderosa.",
        "attack": 28,
        "defense": 18,
        "wood": 30,
        "stone": 20,
        "gold": 90,
        "food": 65,
        "seconds": 60,
        "barracks": 4,
    },
    "royal_guard": {
        "name": "Guardia real",
        "emoji": "🛡️",
        "description": "Élite militar del reino.",
        "attack": 35,
        "defense": 40,
        "wood": 80,
        "stone": 60,
        "gold": 120,
        "food": 80,
        "seconds": 90,
        "barracks": 6,
    },
}


QUANTITIES = (5, 10, 25)


RESOURCE_LABELS = {
    "wood": "🪵 Madera",
    "stone": "🪨 Piedra",
    "gold": "🪙 Oro",
    "food": "🌾 Alimentos",
}


def format_costs(costs):
    return "\n".join(
        f"{RESOURCE_LABELS[resource]}: <b>{amount:,}</b>"
        for resource, amount in costs.items()
    )


async def finish_training(connection, realm_id):
    completed = await connection.fetch(
        """
        SELECT id, unit_type, quantity
        FROM training_queue
        WHERE realm_id = $1
          AND finishes_at <= NOW()
        ORDER BY finishes_at
        FOR UPDATE
        """,
        realm_id,
    )

    for item in completed:
        await connection.execute(
            """
            INSERT INTO army (
                realm_id,
                unit_type,
                quantity
            )
            VALUES ($1, $2, $3)
            ON CONFLICT (realm_id, unit_type)
            DO UPDATE SET quantity =
                army.quantity + EXCLUDED.quantity
            """,
            realm_id,
            item["unit_type"],
            item["quantity"],
        )

        await connection.execute(
            "DELETE FROM training_queue WHERE id = $1",
            item["id"],
        )


async def get_military_data(user_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            realm = await connection.fetchrow(
                """
                SELECT id, name, power
                FROM realms
                WHERE owner_id = $1
                """,
                user_id,
            )

            if not realm:
                return None

            await finish_training(
                connection,
                realm["id"],
            )

            barracks = await connection.fetchval(
                """
                SELECT COALESCE(MAX(level), 0)
                FROM buildings
                WHERE realm_id = $1
                  AND building_type = 'barracks'
                """,
                realm["id"],
            )

            troops = await connection.fetch(
                """
                SELECT unit_type, quantity
                FROM army
                WHERE realm_id = $1
                ORDER BY unit_type
                """,
                realm["id"],
            )

            queue = await connection.fetch(
                """
                SELECT unit_type, quantity, finishes_at
                FROM training_queue
                WHERE realm_id = $1
                ORDER BY finishes_at
                """,
                realm["id"],
            )

            return {
                "realm": realm,
                "barracks": barracks or 0,
                "troops": troops,
                "queue": queue,
            }


async def start_training(user_id, unit_type, quantity):
    if unit_type not in UNITS:
        return False, "Unidad desconocida."

    if quantity not in QUANTITIES:
        return False, "Cantidad no válida."

    unit = UNITS[unit_type]
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

            barracks = await connection.fetchval(
                """
                SELECT COALESCE(MAX(level), 0)
                FROM buildings
                WHERE realm_id = $1
                  AND building_type = 'barracks'
                """,
                realm_id,
            )

            if (barracks or 0) < unit["barracks"]:
                return False, (
                    f"Necesitas un cuartel de nivel "
                    f"{unit['barracks']} para entrenar "
                    f"{unit['name']}."
                )

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

            costs = {
                "wood": unit["wood"] * quantity,
                "stone": unit["stone"] * quantity,
                "gold": unit["gold"] * quantity,
                "food": unit["food"] * quantity,
            }

            missing = []

            for resource, amount in costs.items():
                if resources[resource] < amount:
                    missing.append(
                        f"{RESOURCE_LABELS[resource]}: "
                        f"faltan "
                        f"{amount - resources[resource]:,}"
                    )

            if missing:
                return False, (
                    "No tienes suficientes recursos.\n\n"
                    + "\n".join(missing)
                    + "\n\n<b>Coste total requerido:</b>\n"
                    + format_costs(costs)
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

            last_finish = await connection.fetchval(
                """
                SELECT MAX(finishes_at)
                FROM training_queue
                WHERE realm_id = $1
                """,
                realm_id,
            )

            duration = ceil(
                unit["seconds"] * quantity
                / (
                    1
                    + max(0, (barracks or 1) - 1) * 0.10
                )
            )

            await connection.execute(
                """
                INSERT INTO training_queue (
                    realm_id,
                    unit_type,
                    quantity,
                    finishes_at
                )
                VALUES (
                    $1,
                    $2,
                    $3,
                    GREATEST(
                        NOW(),
                        COALESCE($4::timestamptz, NOW())
                    ) + $5 * INTERVAL '1 second'
                )
                """,
                realm_id,
                unit_type,
                quantity,
                last_finish,
                duration,
            )

            return True, (
                f"{unit['emoji']} <b>Entrenamiento iniciado</b>\n\n"
                f"Unidad: {unit['name']}\n"
                f"Cantidad: {quantity}\n"
                f"Duración aproximada: {duration} segundos."
            )

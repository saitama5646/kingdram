from math import ceil

from bot.database.connection import get_pool
from bot.services.world import (
    calculate_distance,
    calculate_travel_time,
)

RESOURCE_FIELDS = ("wood", "stone", "gold", "food")
CARGO_CAPACITY = 1000


async def create_transport(
    user_id,
    target_realm_id,
    caravan_quantity,
    resources,
):
    try:
        caravan_quantity = int(caravan_quantity)
        resources = {
            key: int(resources.get(key, 0))
            for key in RESOURCE_FIELDS
        }
    except (TypeError, ValueError):
        return False, "Las cantidades deben ser números enteros."

    if caravan_quantity <= 0:
        return False, "Debes enviar al menos una caravana."

    if any(value < 0 for value in resources.values()):
        return False, "No puedes enviar cantidades negativas."

    total_cargo = sum(resources.values())

    if total_cargo <= 0:
        return False, "Debes enviar algún recurso."

    capacity = caravan_quantity * CARGO_CAPACITY

    if total_cargo > capacity:
        return False, (
            "La carga supera la capacidad de las caravanas.\n"
            f"Capacidad: {capacity:,}\n"
            f"Carga solicitada: {total_cargo:,}"
        )

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            origin = await connection.fetchrow(
                """
                SELECT id, name, continent, region, position
                FROM realms
                WHERE owner_id = $1
                FOR UPDATE
                """,
                user_id,
            )

            if not origin:
                return False, "Primero debes fundar tu reino."

            if int(origin["id"]) == int(target_realm_id):
                return False, "No puedes transportar recursos a tu propio reino."

            await connection.fetch(
                """
                SELECT id
                FROM realms
                WHERE id = ANY($1::BIGINT[])
                ORDER BY id
                FOR UPDATE
                """,
                [origin["id"], target_realm_id],
            )

            target = await connection.fetchrow(
                """
                SELECT id, name, continent, region, position
                FROM realms
                WHERE id = $1
                """,
                target_realm_id,
            )

            if not target:
                return False, "El reino destino ya no existe."

            caravans = await connection.fetchval(
                """
                SELECT quantity
                FROM army
                WHERE realm_id = $1
                  AND unit_type = 'cargo_caravan'
                FOR UPDATE
                """,
                origin["id"],
            )

            available_caravans = int(caravans or 0)

            if available_caravans < caravan_quantity:
                return False, (
                    "No tienes suficientes caravanas.\n"
                    f"Disponibles: {available_caravans}\n"
                    f"Solicitadas: {caravan_quantity}"
                )

            stock = await connection.fetchrow(
                """
                SELECT wood, stone, gold, food
                FROM resources
                WHERE realm_id = $1
                FOR UPDATE
                """,
                origin["id"],
            )

            if not stock:
                return False, "No se encontraron los recursos del reino."

            for resource, amount in resources.items():
                if int(stock[resource]) < amount:
                    return False, (
                        f"No tienes suficientes {resource}.\n"
                        f"Disponibles: {int(stock[resource]):,}\n"
                        f"Solicitados: {amount:,}"
                    )

            origin_position = (
                origin["continent"],
                origin["region"],
                origin["position"],
            )

            target_position = (
                target["continent"],
                target["region"],
                target["position"],
            )

            distance = calculate_distance(
                origin_position,
                target_position,
            )

            travel_seconds = calculate_travel_time(
                distance,
                1,
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
                resources["wood"],
                resources["stone"],
                resources["gold"],
                resources["food"],
                origin["id"],
            )

            await connection.execute(
                """
                UPDATE army
                SET quantity = quantity - $1
                WHERE realm_id = $2
                  AND unit_type = 'cargo_caravan'
                """,
                caravan_quantity,
                origin["id"],
            )

            await connection.execute(
                """
                DELETE FROM army
                WHERE realm_id = $1
                  AND unit_type = 'cargo_caravan'
                  AND quantity <= 0
                """,
                origin["id"],
            )

            mission = await connection.fetchrow(
                """
                INSERT INTO logistics_missions (
                    owner_id,
                    origin_realm_id,
                    target_realm_id,
                    caravan_quantity,
                    wood,
                    stone,
                    gold,
                    food,
                    distance,
                    status,
                    delivery_at
                )
                VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7, $8,
                    $9, 'travelling',
                    NOW() + $10 * INTERVAL '1 second'
                )
                RETURNING id, delivery_at
                """,
                user_id,
                origin["id"],
                target["id"],
                caravan_quantity,
                resources["wood"],
                resources["stone"],
                resources["gold"],
                resources["food"],
                distance,
                travel_seconds,
            )

            return True, {
                "mission_id": mission["id"],
                "origin_name": origin["name"],
                "target_name": target["name"],
                "caravans": caravan_quantity,
                "capacity": capacity,
                "cargo": resources,
                "distance": distance,
                "travel_seconds": travel_seconds,
                "delivery_at": mission["delivery_at"],
            }


async def process_logistics():
    pool = await get_pool()

    async with pool.acquire() as connection:
        # Entrega: se cambia el estado dentro de la transacción.
        async with connection.transaction():
            missions = await connection.fetch(
                """
                SELECT *
                FROM logistics_missions
                WHERE status = 'travelling'
                  AND delivery_at <= NOW()
                ORDER BY delivery_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 30
                """
            )

            for mission in missions:
                await connection.fetch(
                    """
                    SELECT id
                    FROM realms
                    WHERE id = ANY($1::BIGINT[])
                    ORDER BY id
                    FOR UPDATE
                    """,
                    [
                        mission["origin_realm_id"],
                        mission["target_realm_id"],
                    ],
                )

                target_exists = await connection.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM realms
                        WHERE id = $1
                    )
                    """,
                    mission["target_realm_id"],
                )

                if not target_exists:
                    await connection.execute(
                        """
                        UPDATE logistics_missions
                        SET status = 'cancelled'
                        WHERE id = $1
                        """,
                        mission["id"],
                    )

                    continue

                await connection.execute(
                    """
                    INSERT INTO resources (
                        realm_id, wood, stone, gold, food
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (realm_id)
                    DO UPDATE SET
                        wood = resources.wood + EXCLUDED.wood,
                        stone = resources.stone + EXCLUDED.stone,
                        gold = resources.gold + EXCLUDED.gold,
                        food = resources.food + EXCLUDED.food
                    """,
                    mission["target_realm_id"],
                    mission["wood"],
                    mission["stone"],
                    mission["gold"],
                    mission["food"],
                )

                return_seconds = calculate_travel_time(
                    float(mission["distance"]),
                    1,
                )

                await connection.execute(
                    """
                    UPDATE logistics_missions
                    SET status = 'returning',
                        delivered_at = NOW(),
                        return_at = NOW() + $2 * INTERVAL '1 second'
                    WHERE id = $1
                    """,
                    mission["id"],
                    return_seconds,
                )

        # Retorno de caravanas.
        async with connection.transaction():
            returning = await connection.fetch(
                """
                SELECT *
                FROM logistics_missions
                WHERE status = 'returning'
                  AND return_at <= NOW()
                ORDER BY return_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 30
                """
            )

            for mission in returning:
                await connection.execute(
                    """
                    INSERT INTO army (
                        realm_id, unit_type, quantity
                    )
                    VALUES ($1, 'cargo_caravan', $2)
                    ON CONFLICT (realm_id, unit_type)
                    DO UPDATE SET quantity =
                        army.quantity + EXCLUDED.quantity
                    """,
                    mission["origin_realm_id"],
                    mission["caravan_quantity"],
                )

                await connection.execute(
                    """
                    UPDATE logistics_missions
                    SET status = 'completed',
                        completed_at = NOW()
                    WHERE id = $1
                    """,
                    mission["id"],
                )


async def logistics_worker():
    import asyncio

    while True:
        await process_logistics()
        await asyncio.sleep(5)

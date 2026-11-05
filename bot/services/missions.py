from bot.database.connection import get_pool
from bot.services.military import UNITS
from bot.services.world import (
    calculate_distance,
    calculate_travel_time,
    calculate_mission_speed,
    get_realm_coordinates,
)


UNIT_ORDER = (
    "spearman",
    "archer",
    "cavalry",
    "royal_guard",
)


def validate_troops(troops):
    selected = {}

    for unit_type in UNIT_ORDER:
        quantity = int(troops.get(unit_type, 0))

        if quantity < 0:
            raise ValueError(
                "Las cantidades no pueden ser negativas."
            )

        selected[unit_type] = quantity

    if sum(selected.values()) <= 0:
        raise ValueError(
            "Debes seleccionar al menos una unidad."
        )

    return selected


async def create_mission(
    user_id,
    defender_realm_id,
    troops,
):
    selected = validate_troops(troops)

    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            attacker = await connection.fetchrow(
                """
                SELECT id, name, continent, region, position
                FROM realms
                WHERE owner_id = $1
                FOR UPDATE
                """,
                user_id,
            )

            if not attacker:
                return False, "Primero debes fundar un reino."

            if attacker["id"] == defender_realm_id:
                return False, "No puedes atacar tu propio reino."

            defender = await connection.fetchrow(
                """
                SELECT id, name, continent, region, position
                FROM realms
                WHERE id = $1
                FOR UPDATE
                """,
                defender_realm_id,
            )

            if not defender:
                return False, "El reino objetivo ya no existe."

            relation = await connection.fetchrow(
                """
                SELECT id
                FROM vassalage_relations
                WHERE lord_realm_id = $1
                  AND vassal_realm_id = $2
                  AND status = 'active'
                """,
                attacker["id"],
                defender_realm_id,
            )

            if relation:
                return False, (
                    "No puedes atacar a tu propio vasallo."
                )

            # PACTO DE NO AGRESION ENTRE ALIANZAS
            non_aggression = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM alliance_members attacker_member
                    JOIN alliance_members defender_member
                      ON defender_member.player_id = $2
                    JOIN alliance_treaties treaty
                      ON treaty.status = 'active'
                     AND treaty.treaty_type = 'non_aggression'
                     AND (
                         (
                             treaty.alliance_id =
                                 attacker_member.alliance_id
                             AND treaty.other_alliance_id =
                                 defender_member.alliance_id
                         )
                         OR
                         (
                             treaty.alliance_id =
                                 defender_member.alliance_id
                             AND treaty.other_alliance_id =
                                 attacker_member.alliance_id
                         )
                     )
                    WHERE attacker_member.player_id = $1
                )
                """,
                user_id,
                await connection.fetchval(
                    """
                    SELECT owner_id
                    FROM realms
                    WHERE id = $1
                    """,
                    defender_realm_id,
                ),
            )

            if non_aggression:
                return False, (
                    "No puedes atacar a este reino: "
                    "tu alianza mantiene un pacto de "
                    "no agresión vigente con su alianza."
                )

            available_rows = await connection.fetch(
                """
                SELECT unit_type, quantity
                FROM army
                WHERE realm_id = $1
                FOR UPDATE
                """,
                attacker["id"],
            )

            available = {
                row["unit_type"]: int(row["quantity"])
                for row in available_rows
            }

            for unit_type, quantity in selected.items():
                if quantity > available.get(unit_type, 0):
                    unit_name = UNITS[unit_type]["name"]

                    return False, (
                        f"No tienes suficientes {unit_name}.\n"
                        f"Disponibles: "
                        f"{available.get(unit_type, 0)}\n"
                        f"Seleccionados: {quantity}"
                    )

            origin = (
                attacker["continent"],
                attacker["region"],
                attacker["position"],
            )

            target = (
                defender["continent"],
                defender["region"],
                defender["position"],
            )

            distance = calculate_distance(
                origin,
                target,
            )

            troops_for_speed = [
                {
                    "unit_type": unit_type,
                    "quantity": quantity,
                }
                for unit_type, quantity in selected.items()
                if quantity > 0
            ]

            speed = calculate_mission_speed(
                troops_for_speed
            )

            if speed <= 0:
                return False, (
                    "No se pudo calcular la velocidad "
                    "de la expedición."
                )

            travel_seconds = calculate_travel_time(
                distance,
                speed,
            )

            mission = await connection.fetchrow(
                """
                INSERT INTO military_missions (
                    attacker_realm_id,
                    defender_realm_id,
                    mission_type,
                    status,
                    origin_continent,
                    origin_region,
                    origin_position,
                    target_continent,
                    target_region,
                    target_position,
                    distance,
                    departure_at,
                    arrival_at
                )
                VALUES (
                    $1, $2, 'attack', 'travelling',
                    $3, $4, $5,
                    $6, $7, $8,
                    $9, NOW(),
                    NOW() + $10 * INTERVAL '1 second'
                )
                RETURNING id, arrival_at
                """,
                attacker["id"],
                defender_realm_id,
                origin[0],
                origin[1],
                origin[2],
                target[0],
                target[1],
                target[2],
                distance,
                travel_seconds,
            )

            for unit_type, quantity in selected.items():
                if quantity <= 0:
                    continue

                await connection.execute(
                    """
                    UPDATE army
                    SET quantity = quantity - $1
                    WHERE realm_id = $2
                      AND unit_type = $3
                    """,
                    quantity,
                    attacker["id"],
                    unit_type,
                )

                await connection.execute(
                    """
                    DELETE FROM army
                    WHERE realm_id = $1
                      AND unit_type = $2
                      AND quantity <= 0
                    """,
                    attacker["id"],
                    unit_type,
                )

                await connection.execute(
                    """
                    INSERT INTO military_mission_units (
                        mission_id,
                        unit_type,
                        quantity,
                        surviving_quantity
                    )
                    VALUES ($1, $2, $3, $3)
                    """,
                    mission["id"],
                    unit_type,
                    quantity,
                )

            return True, {
                "mission_id": mission["id"],
                "attacker_name": attacker["name"],
                "defender_name": defender["name"],
                "distance": distance,
                "travel_seconds": travel_seconds,
                "arrival_at": mission["arrival_at"],
                "troops": selected,
            }


async def recall_mission(user_id, mission_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            mission = await connection.fetchrow(
                """
                SELECT
                    m.*,
                    r.owner_id
                FROM military_missions m
                JOIN realms r
                  ON r.id = m.attacker_realm_id
                WHERE m.id = $1
                FOR UPDATE
                """,
                mission_id,
            )

            if not mission:
                return False, "La misión no existe."

            if mission["owner_id"] != user_id:
                return False, "Esta misión no te pertenece."

            if mission["status"] != "travelling":
                return False, (
                    "Solo puedes retirar tropas "
                    "que todavía están viajando."
                )

            elapsed = await connection.fetchval(
                """
                SELECT EXTRACT(
                    EPOCH FROM NOW() - departure_at
                )
                FROM military_missions
                WHERE id = $1
                """,
                mission_id,
            )

            return_seconds = max(
                30,
                int(elapsed or 30),
            )

            await connection.execute(
                """
                UPDATE military_missions
                SET mission_type = 'return',
                    status = 'returning',
                    arrival_at =
                        NOW() + $1 * INTERVAL '1 second'
                WHERE id = $2
                """,
                return_seconds,
                mission_id,
            )

            return True, {
                "mission_id": mission_id,
                "return_seconds": return_seconds,
            }


async def get_player_missions(user_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        return await connection.fetch(
            """
            SELECT
                m.id,
                m.mission_type,
                m.status,
                m.distance,
                m.departure_at,
                m.arrival_at,
                r.name AS defender_name
            FROM military_missions m
            JOIN realms a
              ON a.id = m.attacker_realm_id
            JOIN realms r
              ON r.id = m.defender_realm_id
            WHERE a.owner_id = $1
              AND m.status IN (
                  'travelling',
                  'battling',
                  'returning'
              )
            ORDER BY m.arrival_at
            """,
            user_id,
        )


async def finish_returning_mission(
    connection,
    mission_id,
):
    mission = await connection.fetchrow(
        """
        SELECT attacker_realm_id
        FROM military_missions
        WHERE id = $1
          AND status = 'returning'
        FOR UPDATE
        """,
        mission_id,
    )

    if not mission:
        return False

    troops = await connection.fetch(
        """
        SELECT unit_type, surviving_quantity
        FROM military_mission_units
        WHERE mission_id = $1
          AND surviving_quantity > 0
        FOR UPDATE
        """,
        mission_id,
    )

    for troop in troops:
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
            mission["attacker_realm_id"],
            troop["unit_type"],
            troop["surviving_quantity"],
        )

    await connection.execute(
        """
        UPDATE military_missions
        SET status = 'completed',
            completed_at = NOW()
        WHERE id = $1
        """,
        mission_id,
    )

    return True

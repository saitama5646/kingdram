import asyncio
import logging

from bot.database.connection import get_pool
from bot.services.missions import finish_returning_mission
from bot.services.military import UNITS


def army_power(troops, mode):
    total = 0

    statistic = (
        "attack"
        if mode == "attack"
        else "defense"
    )

    for troop in troops:
        unit = UNITS.get(troop["unit_type"])

        if not unit:
            continue

        quantity = int(troop["quantity"])

        total += quantity * int(
            unit[statistic]
        )

    return total


async def process_arrival(connection, mission):
    mission_id = mission["id"]

    troops = await connection.fetch(
        """
        SELECT unit_type, quantity
        FROM military_mission_units
        WHERE mission_id = $1
          AND quantity > 0
        FOR UPDATE
        """,
        mission_id,
    )

    defenders = await connection.fetch(
        """
        SELECT unit_type, quantity
        FROM army
        WHERE realm_id = $1
          AND quantity > 0
        FOR UPDATE
        """,
        mission["defender_realm_id"],
    )

    attacker_power = army_power(
        troops,
        "attack",
    )

    defender_power = army_power(
        defenders,
        "defense",
    )

    attacker_wins = (
        attacker_power > defender_power
    )

    if attacker_wins:
        attacker_loss_rate = 0.20
        defender_loss_rate = 0.50
    else:
        attacker_loss_rate = 0.50
        defender_loss_rate = 0.15

    for troop in troops:
        quantity = int(troop["quantity"])

        losses = min(
            quantity,
            int(quantity * attacker_loss_rate + 0.999),
        )

        survivors = quantity - losses

        await connection.execute(
            """
            UPDATE military_mission_units
            SET surviving_quantity = $1
            WHERE mission_id = $2
              AND unit_type = $3
            """,
            survivors,
            mission_id,
            troop["unit_type"],
        )

    for troop in defenders:
        quantity = int(troop["quantity"])

        losses = min(
            quantity,
            int(quantity * defender_loss_rate + 0.999),
        )

        remaining = quantity - losses

        if remaining <= 0:
            await connection.execute(
                """
                DELETE FROM army
                WHERE realm_id = $1
                  AND unit_type = $2
                """,
                mission["defender_realm_id"],
                troop["unit_type"],
            )
        else:
            await connection.execute(
                """
                UPDATE army
                SET quantity = $1
                WHERE realm_id = $2
                  AND unit_type = $3
                """,
                remaining,
                mission["defender_realm_id"],
                troop["unit_type"],
            )

    distance = float(mission["distance"])

    return_seconds = max(
        30,
        int(distance * 10),
    )

    await connection.execute(
        """
        UPDATE military_missions
        SET status = 'returning',
            mission_type = 'return',
            arrival_at =
                NOW() + $1 * INTERVAL '1 second'
        WHERE id = $2
        """,
        return_seconds,
        mission_id,
    )


async def missions_worker():
    print("Sistema de misiones militares iniciado.")

    while True:
        try:
            pool = await get_pool()

            async with pool.acquire() as connection:
                arriving = await connection.fetch(
                    """
                    SELECT *
                    FROM military_missions
                    WHERE status = 'travelling'
                      AND mission_type = 'attack'
                      AND arrival_at <= NOW()
                    ORDER BY arrival_at, id
                    LIMIT 20
                    """
                )

                for mission in arriving:
                    async with connection.transaction():
                        locked = await connection.fetchrow(
                            """
                            SELECT *
                            FROM military_missions
                            WHERE id = $1
                              AND status = 'travelling'
                              AND mission_type = 'attack'
                            FOR UPDATE
                            """,
                            mission["id"],
                        )

                        if locked:
                            await process_arrival(
                                connection,
                                locked,
                            )

                returning = await connection.fetch(
                    """
                    SELECT id
                    FROM military_missions
                    WHERE status = 'returning'
                      AND arrival_at <= NOW()
                    ORDER BY arrival_at, id
                    LIMIT 20
                    """
                )

                for mission in returning:
                    async with connection.transaction():
                        await finish_returning_mission(
                            connection,
                            mission["id"],
                        )

        except asyncio.CancelledError:
            raise

        except Exception:
            logging.exception(
                "Error en el trabajador de misiones."
            )

        await asyncio.sleep(5)

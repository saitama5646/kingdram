import asyncio
import logging
import random

from bot.database.connection import get_pool
from bot.services.missions import finish_returning_mission
from bot.services.military import UNITS


MAX_BATTLE_ROUNDS = 6
DAMAGE_VARIATION = 0.10
MIN_MORALE = 0.60
MAX_MORALE = 1.25


def army_quantity(troops):
    return sum(
        max(0, int(troop["quantity"]))
        for troop in troops
    )


def army_power(troops, mode):
    stat = "attack" if mode == "attack" else "defense"

    total = 0

    for troop in troops:
        unit = UNITS.get(troop["unit_type"])

        if not unit:
            continue

        quantity = max(
            0,
            int(troop["quantity"]),
        )

        total += quantity * int(unit[stat])

    return total


def calculate_morale(troops, initial_quantity):
    current_quantity = army_quantity(troops)

    if initial_quantity <= 0 or current_quantity <= 0:
        return MIN_MORALE

    survival_ratio = (
        current_quantity / initial_quantity
    )

    return max(
        MIN_MORALE,
        min(
            MAX_MORALE,
            0.75 + survival_ratio * 0.25,
        ),
    )


def calculate_damage(
    attackers,
    defenders,
    morale,
):
    attack = army_power(
        attackers,
        "attack",
    )

    defense = army_power(
        defenders,
        "defense",
    )

    defender_count = army_quantity(
        defenders,
    )

    if attack <= 0 or defender_count <= 0:
        return 0.0

    defense_per_unit = max(
        1.0,
        defense / defender_count,
    )

    mitigation = (
        100.0
        / (100.0 + defense_per_unit * 2.0)
    )

    variation = random.uniform(
        1.0 - DAMAGE_VARIATION,
        1.0 + DAMAGE_VARIATION,
    )

    return attack * mitigation * morale * variation


def calculate_losses(troops, damage):
    count = army_quantity(troops)

    if count <= 0 or damage <= 0:
        return {}

    defense = army_power(
        troops,
        "defense",
    )

    defense_per_unit = max(
        1.0,
        defense / count,
    )

    losses_total = min(
        count,
        max(
            0,
            int(damage / defense_per_unit),
        ),
    )

    if losses_total == 0:
        return {}

    distribution = []

    for troop in troops:
        quantity = int(
            troop["quantity"]
        )

        if quantity <= 0:
            continue

        exact = (
            losses_total
            * quantity
            / count
        )

        losses = int(exact)

        distribution.append(
            {
                "unit_type": troop["unit_type"],
                "quantity": quantity,
                "losses": losses,
                "remainder": exact - losses,
            }
        )

    allocated = sum(
        item["losses"]
        for item in distribution
    )

    left = losses_total - allocated

    distribution.sort(
        key=lambda item: item["remainder"],
        reverse=True,
    )

    for item in distribution:
        if left <= 0:
            break

        if item["losses"] < item["quantity"]:
            item["losses"] += 1
            left -= 1

    return {
        item["unit_type"]: item["losses"]
        for item in distribution
        if item["losses"] > 0
    }


def apply_losses(troops, losses):
    survivors = []

    for troop in troops:
        unit_type = troop["unit_type"]

        quantity = int(
            troop["quantity"]
        )

        lost = int(
            losses.get(unit_type, 0)
        )

        remaining = max(
            0,
            quantity - lost,
        )

        if remaining:
            survivors.append(
                {
                    "unit_type": unit_type,
                    "quantity": remaining,
                }
            )

    return survivors


def survivor_map(troops):
    return {
        troop["unit_type"]: int(
            troop["quantity"]
        )
        for troop in troops
    }


async def save_attacker_survivors(
    connection,
    mission_id,
    original_troops,
    survivors,
):
    remaining = survivor_map(
        survivors,
    )

    for troop in original_troops:
        unit_type = troop["unit_type"]

        await connection.execute(
            """
            UPDATE military_mission_units
            SET surviving_quantity = $1
            WHERE mission_id = $2
              AND unit_type = $3
            """,
            remaining.get(unit_type, 0),
            mission_id,
            unit_type,
        )


async def save_defender_survivors(
    connection,
    realm_id,
    original_troops,
    survivors,
):
    remaining = survivor_map(
        survivors,
    )

    for troop in original_troops:
        unit_type = troop["unit_type"]

        quantity = remaining.get(
            unit_type,
            0,
        )

        if quantity <= 0:
            await connection.execute(
                """
                DELETE FROM army
                WHERE realm_id = $1
                  AND unit_type = $2
                """,
                realm_id,
                unit_type,
            )
        else:
            await connection.execute(
                """
                UPDATE army
                SET quantity = $1
                WHERE realm_id = $2
                  AND unit_type = $3
                """,
                quantity,
                realm_id,
                unit_type,
            )


async def process_arrival(
    connection,
    mission,
):
    mission_id = mission["id"]
    defender_realm_id = mission["defender_realm_id"]

    attacker_rows = await connection.fetch(
        """
        SELECT unit_type, quantity
        FROM military_mission_units
        WHERE mission_id = $1
          AND quantity > 0
        FOR UPDATE
        """,
        mission_id,
    )

    defender_rows = await connection.fetch(
        """
        SELECT unit_type, quantity
        FROM army
        WHERE realm_id = $1
          AND quantity > 0
        FOR UPDATE
        """,
        defender_realm_id,
    )

    attackers = [
        {
            "unit_type": row["unit_type"],
            "quantity": int(row["quantity"]),
        }
        for row in attacker_rows
    ]

    defenders = [
        {
            "unit_type": row["unit_type"],
            "quantity": int(row["quantity"]),
        }
        for row in defender_rows
    ]

    attacker_initial = army_quantity(
        attackers,
    )

    defender_initial = army_quantity(
        defenders,
    )

    round_number = 0

    while (
        attackers
        and defenders
        and round_number < MAX_BATTLE_ROUNDS
    ):
        round_number += 1

        attacker_morale = calculate_morale(
            attackers,
            attacker_initial,
        )

        defender_morale = calculate_morale(
            defenders,
            defender_initial,
        )

        attacker_damage = calculate_damage(
            attackers,
            defenders,
            attacker_morale,
        )

        defender_damage = calculate_damage(
            defenders,
            attackers,
            defender_morale,
        )

        attacker_losses = calculate_losses(
            attackers,
            defender_damage,
        )

        defender_losses = calculate_losses(
            defenders,
            attacker_damage,
        )

        attackers = apply_losses(
            attackers,
            attacker_losses,
        )

        defenders = apply_losses(
            defenders,
            defender_losses,
        )

        logging.info(
            (
                "Misión %s | Ronda %s/%s | "
                "Atacantes %s | Defensores %s"
            ),
            mission_id,
            round_number,
            MAX_BATTLE_ROUNDS,
            army_quantity(attackers),
            army_quantity(defenders),
        )

    await save_attacker_survivors(
        connection,
        mission_id,
        attacker_rows,
        attackers,
    )

    await save_defender_survivors(
        connection,
        defender_realm_id,
        defender_rows,
        defenders,
    )

    if attackers and not defenders:
        result = "victoria atacante"
    elif defenders and not attackers:
        result = "victoria defensora"
    elif attackers and defenders:
        result = "combate inconcluso"
    else:
        result = "ambos ejércitos derrotados"

    logging.info(
        "Misión %s: %s.",
        mission_id,
        result,
    )

    return_seconds = max(
        30,
        int(float(mission["distance"]) * 10),
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
    print(
        "Sistema de misiones militares iniciado."
    )

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

import asyncio
import logging
from math import floor

from bot.database.connection import get_pool
from bot.services.missions import finish_returning_mission
from bot.services.military import UNITS


MAX_BATTLE_ROUNDS = 6


def army_power(troops, mode):
    statistic = (
        "attack"
        if mode == "attack"
        else "defense"
    )

    total = 0

    for troop in troops:
        unit = UNITS.get(troop["unit_type"])

        if not unit:
            continue

        quantity = int(troop["quantity"])

        if quantity <= 0:
            continue

        total += quantity * int(unit[statistic])

    return total


def army_quantity(troops):
    return sum(
        int(troop["quantity"])
        for troop in troops
        if int(troop["quantity"]) > 0
    )


def average_defense(troops):
    quantity = army_quantity(troops)

    if quantity <= 0:
        return 1

    total_defense = army_power(
        troops,
        "defense",
    )

    return max(
        1,
        total_defense / quantity,
    )


def calculate_damage(attacking_troops, defending_troops):
    attack_strength = army_power(
        attacking_troops,
        "attack",
    )

    defense_value = average_defense(
        defending_troops,
    )

    if attack_strength <= 0:
        return 0

    mitigation = (
        100
        / (100 + defense_value * 2)
    )

    return attack_strength * mitigation


def calculate_losses(troops, damage):
    total_quantity = army_quantity(troops)

    if total_quantity <= 0 or damage <= 0:
        return {}

    defense_value = average_defense(troops)

    estimated_losses = int(
        damage / defense_value
    )

    estimated_losses = max(
        0,
        min(
            total_quantity,
            estimated_losses,
        ),
    )

    if estimated_losses <= 0:
        return {}

    distribution = []

    for troop in troops:
        quantity = int(troop["quantity"])

        if quantity <= 0:
            continue

        exact_share = (
            estimated_losses
            * quantity
            / total_quantity
        )

        base_losses = floor(exact_share)

        distribution.append(
            {
                "unit_type": troop["unit_type"],
                "quantity": quantity,
                "losses": base_losses,
                "remainder": (
                    exact_share - base_losses
                ),
            }
        )

    allocated = sum(
        item["losses"]
        for item in distribution
    )

    remaining = (
        estimated_losses - allocated
    )

    distribution.sort(
        key=lambda item: item["remainder"],
        reverse=True,
    )

    for item in distribution:
        if remaining <= 0:
            break

        if item["losses"] < item["quantity"]:
            item["losses"] += 1
            remaining -= 1

    return {
        item["unit_type"]: item["losses"]
        for item in distribution
        if item["losses"] > 0
    }


def apply_losses(troops, losses):
    result = []

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

        if remaining > 0:
            result.append(
                {
                    "unit_type": unit_type,
                    "quantity": remaining,
                }
            )

    return result


async def update_attacker_survivors(
    connection,
    mission_id,
    troops,
):
    for troop in troops:
        await connection.execute(
            """
            UPDATE military_mission_units
            SET surviving_quantity = $1
            WHERE mission_id = $2
              AND unit_type = $3
            """,
            int(troop["quantity"]),
            mission_id,
            troop["unit_type"],
        )


async def update_defender_survivors(
    connection,
    defender_realm_id,
    troops,
):
    for troop in troops:
        quantity = int(
            troop["quantity"]
        )

        if quantity <= 0:
            await connection.execute(
                """
                DELETE FROM army
                WHERE realm_id = $1
                  AND unit_type = $2
                """,
                defender_realm_id,
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
                quantity,
                defender_realm_id,
                troop["unit_type"],
            )


async def process_arrival(connection, mission):
    mission_id = mission["id"]

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
        mission["defender_realm_id"],
    )

    attackers = [
        {
            "unit_type": troop["unit_type"],
            "quantity": int(troop["quantity"]),
        }
        for troop in attacker_rows
    ]

    defenders = [
        {
            "unit_type": troop["unit_type"],
            "quantity": int(troop["quantity"]),
        }
        for troop in defender_rows
    ]

    if not attackers:
        logging.info(
            "Misión %s: ejército atacante vacío.",
            mission_id,
        )

    elif not defenders:
        logging.info(
            "Misión %s: reino defensor sin tropas.",
            mission_id,
        )

    battle_round = 0

    while (
        attackers
        and defenders
        and battle_round < MAX_BATTLE_ROUNDS
    ):
        battle_round += 1

        attacker_damage = calculate_damage(
            attackers,
            defenders,
        )

        defender_damage = calculate_damage(
            defenders,
            attackers,
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
                "Misión %s | Ronda %s | "
                "Atacantes restantes: %s | "
                "Defensores restantes: %s"
            ),
            mission_id,
            battle_round,
            army_quantity(attackers),
            army_quantity(defenders),
        )

    await update_attacker_survivors(
        connection,
        mission_id,
        attackers,
    )

    await update_defender_survivors(
        connection,
        mission["defender_realm_id"],
        defenders,
    )

    if attackers and not defenders:
        result = "victoria atacante"

    elif defenders and not attackers:
        result = "victoria defensora"

    elif attackers and defenders:
        result = "combate inconcluso"

    else:
        result = "empate por aniquilación"

    logging.info(
        "Misión %s finalizada: %s.",
        mission_id,
        result,
    )

    distance = float(
        mission["distance"]
    )

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

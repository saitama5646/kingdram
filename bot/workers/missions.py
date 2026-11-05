import asyncio
import json
import logging
import random

from bot.database.connection import get_pool
from bot.services.missions import finish_returning_mission
from bot.services.military import UNITS


MAX_BATTLE_ROUNDS = 6
DAMAGE_VARIATION = 0.10

MIN_MORALE = 0.25
MAX_MORALE = 1.25

MORALE_LOSS_FACTOR = 0.45
MORALE_ADVANTAGE_FACTOR = 0.10


def army_quantity(troops):
    return sum(max(0, int(t["quantity"])) for t in troops)


def army_power(troops, stat):
    return sum(
        max(0, int(t["quantity"]))
        * int(UNITS.get(t["unit_type"], {}).get(stat, 0))
        for t in troops
    )


def survivor_map(troops):
    return {
        t["unit_type"]: int(t["quantity"])
        for t in troops
    }


def initial_morale(own, enemy):
    if enemy <= 0:
        bonus = 0.10
    else:
        ratio = own / enemy

        if ratio >= 2:
            bonus = 0.10
        elif ratio >= 1.5:
            bonus = 0.07
        elif ratio >= 1.2:
            bonus = 0.04
        elif ratio <= 0.5:
            bonus = -0.10
        elif ratio <= 0.67:
            bonus = -0.07
        elif ratio <= 0.83:
            bonus = -0.04
        else:
            bonus = 0.0

    return max(MIN_MORALE, min(MAX_MORALE, 1.0 + bonus))


def update_morale(
    morale,
    own_losses,
    own_before,
    enemy_losses,
    enemy_before,
):
    own_ratio = own_losses / own_before if own_before else 0.0
    enemy_ratio = enemy_losses / enemy_before if enemy_before else 0.0

    change = (
        -own_ratio * MORALE_LOSS_FACTOR
        + enemy_ratio * MORALE_ADVANTAGE_FACTOR
    )

    return max(
        MIN_MORALE,
        min(MAX_MORALE, morale + change),
    )


def calculate_damage(attackers, defenders, morale):
    attack = army_power(attackers, "attack")
    defense = army_power(defenders, "defense")
    count = army_quantity(defenders)

    if attack <= 0 or count <= 0:
        return 0.0

    defense_per_unit = max(1.0, defense / count)
    mitigation = 100.0 / (100.0 + defense_per_unit * 2.0)

    variation = random.uniform(
        1.0 - DAMAGE_VARIATION,
        1.0 + DAMAGE_VARIATION,
    )

    return attack * mitigation * morale * variation


def calculate_losses(troops, damage):
    total_units = army_quantity(troops)

    if total_units <= 0 or damage <= 0:
        return {}

    defense = army_power(troops, "defense")
    defense_per_unit = max(1.0, defense / total_units)

    losses_total = int(
        damage / max(1.0, defense_per_unit * 0.25)
    )

    losses_total = min(total_units, max(0, losses_total))

    if losses_total <= 0:
        return {}

    distribution = []

    for troop in troops:
        quantity = max(0, int(troop["quantity"]))

        if quantity <= 0:
            continue

        exact = losses_total * quantity / total_units
        base_losses = min(quantity, int(exact))

        distribution.append({
            "unit_type": troop["unit_type"],
            "quantity": quantity,
            "losses": base_losses,
            "remainder": exact - base_losses,
        })

    allocated = sum(item["losses"] for item in distribution)
    remaining = losses_total - allocated

    distribution.sort(
        key=lambda item: item["remainder"],
        reverse=True,
    )

    while remaining > 0:
        changed = False

        for item in distribution:
            if remaining <= 0:
                break

            if item["losses"] < item["quantity"]:
                item["losses"] += 1
                remaining -= 1
                changed = True

        if not changed:
            break

    return {
        item["unit_type"]: item["losses"]
        for item in distribution
        if item["losses"] > 0
    }


def apply_losses(troops, losses):
    survivors = []

    for troop in troops:
        unit_type = troop["unit_type"]

        remaining = max(
            0,
            int(troop["quantity"])
            - int(losses.get(unit_type, 0)),
        )

        if remaining:
            survivors.append({
                "unit_type": unit_type,
                "quantity": remaining,
            })

    return survivors


def losses_map(original, survivors):
    remaining = survivor_map(survivors)

    return {
        troop["unit_type"]: max(
            0,
            int(troop["quantity"])
            - remaining.get(troop["unit_type"], 0),
        )
        for troop in original
    }


async def save_attacker_survivors(
    connection,
    mission_id,
    original,
    survivors,
):
    remaining = survivor_map(survivors)

    for troop in original:
        await connection.execute(
            """
            UPDATE military_mission_units
            SET surviving_quantity = $1
            WHERE mission_id = $2
              AND unit_type = $3
            """,
            remaining.get(troop["unit_type"], 0),
            mission_id,
            troop["unit_type"],
        )


async def save_defender_survivors(
    connection,
    realm_id,
    original,
    survivors,
):
    remaining = survivor_map(survivors)

    for troop in original:
        unit_type = troop["unit_type"]
        quantity = remaining.get(unit_type, 0)

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


async def save_report(
    connection,
    mission,
    attackers,
    defenders,
    attacker_original,
    defender_original,
    attacker_power_initial,
    defender_power_initial,
    attacker_losses_total,
    defender_losses_total,
    attacker_morale,
    defender_morale,
    rounds,
    round_log,
):
    attacker_realm_id = mission["attacker_realm_id"]
    defender_realm_id = mission["defender_realm_id"]

    owners = await connection.fetch(
        """
        SELECT id, owner_id
        FROM realms
        WHERE id = ANY($1::BIGINT[])
        """,
        [attacker_realm_id, defender_realm_id],
    )

    owner_map = {
        int(row["id"]): int(row["owner_id"])
        for row in owners
    }

    attacker_owner = owner_map[attacker_realm_id]
    defender_owner = owner_map[defender_realm_id]

    attacker_remaining_power = army_power(attackers, "attack")
    defender_remaining_power = army_power(defenders, "defense")

    if attackers and not defenders:
        outcome = "attacker_victory"
        winner = attacker_realm_id
    elif defenders and not attackers:
        outcome = "defender_victory"
        winner = defender_realm_id
    elif attackers and defenders:
        outcome = "inconclusive"
        winner = None
    else:
        outcome = "mutual_destruction"
        winner = None

    report_id = await connection.fetchval(
        """
        INSERT INTO battle_reports (
            attacker_realm_id,
            defender_realm_id,
            attacker_owner_id,
            defender_owner_id,
            winner_realm_id,
            attacker_power,
            defender_power,
            attacker_losses,
            defender_losses,
            outcome,
            rounds,
            attacker_morale,
            defender_morale,
            round_log
        )
        VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12, $13, $14::JSONB
        )
        RETURNING id
        """,
        attacker_realm_id,
        defender_realm_id,
        attacker_owner,
        defender_owner,
        winner,
        attacker_power_initial,
        defender_power_initial,
        attacker_losses_total,
        defender_losses_total,
        outcome,
        rounds,
        round(attacker_morale, 3),
        round(defender_morale, 3),
        json.dumps(round_log),
    )

    attacker_lost = losses_map(attacker_original, attackers)
    defender_lost = losses_map(defender_original, defenders)

    attacker_remaining = survivor_map(attackers)
    defender_remaining = survivor_map(defenders)

    for troop in attacker_original:
        unit_type = troop["unit_type"]

        await connection.execute(
            """
            INSERT INTO battle_unit_results (
                battle_id,
                realm_id,
                unit_type,
                initial_quantity,
                lost_quantity,
                remaining_quantity
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            report_id,
            attacker_realm_id,
            unit_type,
            int(troop["quantity"]),
            attacker_lost.get(unit_type, 0),
            attacker_remaining.get(unit_type, 0),
        )

    for troop in defender_original:
        unit_type = troop["unit_type"]

        await connection.execute(
            """
            INSERT INTO battle_unit_results (
                battle_id,
                realm_id,
                unit_type,
                initial_quantity,
                lost_quantity,
                remaining_quantity
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            report_id,
            defender_realm_id,
            unit_type,
            int(troop["quantity"]),
            defender_lost.get(unit_type, 0),
            defender_remaining.get(unit_type, 0),
        )

    return report_id, outcome


async def process_arrival(connection, mission):
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

    attacker_original = [dict(troop) for troop in attackers]
    defender_original = [dict(troop) for troop in defenders]

    attacker_initial = army_quantity(attackers)
    defender_initial = army_quantity(defenders)

    attacker_power_initial = army_power(attackers, "attack")
    defender_power_initial = army_power(defenders, "defense")

    attacker_morale = initial_morale(
        attacker_initial,
        defender_initial,
    )

    defender_morale = initial_morale(
        defender_initial,
        attacker_initial,
    )

    round_number = 0
    round_log = []

    logging.info(
        "MISIÓN %s: combate iniciado. A=%s D=%s",
        mission_id,
        attacker_initial,
        defender_initial,
    )

    while (
        attackers
        and defenders
        and round_number < MAX_BATTLE_ROUNDS
    ):
        round_number += 1

        attacker_before = army_quantity(attackers)
        defender_before = army_quantity(defenders)

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

        attacker_losses_map = calculate_losses(
            attackers,
            defender_damage,
        )

        defender_losses_map = calculate_losses(
            defenders,
            attacker_damage,
        )

        attacker_losses = sum(attacker_losses_map.values())
        defender_losses = sum(defender_losses_map.values())

        attacker_morale = update_morale(
            attacker_morale,
            attacker_losses,
            attacker_before,
            defender_losses,
            defender_before,
        )

        defender_morale = update_morale(
            defender_morale,
            defender_losses,
            defender_before,
            attacker_losses,
            attacker_before,
        )

        attackers = apply_losses(
            attackers,
            attacker_losses_map,
        )

        defenders = apply_losses(
            defenders,
            defender_losses_map,
        )

        round_log.append({
            "round": round_number,
            "attacker_damage": round(attacker_damage, 2),
            "defender_damage": round(defender_damage, 2),
            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
            "attacker_remaining": army_quantity(attackers),
            "defender_remaining": army_quantity(defenders),
            "attacker_morale": round(attacker_morale, 3),
            "defender_morale": round(defender_morale, 3),
        })

        logging.info(
            "MISIÓN %s | RONDA %s | Bajas A=%s D=%s | Moral A=%.2f D=%.2f",
            mission_id,
            round_number,
            attacker_losses,
            defender_losses,
            attacker_morale,
            defender_morale,
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

    attacker_losses_total = (
        attacker_initial - army_quantity(attackers)
    )

    defender_losses_total = (
        defender_initial - army_quantity(defenders)
    )

    report_id, outcome = await save_report(
        connection,
        mission,
        attackers,
        defenders,
        attacker_original,
        defender_original,
        attacker_power_initial,
        defender_power_initial,
        attacker_losses_total,
        defender_losses_total,
        attacker_morale,
        defender_morale,
        round_number,
        round_log,
    )

    logging.info(
        "MISIÓN %s | INFORME #%s | RESULTADO=%s",
        mission_id,
        report_id,
        outcome,
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
            arrival_at = NOW() + $1 * INTERVAL '1 second'
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
                    SELECT id
                    FROM military_missions
                    WHERE status = 'travelling'
                      AND mission_type = 'attack'
                      AND arrival_at <= NOW()
                    ORDER BY arrival_at, id
                    LIMIT 20
                    """
                )

                for item in arriving:
                    async with connection.transaction():
                        mission = await connection.fetchrow(
                            """
                            SELECT *
                            FROM military_missions
                            WHERE id = $1
                              AND status = 'travelling'
                              AND mission_type = 'attack'
                            FOR UPDATE
                            """,
                            item["id"],
                        )

                        if mission:
                            await process_arrival(
                                connection,
                                mission,
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

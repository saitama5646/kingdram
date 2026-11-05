
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

        quantity = max(0, int(troop["quantity"]))

        total += quantity * int(unit[stat])

    return total


def morale_advantage(own_initial, enemy_initial):
    if own_initial <= 0:
        return -0.10

    if enemy_initial <= 0:
        return 0.10

    ratio = own_initial / enemy_initial

    if ratio >= 2.0:
        return 0.10

    if ratio >= 1.5:
        return 0.07

    if ratio >= 1.2:
        return 0.04

    if ratio <= 0.5:
        return -0.10

    if ratio <= 0.67:
        return -0.07

    if ratio <= 0.83:
        return -0.04

    return 0.0


def initial_morale(own_initial, enemy_initial):
    return max(
        MIN_MORALE,
        min(
            MAX_MORALE,
            1.0 + morale_advantage(
                own_initial,
                enemy_initial,
            ),
        ),
    )


def update_morale(
    current_morale,
    own_losses,
    own_quantity_before,
    enemy_losses,
    enemy_quantity_before,
):
    own_ratio = (
        own_losses / own_quantity_before
        if own_quantity_before > 0
        else 1.0
    )

    enemy_ratio = (
        enemy_losses / enemy_quantity_before
        if enemy_quantity_before > 0
        else 0.0
    )

    morale_change = (
        -own_ratio * MORALE_LOSS_FACTOR
        + enemy_ratio * MORALE_ADVANTAGE_FACTOR
    )

    return max(
        MIN_MORALE,
        min(
            MAX_MORALE,
            current_morale + morale_change,
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

    return (
        attack
        * mitigation
        * morale
        * variation
    )


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


def losses_map(original, survivors):
    remaining = survivor_map(survivors)

    result = {}

    for troop in original:
        unit_type = troop["unit_type"]

        initial = int(troop["quantity"])
        final = remaining.get(unit_type, 0)

        result[unit_type] = max(
            0,
            initial - final,
        )

    return result


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


async def save_battle_report(
    connection,
    mission,
    attackers,
    defenders,
    attacker_initial,
    defender_initial,
    attacker_power_initial,
    defender_power_initial,
    attacker_losses,
    defender_losses,
    attacker_morale,
    defender_morale,
    round_number,
    round_log,
):
    attacker_realm_id = mission["attacker_realm_id"]
    defender_realm_id = mission["defender_realm_id"]

    realm_owners = await connection.fetch(
        """
        SELECT id, owner_id
        FROM realms
        WHERE id = ANY($1::BIGINT[])
        """,
        [
            attacker_realm_id,
            defender_realm_id,
        ],
    )

    owners = {
        int(row["id"]): int(row["owner_id"])
        for row in realm_owners
    }

    attacker_owner_id = owners.get(
        int(attacker_realm_id)
    )

    defender_owner_id = owners.get(
        int(defender_realm_id)
    )

    if attacker_owner_id is None or defender_owner_id is None:
        raise RuntimeError(
            "No se pudieron identificar los propietarios de los reinos."
        )

    attacker_survivors = army_quantity(
        attackers,
    )

    defender_survivors = army_quantity(
        defenders,
    )

    if attackers and not defenders:
        outcome = "attacker_victory"
        winner_realm_id = attacker_realm_id

    elif defenders and not attackers:
        outcome = "defender_victory"
        winner_realm_id = defender_realm_id

    elif attackers and defenders:
        outcome = "inconclusive"

        attacker_remaining_power = army_power(
            attackers,
            "attack",
        )

        defender_remaining_power = army_power(
            defenders,
            "attack",
        )

        winner_realm_id = (
            attacker_realm_id
            if attacker_remaining_power > defender_remaining_power
            else defender_realm_id
        )

    else:
        outcome = "mutual_destruction"
        winner_realm_id = defender_realm_id

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
        attacker_owner_id,
        defender_owner_id,
        winner_realm_id,
        attacker_power_initial,
        defender_power_initial,
        attacker_losses,
        defender_losses,
        outcome,
        round_number,
        round(attacker_morale, 3),
        round(defender_morale, 3),
        json.dumps(round_log),
    )

    attacker_loss_map = losses_map(
        mission["attacker_original"],
        attackers,
    )

    defender_loss_map = losses_map(
        mission["defender_original"],
        defenders,
    )

    attacker_remaining_map = survivor_map(
        attackers,
    )

    defender_remaining_map = survivor_map(
        defenders,
    )

    for troop in mission["attacker_original"]:
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
            attacker_loss_map.get(unit_type, 0),
            attacker_remaining_map.get(unit_type, 0),
        )

    for troop in mission["defender_original"]:
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
            defender_loss_map.get(unit_type, 0),
            defender_remaining_map.get(unit_type, 0),
        )

    return report_id, outcome


async def process_arrival(
    connection,
    mission,
):
    mission_id = mission["id"]

    attacker_realm_id = mission["attacker_realm_id"]
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

    attacker_original = [
        dict(troop)
        for troop in attackers
    ]

    defender_original = [
        dict(troop)
        for troop in defenders
    ]

    attacker_initial = army_quantity(
        attackers,
    )

    defender_initial = army_quantity(
        defenders,
    )

    attacker_power_initial = army_power(
        attackers,
        "attack",
    )

    defender_power_initial = army_power(
        defenders,
        "attack",
    )

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

    while (
        attackers
        and defenders
        and round_number < MAX_BATTLE_ROUNDS
    ):
        round_number += 1

        attacker_count_before = army_quantity(
            attackers,
        )

        defender_count_before = army_quantity(
            defenders,
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

        attacker_losses_map = calculate_losses(
            attackers,
            defender_damage,
        )

        defender_losses_map = calculate_losses(
            defenders,
            attacker_damage,
        )

        attacker_losses_this_round = sum(
            attacker_losses_map.values()
        )

        defender_losses_this_round = sum(
            defender_losses_map.values()
        )

        attacker_morale = update_morale(
            attacker_morale,
            attacker_losses_this_round,
            attacker_count_before,
            defender_losses_this_round,
            defender_count_before,
        )

        defender_morale = update_morale(
            defender_morale,
            defender_losses_this_round,
            defender_count_before,
            attacker_losses_this_round,
            attacker_count_before,
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
            "attacker_losses": attacker_losses_this_round,
            "defender_losses": defender_losses_this_round,
            "attacker_remaining": army_quantity(attackers),
            "defender_remaining": army_quantity(defenders),
            "attacker_morale": round(attacker_morale, 3),
            "defender_morale": round(defender_morale, 3),
        })

        logging.info(
            (
                "Misión %s | Ronda %s/%s | "
                "Pérdidas atacante %s | "
                "Pérdidas defensor %s | "
                "Moral atacante %.3f | "
                "Moral defensor %.3f"
            ),
            mission_id,
            round_number,
            MAX_BATTLE_ROUNDS,
            attacker_losses_this_round,
            defender_losses_this_round,
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
        attacker_initial
        - army_quantity(attackers)
    )

    defender_losses_total = (
        defender_initial
        - army_quantity(defenders)
    )

    mission_data = dict(mission)

    mission_data["attacker_original"] = attacker_original
    mission_data["defender_original"] = defender_original

    report_id, outcome = await save_battle_report(
        connection,
        mission_data,
        attackers,
        defenders,
        attacker_initial,
        defender_initial,
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
        "Misión %s: informe #%s guardado (%s).",
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

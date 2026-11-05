
import asyncio
import json
import logging
import random
from math import ceil

from bot.database.connection import get_pool
from bot.services.missions import finish_returning_mission
from bot.services.military import UNITS
from bot.services.research import get_research_effects
from bot.services.construction import BUILDINGS


MAX_BATTLE_ROUNDS = 6
DAMAGE_VARIATION = 0.10

MIN_MORALE = 0.25
MAX_MORALE = 1.25

MORALE_LOSS_FACTOR = 0.45
MORALE_ADVANTAGE_FACTOR = 0.10

BUILDING_COST_GROWTH = 1.65
MAX_INFRASTRUCTURE_DAMAGE = 0.65
MIN_DAMAGE_FOR_VASSALAGE = 0.50


def army_quantity(troops):
    return sum(max(0, int(t["quantity"])) for t in troops)


def army_power(troops, stat, research_effects=None):
    research_effects = research_effects or {}

    effect_name = (
        "military_attack"
        if stat == "attack"
        else "military_defense"
        if stat == "defense"
        else None
    )

    multiplier = 1.0

    if effect_name:
        multiplier += max(
            0.0,
            float(research_effects.get(effect_name, 0)),
        )

    return sum(
        max(0, int(troop["quantity"]))
        * float(UNITS.get(troop["unit_type"], {}).get(stat, 0))
        * multiplier
        for troop in troops
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
    if not attackers or not defenders:
        return 0.0

    return max(
        0.0,
        army_power(attackers, "attack") * float(morale),
    )


async def load_combat_research_effects(connection, realm_id):
    rows = await connection.fetch(
        """
        SELECT research_type, level
        FROM realm_research
        WHERE realm_id = $1
        """,
        realm_id,
    )

    levels = {
        row["research_type"]: int(row["level"])
        for row in rows
    }

    return get_research_effects(levels)


def expand_combat_units(troops, research_effects=None):
    research_effects = research_effects or {}

    attack_multiplier = 1.0 + max(
        0.0,
        float(research_effects.get("military_attack", 0)),
    )

    hull_bonus = max(
        float(research_effects.get("military_hull", 0)),
        float(research_effects.get("military_defense", 0)),
    )

    defense_multiplier = 1.0 + max(0.0, hull_bonus)

    shield_multiplier = 1.0 + max(
        0.0,
        float(research_effects.get("military_shield", 0)),
    )

    units = []

    for troop in troops:
        unit_type = troop["unit_type"]
        quantity = max(0, int(troop["quantity"]))
        definition = UNITS.get(unit_type)

        if not definition:
            continue

        attack = max(
            0.0,
            float(definition.get("attack", 0)) * attack_multiplier,
        )

        shield = max(
            0.0,
            float(definition.get("shield", 0)) * shield_multiplier,
        )

        hull = max(
            1.0,
            float(definition.get("hull", 100)) * defense_multiplier,
        )

        for _ in range(quantity):
            units.append({
                "unit_type": unit_type,
                "attack": attack,
                "shield": shield,
                "hull": hull,
                "hull_damage": 0.0,
                "destroyed": False,
            })

    return units


def aggregate_combat_units(units):
    quantities = {}

    for unit in units:
        if unit.get("destroyed", False):
            continue

        unit_type = unit["unit_type"]
        quantities[unit_type] = quantities.get(unit_type, 0) + 1

    return [
        {
            "unit_type": unit_type,
            "quantity": quantity,
        }
        for unit_type, quantity in sorted(quantities.items())
        if quantity > 0
    ]


def resolve_volley(shooters, targets, morale):
    """
    Resuelve los disparos de un bando contra el contrario.

    - Cada unidad dispara una vez.
    - Los objetivos se seleccionan aleatoriamente.
    - Los escudos absorben el daño antes que el blindaje.
    - Los escudos se recuperan en la siguiente ronda.
    - El daño al blindaje permanece.
    - La explosión se comprueba después de cada impacto.
    - Las unidades destruidas permanecen en la lista hasta
      que termine la ronda, para no alterar la selección.
    """

    if not shooters or not targets:
        return 0.0, targets

    shield_remaining = [
        max(0.0, float(target.get("shield", 0)))
        for target in targets
    ]

    total_damage = 0.0
    morale = max(0.0, float(morale))

    for shooter in shooters:
        if shooter.get("destroyed", False):
            continue

        if not targets:
            break

        attack = max(
            0.0,
            float(shooter.get("attack", 0)) * morale,
        )

        if attack <= 0:
            continue

        target_index = random.randrange(len(targets))
        target = targets[target_index]

        if target.get("destroyed", False):
            continue

        maximum_shield = max(
            0.0,
            float(target.get("shield", 0)),
        )

        # Regla del 1%: impactos demasiado débiles
        # no afectan al objetivo.
        if (
            maximum_shield > 0
            and attack < maximum_shield * 0.01
        ):
            continue

        absorbed = min(
            shield_remaining[target_index],
            attack,
        )

        shield_remaining[target_index] -= absorbed

        penetrating_damage = max(
            0.0,
            attack - absorbed,
        )

        target["hull_damage"] = (
            float(target.get("hull_damage", 0))
            + penetrating_damage
        )

        total_damage += attack

        maximum_hull = max(
            1.0,
            float(target.get("hull", 100)),
        )

        remaining_hull = max(
            0.0,
            maximum_hull - target["hull_damage"],
        )

        if remaining_hull <= 0:
            target["destroyed"] = True
            continue

        # Regla de explosión: por debajo del 70% de
        # blindaje, cada impacto puede destruir la unidad.
        if remaining_hull < maximum_hull * 0.70:
            destruction_chance = 1.0 - (
                remaining_hull / maximum_hull
            )

            if random.random() < destruction_chance:
                target["destroyed"] = True

    return total_damage, targets


def resolve_battle_round(
    attackers,
    defenders,
    attacker_morale,
    defender_morale,
):
    """
    Una ronda completa.

    Los dos ejércitos conservan una copia de sus unidades
    al inicio de la ronda. Por tanto, una unidad destruida
    durante esta ronda todavía puede disparar antes de que
    se retiren las bajas.
    """

    attacker_shooters = [
        dict(unit)
        for unit in attackers
        if not unit.get("destroyed", False)
    ]

    defender_shooters = [
        dict(unit)
        for unit in defenders
        if not unit.get("destroyed", False)
    ]

    attacker_damage, _ = resolve_volley(
        attacker_shooters,
        defenders,
        attacker_morale,
    )

    defender_damage, _ = resolve_volley(
        defender_shooters,
        attackers,
        defender_morale,
    )

    attackers_after = [
        unit
        for unit in attackers
        if not unit.get("destroyed", False)
    ]

    defenders_after = [
        unit
        for unit in defenders
        if not unit.get("destroyed", False)
    ]

    return (
        attackers_after,
        defenders_after,
        attacker_damage,
        defender_damage,
    )


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


def infrastructure_value(buildings):
    total = 0

    for building in buildings:
        definition = BUILDINGS.get(building["building_type"])
        level = int(building["level"])

        if not definition or level <= 0:
            continue

        base_value = sum(
            int(amount)
            for amount in definition["base_cost"].values()
        )

        for current_level in range(1, level + 1):
            total += ceil(
                base_value
                * (BUILDING_COST_GROWTH ** (current_level - 1))
            )

    return total


async def damage_infrastructure(
    connection,
    realm_id,
    target_damage,
):
    buildings = await connection.fetch(
        """
        SELECT id, building_type, level
        FROM buildings
        WHERE realm_id = $1
        ORDER BY level DESC, id
        FOR UPDATE
        """,
        realm_id,
    )

    before = infrastructure_value(buildings)
    infrastructure_log = []

    if before <= 0 or target_damage <= 0:
        return before, before, 0.0, infrastructure_log

    target_damage = max(
        0.0,
        min(float(target_damage), MAX_INFRASTRUCTURE_DAMAGE),
    )

    target_value = int(before * target_damage)
    remaining_target = target_value

    planned_levels = {
        int(building["id"]): int(building["level"])
        for building in buildings
    }

    building_values = {}

    for building in buildings:
        definition = BUILDINGS.get(building["building_type"])

        if not definition:
            continue

        building_values[int(building["id"])] = sum(
            int(amount)
            for amount in definition["base_cost"].values()
        )

    # Destruye niveles sin superar el presupuesto de daño.
    while remaining_target > 0:
        candidates = []

        for building in buildings:
            building_id = int(building["id"])
            level = planned_levels[building_id]
            base_value = building_values.get(building_id, 0)

            if level <= 0 or base_value <= 0:
                continue

            level_value = ceil(
                base_value * (BUILDING_COST_GROWTH ** (level - 1))
            )

            if level_value <= remaining_target:
                candidates.append((level_value, building_id))

        if not candidates:
            break

        level_value, building_id = max(
            candidates,
            key=lambda item: (item[0], -item[1]),
        )

        planned_levels[building_id] -= 1
        remaining_target -= level_value

    for building in buildings:
        building_id = int(building["id"])
        original_level = int(building["level"])
        new_level = planned_levels[building_id]

        if new_level == original_level:
            continue

        if new_level <= 0:
            await connection.execute(
                """
                DELETE FROM buildings
                WHERE id = $1
                """,
                building_id,
            )
        else:
            await connection.execute(
                """
                UPDATE buildings
                SET level = $1
                WHERE id = $2
                """,
                new_level,
                building_id,
            )

        infrastructure_log.append({
            "building_type": building["building_type"],
            "old_level": original_level,
            "new_level": new_level,
            "destroyed_levels": original_level - new_level,
        })

    remaining_buildings = await connection.fetch(
        """
        SELECT building_type, level
        FROM buildings
        WHERE realm_id = $1
        """,
        realm_id,
    )

    after = infrastructure_value(remaining_buildings)

    actual_damage = (
        max(0, before - after) / before
        if before > 0
        else 0.0
    )

    return (
        before,
        after,
        min(MAX_INFRASTRUCTURE_DAMAGE, actual_damage),
        infrastructure_log,
    )


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

    infrastructure_before = 0
    infrastructure_after = 0
    infrastructure_damage = 0.0
    infrastructure_log = []
    vassalage_unlocked = False

    if outcome == "attacker_victory":
        if defender_power_initial <= 0:
            target_damage = MAX_INFRASTRUCTURE_DAMAGE
        else:
            ratio = attacker_power_initial / defender_power_initial

            target_damage = min(
                MAX_INFRASTRUCTURE_DAMAGE,
                max(0.15, 0.15 + max(0, ratio - 1) * 0.12),
            )

        (
            infrastructure_before,
            infrastructure_after,
            infrastructure_damage,
            infrastructure_log,
        ) = await damage_infrastructure(
            connection,
            defender_realm_id,
            target_damage,
        )

        vassalage_unlocked = (
            infrastructure_damage >= MIN_DAMAGE_FOR_VASSALAGE
        )

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
            infrastructure_before,
            infrastructure_after,
            infrastructure_damage,
            vassalage_unlocked,
            outcome,
            rounds,
            attacker_morale,
            defender_morale,
            round_log,
            infrastructure_log
        )
        VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12, $13,
            $14, $15, $16, $17, $18::JSONB, $19::JSONB
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
        infrastructure_before,
        infrastructure_after,
        infrastructure_damage,
        vassalage_unlocked,
        outcome,
        rounds,
        round(attacker_morale, 3),
        round(defender_morale, 3),
        json.dumps(round_log),
        json.dumps(infrastructure_log),
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

    attacker_research_effects = (
        await load_combat_research_effects(
            connection,
            mission["attacker_realm_id"],
        )
    )

    defender_research_effects = (
        await load_combat_research_effects(
            connection,
            defender_realm_id,
        )
    )

    attacker_power_initial = army_power(
        attackers,
        "attack",
        attacker_research_effects,
    )

    defender_power_initial = army_power(
        defenders,
        "defense",
        defender_research_effects,
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

    attacker_combat_units = expand_combat_units(
        attackers,
        attacker_research_effects,
    )

    defender_combat_units = expand_combat_units(
        defenders,
        defender_research_effects,
    )

    logging.info(
        "MISIÓN %s: combate iniciado. A=%s D=%s",
        mission_id,
        attacker_initial,
        defender_initial,
    )

    while (
        attacker_combat_units
        and defender_combat_units
        and round_number < MAX_BATTLE_ROUNDS
    ):
        round_number += 1

        attacker_before = len(attacker_combat_units)
        defender_before = len(defender_combat_units)

        (
            attacker_combat_units,
            defender_combat_units,
            attacker_damage,
            defender_damage,
        ) = resolve_battle_round(
            attacker_combat_units,
            defender_combat_units,
            attacker_morale,
            defender_morale,
        )

        attackers = aggregate_combat_units(attacker_combat_units)
        defenders = aggregate_combat_units(defender_combat_units)

        attacker_losses = (
            attacker_before - len(attacker_combat_units)
        )
        defender_losses = (
            defender_before - len(defender_combat_units)
        )

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

        round_log.append({
            "round": round_number,
            "attacker_damage": round(attacker_damage, 2),
            "defender_damage": round(defender_damage, 2),
            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
            "attacker_remaining": len(attacker_combat_units),
            "defender_remaining": len(defender_combat_units),
            "attacker_morale": round(attacker_morale, 3),
            "defender_morale": round(defender_morale, 3),
        })

        logging.info(
            "MISIÓN %s | RONDA %s | Bajas A=%s D=%s | Restantes A=%s D=%s",
            mission_id,
            round_number,
            attacker_losses,
            defender_losses,
            len(attacker_combat_units),
            len(defender_combat_units),
        )

    attackers = aggregate_combat_units(attacker_combat_units)
    defenders = aggregate_combat_units(defender_combat_units)

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

    return report_id, outcome


async def send_battle_notifications(bot, report_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        report = await connection.fetchrow(
            """
            SELECT
                br.*,
                attacker.name AS attacker_name,
                defender.name AS defender_name
            FROM battle_reports br
            JOIN realms attacker
              ON attacker.id = br.attacker_realm_id
            JOIN realms defender
              ON defender.id = br.defender_realm_id
            WHERE br.id = $1
            """,
            report_id,
        )

    if not report:
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    if report["outcome"] == "attacker_victory":
        result = f"🏆 Victoria de {report['attacker_name']}"
    elif report["outcome"] == "defender_victory":
        result = f"🛡️ Defensa exitosa de {report['defender_name']}"
    elif report["outcome"] == "inconclusive":
        result = "⚖️ Combate inconcluso"
    else:
        result = "☠️ Destrucción mutua"

    text = (
        f"📜 <b>¡BATALLA RESUELTA!</b>\n\n"
        f"⚔️ <b>{report['attacker_name']}</b> "
        f"vs. <b>{report['defender_name']}</b>\n\n"
        f"{result}\n"
        f"🔁 Rondas: <b>{report['rounds']}</b>\n\n"
        f"💀 Bajas del atacante: "
        f"<b>{report['attacker_losses']:,}</b>\n"
        f"💀 Bajas del defensor: "
        f"<b>{report['defender_losses']:,}</b>\n"
        f"🏰 Infraestructura dañada: "
        f"<b>{float(report['infrastructure_damage'] or 0) * 100:.1f}%</b>\n\n"
        f"📖 El informe completo ya está disponible."
    )

    report_button = InlineKeyboardButton(
        text="📜 Abrir informe de batalla",
        callback_data=f"battle:report:{report_id}",
    )

    attacker_buttons = [[report_button]]

    if (
        report["vassalage_unlocked"]
        and report["outcome"] == "attacker_victory"
    ):
        attacker_buttons.append([
            InlineKeyboardButton(
                text="👑 Proponer vasallaje",
                callback_data=f"battle:vassal:propose:{report_id}",
            )
        ])

    defender_buttons = [[report_button]]

    notifications = [
        (
            int(report["attacker_owner_id"]),
            InlineKeyboardMarkup(inline_keyboard=attacker_buttons),
        ),
        (
            int(report["defender_owner_id"]),
            InlineKeyboardMarkup(inline_keyboard=defender_buttons),
        ),
    ]

    for owner_id, markup in notifications:
        try:
            await bot.send_message(
                owner_id,
                text,
                reply_markup=markup,
                parse_mode="HTML",
            )
        except Exception:
            logging.exception(
                "No se pudo notificar la batalla #%s al jugador %s.",
                report_id,
                owner_id,
            )


async def missions_worker(bot):
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
                            report_id, outcome = await process_arrival(
                                connection,
                                mission,
                            )

                    if mission:
                        await send_battle_notifications(
                            bot,
                            report_id,
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

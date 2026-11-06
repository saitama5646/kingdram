
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
from bot.services.world import calculate_travel_time, calculate_mission_speed


MAX_BATTLE_ROUNDS = 6
COMBAT_GROUP_THRESHOLD = 2000
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

    if stat == "attack":
        bonus = float(research_effects.get("military_attack", 0))
    elif stat == "defense":
        bonus = max(
            float(research_effects.get("military_hull", 0)),
            float(research_effects.get("military_defense", 0)),
        )
    else:
        bonus = 0.0

    multiplier = 1.0 + max(0.0, bonus)

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




def morale_damage_multiplier(morale):
    """
    La moral modifica el daño de forma moderada.

    Moral <= 20%: penalización máxima del 10%.
    Moral 20%-100%: penalización lineal.
    Moral >= 100%: conserva el bonus de moral positiva.
    """
    morale = float(morale)

    if morale <= 0.20:
        return 0.90

    if morale < 1.0:
        return 0.90 + ((morale - 0.20) / 0.80) * 0.10

    return morale


def calculate_damage(attackers, defenders, morale):
    if not attackers or not defenders:
        return 0.0

    multiplier = morale_damage_multiplier(morale)

    return max(
        0.0,
        army_power(attackers, "attack") * multiplier,
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

    total_quantity = army_quantity(troops)
    grouped = total_quantity >= COMBAT_GROUP_THRESHOLD

    units = []

    for troop in troops:
        unit_type = troop["unit_type"]
        quantity = max(0, int(troop["quantity"]))
        definition = UNITS.get(unit_type)

        if not definition or quantity <= 0:
            continue

        unit = {
            "unit_type": unit_type,
            "attack": max(
                0.0,
                float(definition.get("attack", 0))
                * attack_multiplier,
            ),
            "shield": max(
                0.0,
                float(definition.get("shield", 0))
                * shield_multiplier,
            ),
            "hull": max(
                1.0,
                float(definition.get("hull", 100))
                * defense_multiplier,
            ),
            "hull_damage": 0.0,
            "destroyed": False,
            "quantity": quantity if grouped else 1,
        }

        if grouped:
            units.append(unit)
        else:
            for _ in range(quantity):
                units.append(dict(unit))

    return units

def aggregate_combat_units(units):
    quantities = {}

    for unit in units:
        if unit.get("destroyed", False):
            continue

        unit_type = unit["unit_type"]
        quantity = max(1, int(unit.get("quantity", 1)))

        quantities[unit_type] = (
            quantities.get(unit_type, 0) + quantity
        )

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
    Resuelve una salva con selección ponderada de objetivos.

    El árbol Fenwick mantiene el peso de cada grupo de unidades
    vivas y permite seleccionar un objetivo en O(log n), evitando
    recorrer todos los objetivos en cada disparo.

    Se conservan:
    - Selección aleatoria ponderada por cantidad.
    - Daño individual a las unidades de grupos.
    - Escudos y daño acumulado al casco.
    - Destrucción y probabilidad de explosión.
    - Registro de unidades destruidas.
    - Compactación de supervivientes equivalentes.
    """

    if not shooters or not targets:
        return 0.0, targets

    for target in targets:
        target.setdefault("round_shield_damage", 0.0)
        target.setdefault("round_hull_damage", 0.0)
        target.setdefault("hull_damage", 0.0)
        target.setdefault("quantity", 1)
        target.setdefault("destroyed", False)

        target["_shield_remaining"] = max(
            0.0,
            float(target.get("shield", 0)),
        )

    # --------------------------------------------------------
    # Árbol Fenwick dinámico
    # --------------------------------------------------------

    fenwick = []

    def prefix_sum(end):
        """
        Suma de los pesos de las posiciones 1..end.
        """
        result = 0
        index = end

        while index > 0:
            result += fenwick[index - 1]
            index -= index & -index

        return result

    def append_weight(weight):
        """
        Añade una posición al árbol sin reconstruirlo.
        """
        index = len(fenwick) + 1
        value = int(weight)

        lowbit = index & -index

        if lowbit > 1:
            value += (
                prefix_sum(index - 1)
                - prefix_sum(index - lowbit)
            )

        fenwick.append(value)

    def add_weight(index_zero_based, delta):
        """
        Modifica el peso de una posición existente.
        """
        index = index_zero_based + 1

        while index <= len(fenwick):
            fenwick[index - 1] += delta
            index += index & -index

    def find_by_order(order):
        """
        Encuentra la posición que contiene el elemento ponderado
        número 'order', usando búsqueda binaria en el árbol.
        """
        index = 0
        bit = 1

        while bit << 1 <= len(fenwick):
            bit <<= 1

        while bit:
            next_index = index + bit

            if (
                next_index <= len(fenwick)
                and fenwick[next_index - 1] < order
            ):
                order -= fenwick[next_index - 1]
                index = next_index

            bit >>= 1

        return index

    for target in targets:
        quantity = max(
            0,
            int(target.get("quantity", 1)),
        )

        if target.get("destroyed", False):
            quantity = 0

        append_weight(quantity)

    total_damage = 0.0

    morale_multiplier = morale_damage_multiplier(
        max(0.0, float(morale))
    )

    # --------------------------------------------------------
    # Resolver los disparos
    # --------------------------------------------------------

    for shooter in shooters:
        if shooter.get("destroyed", False):
            continue

        shooter_quantity = max(
            1,
            int(shooter.get("quantity", 1)),
        )

        base_attack = max(
            0.0,
            float(shooter.get("attack", 0))
            * morale_multiplier,
        )

        if base_attack <= 0:
            continue

        for _ in range(shooter_quantity):
            living_quantity = prefix_sum(len(fenwick))

            if living_quantity <= 0:
                break

            selection = random.randrange(living_quantity)

            target_index = find_by_order(selection + 1)

            if target_index >= len(targets):
                raise RuntimeError(
                    "El árbol de selección devolvió "
                    "un objetivo fuera de rango."
                )

            target = targets[target_index]

            if target.get("destroyed", False):
                raise RuntimeError(
                    "El árbol Fenwick seleccionó "
                    "una unidad destruida."
                )

            # ------------------------------------------------
            # Separar una unidad del grupo
            # ------------------------------------------------

            if int(target.get("quantity", 1)) > 1:
                target["quantity"] -= 1

                add_weight(
                    target_index,
                    -1,
                )

                individual = dict(target)

                individual["quantity"] = 1
                individual["round_shield_damage"] = 0.0
                individual["round_hull_damage"] = 0.0

                targets.append(individual)

                append_weight(1)

                target_index = len(targets) - 1
                target = individual

            # ------------------------------------------------
            # Aplicar daño
            # ------------------------------------------------

            attack = base_attack * random.uniform(
                1.0 - DAMAGE_VARIATION,
                1.0 + DAMAGE_VARIATION,
            )

            shield_remaining = max(
                0.0,
                float(target.get("_shield_remaining", 0)),
            )

            absorbed = min(
                shield_remaining,
                attack,
            )

            target["_shield_remaining"] = (
                shield_remaining - absorbed
            )

            target["round_shield_damage"] += absorbed

            penetrating_damage = max(
                0.0,
                attack - absorbed,
            )

            maximum_hull = max(
                1.0,
                float(target.get("hull", 100)),
            )

            current_hull_damage = max(
                0.0,
                float(target.get("hull_damage", 0)),
            )

            remaining_hull = max(
                0.0,
                maximum_hull - current_hull_damage,
            )

            actual_hull_damage = min(
                remaining_hull,
                penetrating_damage,
            )

            target["hull_damage"] = (
                current_hull_damage
                + actual_hull_damage
            )

            target["round_hull_damage"] += (
                actual_hull_damage
            )

            total_damage += (
                absorbed
                + actual_hull_damage
            )

            # ------------------------------------------------
            # Destrucción
            # ------------------------------------------------

            if target["hull_damage"] >= maximum_hull:
                target["destroyed"] = True

                add_weight(
                    target_index,
                    -1,
                )

                continue

            remaining_hull_after_hit = (
                maximum_hull
                - target["hull_damage"]
            )

            if (
                remaining_hull_after_hit
                < maximum_hull * 0.30
            ):
                destruction_chance = max(
                    0.0,
                    min(
                        1.0,
                        1.0
                        - remaining_hull_after_hit
                        / maximum_hull,
                    ),
                )

                if random.random() < destruction_chance:
                    target["destroyed"] = True

                    add_weight(
                        target_index,
                        -1,
                    )

    # --------------------------------------------------------
    # Compactación de resultados
    # --------------------------------------------------------

    destroyed_units = []
    compacted = {}

    for target in targets:
        quantity = max(
            0,
            int(target.get("quantity", 1)),
        )

        if quantity <= 0:
            continue

        if target.get("destroyed", False):
            destroyed_units.append(dict(target))
            continue

        key = (
            target["unit_type"],
            float(target.get("attack", 0)),
            float(target.get("shield", 0)),
            float(target.get("hull", 100)),
            float(target.get("hull_damage", 0)),
            float(target.get("_shield_remaining", 0)),
            float(target.get("round_shield_damage", 0)),
            float(target.get("round_hull_damage", 0)),
        )

        if key not in compacted:
            compacted[key] = dict(target)
        else:
            compacted[key]["quantity"] += quantity

    # Mantener el registro de unidades destruidas para los
    # informes, seguido de los supervivientes compactados.
    targets[:] = (
        destroyed_units
        + list(compacted.values())
    )

    return total_damage, targets


def resolve_battle_round_detailed(
    attackers,
    defenders,
    attacker_morale,
    defender_morale,
):
    for unit in attackers + defenders:
        unit["round_shield_damage"] = 0.0
        unit["round_hull_damage"] = 0.0

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

    attacker_before = sum(
        int(unit.get("quantity", 1))
        for unit in attackers
        if not unit.get("destroyed", False)
    )

    defender_before = sum(
        int(unit.get("quantity", 1))
        for unit in defenders
        if not unit.get("destroyed", False)
    )

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

    details = {
        "attacker_shield_damage": sum(
            float(unit.get("round_shield_damage", 0))
            * int(unit.get("quantity", 1))
            for unit in attackers
        ),
        "attacker_hull_damage": sum(
            float(unit.get("round_hull_damage", 0))
            * int(unit.get("quantity", 1))
            for unit in attackers
        ),
        "defender_shield_damage": sum(
            float(unit.get("round_shield_damage", 0))
            * int(unit.get("quantity", 1))
            for unit in defenders
        ),
        "defender_hull_damage": sum(
            float(unit.get("round_hull_damage", 0))
            * int(unit.get("quantity", 1))
            for unit in defenders
        ),
    }

    attackers_after = [
        unit for unit in attackers
        if not unit.get("destroyed", False)
    ]

    defenders_after = [
        unit for unit in defenders
        if not unit.get("destroyed", False)
    ]

    attacker_remaining = sum(
        int(unit.get("quantity", 1))
        for unit in attackers_after
    )

    defender_remaining = sum(
        int(unit.get("quantity", 1))
        for unit in defenders_after
    )

    return (
        attackers_after,
        defenders_after,
        attacker_damage,
        defender_damage,
        details,
    )

def resolve_battle_round(
    attackers,
    defenders,
    attacker_morale,
    defender_morale,
):
    result = resolve_battle_round_detailed(
        attackers,
        defenders,
        attacker_morale,
        defender_morale,
    )

    return result[:4]

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


async def damage_infrastructure(connection, realm_id, target_damage):
    buildings = await connection.fetch(
        """
        SELECT id, building_type, level, damaged_levels
        FROM buildings
        WHERE realm_id = $1
        ORDER BY level DESC, id
        FOR UPDATE
        """,
        realm_id,
    )

    # Solo cuentan los niveles que están operativos.
    effective_buildings = [
        {
            "building_type": building["building_type"],
            "level": max(
                0,
                int(building["level"])
                - int(building["damaged_levels"]),
            ),
        }
        for building in buildings
    ]

    before = infrastructure_value(effective_buildings)
    infrastructure_log = []

    if before <= 0 or target_damage <= 0:
        return before, before, 0.0, infrastructure_log

    target_damage = max(
        0.0,
        min(float(target_damage), MAX_INFRASTRUCTURE_DAMAGE),
    )

    target_budget = int(before * target_damage)
    hard_limit = int(before * MAX_INFRASTRUCTURE_DAMAGE)

    planned_levels = {
        int(building["id"]): max(
            0,
            int(building["level"])
            - int(building["damaged_levels"]),
        )
        for building in buildings
    }

    building_values = {}

    for building in buildings:
        definition = BUILDINGS.get(building["building_type"])

        if definition:
            building_values[int(building["id"])] = sum(
                int(amount)
                for amount in definition["base_cost"].values()
            )

    damage_planned = 0

    while target_budget > 0:
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

            if (
                level_value <= target_budget
                and damage_planned + level_value <= hard_limit
            ):
                candidates.append((level_value, building_id))

        if candidates:
            level_value, building_id = max(
                candidates,
                key=lambda item: (item[0], -item[1]),
            )

            planned_levels[building_id] -= 1
            target_budget -= level_value
            damage_planned += level_value
            continue

        if damage_planned == 0:
            fallback = []

            for building in buildings:
                building_id = int(building["id"])
                level = planned_levels[building_id]
                base_value = building_values.get(building_id, 0)

                if level <= 0 or base_value <= 0:
                    continue

                level_value = ceil(
                    base_value * (BUILDING_COST_GROWTH ** (level - 1))
                )

                if level_value <= hard_limit:
                    fallback.append((level_value, building_id))

            if fallback:
                level_value, building_id = min(fallback)
                planned_levels[building_id] -= 1
                damage_planned += level_value

        break

    for building in buildings:
        building_id = int(building["id"])
        original_level = int(building["level"])
        old_damaged = int(building["damaged_levels"])

        old_effective = max(0, original_level - old_damaged)
        new_effective = planned_levels[building_id]

        damaged_now = old_effective - new_effective

        if damaged_now <= 0:
            continue

        await connection.execute(
            """
            UPDATE buildings
            SET damaged_levels = damaged_levels + $1,
                rebuild_at = NOW() + INTERVAL '12 hours'
            WHERE id = $2
            """,
            damaged_now,
            building_id,
        )

        infrastructure_log.append({
            "building_type": building["building_type"],
            "old_level": old_effective,
            "new_level": new_effective,
            "destroyed_levels": damaged_now,
        })

    remaining_buildings = await connection.fetch(
        """
        SELECT
            building_type,
            GREATEST(level - damaged_levels, 0) AS level
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

    if actual_damage > MAX_INFRASTRUCTURE_DAMAGE + 1e-9:
        raise RuntimeError(
            "El daño a infraestructura superó el límite del 65 %."
        )

    return before, after, actual_damage, infrastructure_log

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

        attacker_before = sum(
            int(unit.get("quantity", 1))
            for unit in attacker_combat_units
        )
        defender_before = sum(
            int(unit.get("quantity", 1))
            for unit in defender_combat_units
        )

        (
            attacker_combat_units,
            defender_combat_units,
            attacker_damage,
            defender_damage,
            damage_details,
        ) = resolve_battle_round_detailed(
            attacker_combat_units,
            defender_combat_units,
            attacker_morale,
            defender_morale,
        )

        attackers = aggregate_combat_units(attacker_combat_units)
        defenders = aggregate_combat_units(defender_combat_units)

        attacker_after = sum(
            int(unit.get("quantity", 1))
            for unit in attacker_combat_units
        )
        defender_after = sum(
            int(unit.get("quantity", 1))
            for unit in defender_combat_units
        )

        attacker_losses = attacker_before - attacker_after
        defender_losses = defender_before - defender_after

        attacker_morale_before = attacker_morale
        defender_morale_before = defender_morale

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

            # Daño real, ya modificado por moral.
            "attacker_damage": round(attacker_damage, 2),
            "defender_damage": round(defender_damage, 2),

            "damage_breakdown": {
                "attacker_shield_damage_received": round(
                    damage_details["attacker_shield_damage"], 2
                ),
                "attacker_hull_damage_received": round(
                    damage_details["attacker_hull_damage"], 2
                ),
                "defender_shield_damage_received": round(
                    damage_details["defender_shield_damage"], 2
                ),
                "defender_hull_damage_received": round(
                    damage_details["defender_hull_damage"], 2
                ),
            },

            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,

            "attacker_remaining": sum(int(unit.get("quantity", 1)) for unit in attacker_combat_units),
            "defender_remaining": sum(int(unit.get("quantity", 1)) for unit in defender_combat_units),

            "attacker_morale_start": round(attacker_morale_before, 3),
            "attacker_morale_change": round(
                attacker_morale - attacker_morale_before, 3
            ),
            "attacker_morale": round(attacker_morale, 3),

            "defender_morale_start": round(defender_morale_before, 3),
            "defender_morale_change": round(
                defender_morale - defender_morale_before, 3
            ),
            "defender_morale": round(defender_morale, 3),
        })

        logging.info(
            "MISIÓN %s | RONDA %s | Bajas A=%s D=%s | Restantes A=%s D=%s",
            mission_id,
            round_number,
            attacker_losses,
            defender_losses,
            sum(int(unit.get("quantity", 1)) for unit in attacker_combat_units),
            sum(int(unit.get("quantity", 1)) for unit in defender_combat_units),
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

    # El retorno usa la velocidad de las unidades supervivientes.
    # Se mantiene la misma fórmula de viaje utilizada en la ida.
    return_troops = [
        {
            "unit_type": troop["unit_type"],
            "quantity": int(troop["quantity"]),
        }
        for troop in attackers
        if int(troop["quantity"]) > 0
    ]

    return_speed = calculate_mission_speed(return_troops)

    if return_speed <= 0:
        return_seconds = 60
    else:
        return_seconds = calculate_travel_time(
            float(mission["distance"]),
            return_speed,
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

"""Funciones heredadas de combate e infraestructura.
La resolución de batallas se realiza exclusivamente
desde bot.workers.missions.
"""

from math import ceil
from bot.database.connection import get_pool
from bot.services.military import UNITS
from bot.services.research import get_research_effects
from bot.services.construction import BUILDINGS


RESOURCES = ("wood", "stone", "gold", "food")

BUILDING_COST_GROWTH = 1.65

MIN_DAMAGE_FOR_VASSALAGE = 0.50


def calculate_army_power(troops, research_effects, mode):
    total = 0

    effect_name = (
        "military_attack"
        if mode == "attack"
        else "military_defense"
    )

    bonus = float(research_effects.get(effect_name, 0))
    multiplier = 1 + bonus

    for troop in troops:
        unit = UNITS.get(troop["unit_type"])

        if not unit:
            continue

        statistic = unit[
            "attack" if mode == "attack" else "defense"
        ]

        total += int(
            troop["quantity"] * statistic * multiplier
        )

    return total


def get_infrastructure_value(buildings):
    total = 0

    for building in buildings:
        building_type = building["building_type"]
        level = int(building["level"])

        definition = BUILDINGS.get(building_type)

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


def calculate_damage_target(attacker_power, defender_power):
    if defender_power <= 0:
        return 0.65

    ratio = attacker_power / defender_power

    damage = 0.15 + max(0, ratio - 1) * 0.12

    return min(0.65, max(0.15, damage))


def calculate_losses(troops, loss_rate):
    results = []
    total_losses = 0

    for troop in troops:
        quantity = int(troop["quantity"])

        if quantity <= 0:
            continue

        losses = min(
            quantity,
            ceil(quantity * loss_rate)
        )

        remaining = quantity - losses

        results.append({
            "unit_type": troop["unit_type"],
            "initial": quantity,
            "lost": losses,
            "remaining": remaining,
        })

        total_losses += losses

    return results, total_losses


async def apply_losses(connection, realm_id, results):
    for result in results:
        await connection.execute(
            """
            UPDATE army
            SET quantity = $1
            WHERE realm_id = $2
              AND unit_type = $3
            """,
            result["remaining"],
            realm_id,
            result["unit_type"],
        )

        if result["remaining"] == 0:
            await connection.execute(
                """
                DELETE FROM army
                WHERE realm_id = $1
                  AND unit_type = $2
                """,
                realm_id,
                result["unit_type"],
            )


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

    before = get_infrastructure_value(buildings)

    if before <= 0 or target_damage <= 0:
        return before, before, 0.0

    target_value = int(before * target_damage)
    destroyed_value = 0

    for building in buildings:
        if destroyed_value >= target_value:
            break

        building_type = building["building_type"]
        level = int(building["level"])

        definition = BUILDINGS.get(building_type)

        if not definition:
            continue

        base_value = sum(
            int(amount)
            for amount in definition["base_cost"].values()
        )

        while level > 0 and destroyed_value < target_value:
            level_value = ceil(
                base_value
                * (BUILDING_COST_GROWTH ** (level - 1))
            )

            destroyed_value += level_value
            level -= 1

        if level <= 0:
            await connection.execute(
                """
                DELETE FROM buildings
                WHERE id = $1
                """,
                building["id"],
            )
        else:
            await connection.execute(
                """
                UPDATE buildings
                SET level = $1
                WHERE id = $2
                """,
                level,
                building["id"],
            )

    remaining_buildings = await connection.fetch(
        """
        SELECT building_type, level
        FROM buildings
        WHERE realm_id = $1
        """,
        realm_id,
    )

    after = get_infrastructure_value(remaining_buildings)

    actual_damage = (
        max(0, before - after) / before
        if before > 0
        else 0
    )

    return before, after, min(1.0, actual_damage)


async def get_research_effects_for_realm(connection, realm_id):
    rows = await connection.fetch(
        """
        SELECT research_type, level
        FROM realm_research
        WHERE realm_id = $1
        """,
        realm_id,
    )

    levels = {
        row["research_type"]: row["level"]
        for row in rows
    }

    return get_research_effects(levels)


async def get_battle_targets(user_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        attacker = await connection.fetchrow(
            """
            SELECT id
            FROM realms
            WHERE owner_id = $1
            """,
            user_id,
        )

        if not attacker:
            return None

        targets = await connection.fetch(
            """
            SELECT
                r.id,
                r.name,
                r.power,
                r.level,
                r.owner_id
            FROM realms r
            WHERE r.id <> $1
              AND NOT EXISTS (
                  SELECT 1
                  FROM vassalage_relations vr
                  WHERE vr.lord_realm_id = $1
                    AND vr.vassal_realm_id = r.id
                    AND vr.status = 'active'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM alliance_members attacker_member
                  JOIN alliance_members defender_member
                    ON defender_member.player_id = r.owner_id
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
                  WHERE attacker_member.player_id = $2
              )
            ORDER BY r.power DESC, r.id
            LIMIT 20
            """,
            attacker["id"],
            user_id,
        )

        return {
            "attacker_realm_id": attacker["id"],
            "targets": targets,
        }


async def resolve_battle(user_id, defender_realm_id):
    raise RuntimeError(
        "El motor antiguo está deshabilitado. "
        "Las batallas deben iniciarse mediante misiones militares."
    )

    # LEGACY_BATTLE_ENGINE_DISABLED
    pool = await get_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            attacker = await connection.fetchrow(
                """
                SELECT id, owner_id, name
                FROM realms
                WHERE owner_id = $1
                """,
                user_id,
            )

            if not attacker:
                return False, "Primero debes fundar un reino."

            if attacker["id"] == defender_realm_id:
                return False, "No puedes atacar tu propio reino."

            realm_ids = sorted([
                attacker["id"],
                defender_realm_id,
            ])

            locked_realms = await connection.fetch(
                """
                SELECT id, owner_id, name
                FROM realms
                WHERE id = ANY($1::BIGINT[])
                ORDER BY id
                FOR UPDATE
                """,
                realm_ids,
            )

            if len(locked_realms) != 2:
                return False, "El reino seleccionado ya no existe."

            defender = next(
                (
                    realm for realm in locked_realms
                    if realm["id"] == defender_realm_id
                ),
                None,
            )

            if not defender:
                return False, "No se encontró el reino objetivo."

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
                    "No puedes atacar a un reino "
                    "que sea tu vasallo."
                )

            attacker_troops = await connection.fetch(
                """
                SELECT unit_type, quantity
                FROM army
                WHERE realm_id = $1
                  AND quantity > 0
                """,
                attacker["id"],
            )

            defender_troops = await connection.fetch(
                """
                SELECT unit_type, quantity
                FROM army
                WHERE realm_id = $1
                  AND quantity > 0
                """,
                defender_realm_id,
            )

            if not attacker_troops:
                return False, (
                    "No tienes tropas disponibles "
                    "para iniciar una batalla."
                )

            attacker_effects = (
                await get_research_effects_for_realm(
                    connection,
                    attacker["id"],
                )
            )

            defender_effects = (
                await get_research_effects_for_realm(
                    connection,
                    defender_realm_id,
                )
            )

            attacker_power = calculate_army_power(
                attacker_troops,
                attacker_effects,
                "attack",
            )

            defender_power = calculate_army_power(
                defender_troops,
                defender_effects,
                "defense",
            )

            if attacker_power <= 0:
                return False, "Tu ejército no tiene fuerza suficiente."

            attacker_wins = attacker_power > defender_power

            if attacker_wins:
                winner_realm_id = attacker["id"]
                attacker_loss_rate = 0.18
                defender_loss_rate = 0.50

                target_damage = calculate_damage_target(
                    attacker_power,
                    defender_power,
                )
            else:
                winner_realm_id = defender_realm_id
                attacker_loss_rate = 0.45
                defender_loss_rate = 0.15
                target_damage = 0

            attacker_results, attacker_losses = calculate_losses(
                attacker_troops,
                attacker_loss_rate,
            )

            defender_results, defender_losses = calculate_losses(
                defender_troops,
                defender_loss_rate,
            )

            await apply_losses(
                connection,
                attacker["id"],
                attacker_results,
            )

            await apply_losses(
                connection,
                defender_realm_id,
                defender_results,
            )

            infrastructure_before = 0
            infrastructure_after = 0
            infrastructure_damage = 0.0

            if attacker_wins:
                (
                    infrastructure_before,
                    infrastructure_after,
                    infrastructure_damage,
                ) = await damage_infrastructure(
                    connection,
                    defender_realm_id,
                    target_damage,
                )

            vassalage_unlocked = (
                attacker_wins
                and infrastructure_damage >= MIN_DAMAGE_FOR_VASSALAGE
            )

            report = await connection.fetchrow(
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
                    vassalage_unlocked
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9,
                    $10, $11, $12, $13
                )
                RETURNING id, created_at
                """,
                attacker["id"],
                defender_realm_id,
                attacker["owner_id"],
                defender["owner_id"],
                winner_realm_id,
                attacker_power,
                defender_power,
                attacker_losses,
                defender_losses,
                infrastructure_before,
                infrastructure_after,
                infrastructure_damage,
                vassalage_unlocked,
            )

            for result in attacker_results:
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
                    report["id"],
                    attacker["id"],
                    result["unit_type"],
                    result["initial"],
                    result["lost"],
                    result["remaining"],
                )

            for result in defender_results:
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
                    report["id"],
                    defender_realm_id,
                    result["unit_type"],
                    result["initial"],
                    result["lost"],
                    result["remaining"],
                )

            return True, {
                "battle_id": report["id"],
                "attacker_name": attacker["name"],
                "defender_name": defender["name"],
                "attacker_power": attacker_power,
                "defender_power": defender_power,
                "attacker_wins": attacker_wins,
                "attacker_losses": attacker_losses,
                "defender_losses": defender_losses,
                "infrastructure_before": infrastructure_before,
                "infrastructure_after": infrastructure_after,
                "infrastructure_damage": infrastructure_damage,
                "vassalage_unlocked": vassalage_unlocked,
            }

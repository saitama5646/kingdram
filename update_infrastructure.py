from pathlib import Path
import re

path = Path("bot/workers/missions.py")
content = path.read_text(encoding="utf-8")

pattern = re.compile(
    r"async def damage_infrastructure\(.*?"
    r"(?=\n\nasync def save_attacker_survivors)",
    re.DOTALL,
)

replacement = '''async def damage_infrastructure(
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
'''

updated, count = pattern.subn(replacement, content, count=1)

if count != 1:
    raise SystemExit(
        "ERROR: No se encontró damage_infrastructure. "
        "No se modificó el archivo."
    )

path.write_text(updated, encoding="utf-8")

print("Sistema de daño a infraestructura actualizado.")

BASE_CAPACITY = {
    "wood": 15000,
    "stone": 15000,
    "gold": 12000,
    "food": 12000,
}

WAREHOUSE_BONUS = 10000
GRANARY_BONUS = 15000


def get_storage_capacity(buildings):
    levels = {
        row["building_type"]: int(row["level"])
        for row in buildings
    }

    warehouse_level = levels.get("warehouse", 0)
    granary_level = levels.get("granary", 0)

    return {
        "wood": (
            BASE_CAPACITY["wood"]
            + warehouse_level * WAREHOUSE_BONUS
        ),
        "stone": (
            BASE_CAPACITY["stone"]
            + warehouse_level * WAREHOUSE_BONUS
        ),
        "gold": (
            BASE_CAPACITY["gold"]
            + warehouse_level * WAREHOUSE_BONUS
        ),
        "food": (
            BASE_CAPACITY["food"]
            + granary_level * GRANARY_BONUS
        ),
    }


async def get_realm_storage_capacity(connection, realm_id):
    buildings = await connection.fetch(
        """
        SELECT
            building_type,
            GREATEST(level - damaged_levels, 0) AS level
        FROM buildings
        WHERE realm_id = $1
        """,
        realm_id,
    )

    return get_storage_capacity(buildings)

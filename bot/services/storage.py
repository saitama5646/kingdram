BASE_CAPACITY = {
    "wood": 20000,
    "stone": 15000,
    "gold": 8000,
    "food": 12000,
}

# Multiplicador de capacidad alineado con
# el crecimiento de los costes de construcción.
STORAGE_CAPACITY_GROWTH = 1.55


def get_storage_capacity(buildings):
    levels = {
        row["building_type"]: int(row["level"])
        for row in buildings
    }

    warehouse_level = levels.get("warehouse", 0)
    treasury_level = levels.get("treasury", 0)
    granary_level = levels.get("granary", 0)

    return {
        "wood": int(
            BASE_CAPACITY["wood"]
            * STORAGE_CAPACITY_GROWTH ** warehouse_level
        ),
        "stone": int(
            BASE_CAPACITY["stone"]
            * STORAGE_CAPACITY_GROWTH ** warehouse_level
        ),
        "gold": int(
            BASE_CAPACITY["gold"]
            * STORAGE_CAPACITY_GROWTH ** treasury_level
        ),
        "food": int(
            BASE_CAPACITY["food"]
            * STORAGE_CAPACITY_GROWTH ** granary_level
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

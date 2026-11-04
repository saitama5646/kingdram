
from bot.database.connection import get_pool
from bot.services.construction import BUILDINGS, get_upgrade_cost
from bot.services.military import UNITS


POINTS_PER_RESOURCE = 1000


def calculate_building_points(buildings):
    total_investment = 0

    for building in buildings:
        building_type = building["building_type"]

        if building_type not in BUILDINGS:
            continue

        level = int(building["level"])

        for target_level in range(1, level + 1):
            costs = get_upgrade_cost(
                building_type,
                target_level
            )

            total_investment += sum(costs.values())

    return total_investment // POINTS_PER_RESOURCE


def calculate_military_points(troops):
    total_investment = 0

    for troop in troops:
        unit_type = troop["unit_type"]

        if unit_type not in UNITS:
            continue

        unit = UNITS[unit_type]
        quantity = int(troop["quantity"])

        unit_cost = (
            unit["wood"]
            + unit["stone"]
            + unit["gold"]
            + unit["food"]
        )

        total_investment += unit_cost * quantity

    return total_investment // POINTS_PER_RESOURCE


async def calculate_realm_score(realm_id):
    pool = await get_pool()

    async with pool.acquire() as connection:
        buildings = await connection.fetch(
            """
            SELECT building_type, level
            FROM buildings
            WHERE realm_id = $1
            """,
            realm_id
        )

        troops = await connection.fetch(
            """
            SELECT unit_type, quantity
            FROM army
            WHERE realm_id = $1
            """,
            realm_id
        )

        building_points = calculate_building_points(buildings)
        military_points = calculate_military_points(troops)

        research_points = await connection.fetchval(
            """
            SELECT COALESCE(SUM(level), 0)
            FROM realm_research
            WHERE realm_id = $1
            """,
            realm_id
        )

        research_points = int(research_points or 0)

        total_points = (
            building_points
            + military_points
            + research_points
        )

        await connection.execute(
            """
            INSERT INTO realm_statistics (
                realm_id,
                building_points,
                military_points,
                research_points,
                total_points,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (realm_id)
            DO UPDATE SET
                building_points = EXCLUDED.building_points,
                military_points = EXCLUDED.military_points,
                research_points = EXCLUDED.research_points,
                total_points = EXCLUDED.total_points,
                updated_at = NOW()
            """,
            realm_id,
            building_points,
            military_points,
            research_points,
            total_points
        )

        return {
            "buildings": building_points,
            "military": military_points,
            "research": research_points,
            "total": total_points
        }


async def refresh_all_scores():
    pool = await get_pool()

    async with pool.acquire() as connection:
        realm_ids = await connection.fetch(
            "SELECT id FROM realms"
        )

    for realm in realm_ids:
        await calculate_realm_score(realm["id"])


async def get_ranking(limit=10):
    pool = await get_pool()

    async with pool.acquire() as connection:
        realms = await connection.fetch(
            """
            SELECT
                r.id,
                r.name,
                r.owner_id,
                COALESCE(s.building_points, 0) AS building_points,
                COALESCE(s.military_points, 0) AS military_points,
                COALESCE(s.research_points, 0) AS research_points,
                COALESCE(s.total_points, 0) AS total_points
            FROM realms r
            LEFT JOIN realm_statistics s
                ON s.realm_id = r.id
            ORDER BY
                total_points DESC,
                r.created_at ASC
            LIMIT $1
            """,
            limit
        )

    return realms

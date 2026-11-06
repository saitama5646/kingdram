import unittest

from bot.services.construction import (
    BUILDING_COST_GROWTH,
    get_upgrade_cost,
)
from bot.services.research import (
    COST_GROWTH,
    get_research_cost,
)
from bot.services.economy import (
    get_realm_production,
)
from bot.workers.production import calculate_production
from bot.handlers.bazaar import (
    RESOURCES,
    calculate_exchange_amount,
)


class EconomyBalanceTests(unittest.TestCase):

    def test_building_cost_growth(self):
        self.assertEqual(BUILDING_COST_GROWTH, 1.55)

        level_one = get_upgrade_cost("sawmill", 1)
        level_two = get_upgrade_cost("sawmill", 2)

        self.assertEqual(level_one["wood"], 150)
        self.assertEqual(level_two["wood"], int(150 * 1.55))

    def test_research_cost_growth(self):
        self.assertEqual(COST_GROWTH, 1.60)

        level_one = get_research_cost("agriculture", 1)
        level_two = get_research_cost("agriculture", 2)

        self.assertEqual(level_one["gold"], 84)
        self.assertEqual(
            level_two["gold"],
            135,
        )

    def test_food_has_higher_bazaar_value(self):
        self.assertEqual(RESOURCES["food"]["value"], 7)

        received = calculate_exchange_amount(
            7,
            "food",
            "gold",
        )

        self.assertEqual(received, 1)

    def test_production_includes_research_bonus(self):
        buildings = [
            {"building_type": "sawmill", "level": 2},
            {"building_type": "quarry", "level": 1},
            {"building_type": "farm", "level": 1},
        ]

        effects = {
            "wood_production": 0.10,
            "food_production": 0.05,
        }

        production = get_realm_production(
            buildings,
            effects,
        )

        self.assertEqual(production["wood"], 39)
        self.assertEqual(production["stone"], 10)
        self.assertEqual(production["food"], 15)

    def test_worker_and_economy_production_match(self):
        buildings = [
            {"building_type": "sawmill", "level": 3},
            {"building_type": "quarry", "level": 2},
            {"building_type": "gold_mine", "level": 1},
            {"building_type": "farm", "level": 2},
        ]

        effects = {
            "wood_production": 0.10,
            "stone_production": 0.05,
            "gold_production": 0.02,
            "food_production": 0.08,
        }

        self.assertEqual(
            get_realm_production(buildings, effects),
            calculate_production(buildings, effects),
        )


if __name__ == "__main__":
    unittest.main()

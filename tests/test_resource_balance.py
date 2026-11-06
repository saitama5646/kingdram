import unittest

from bot.services.construction import (
    BUILDINGS,
    get_upgrade_cost,
)
from bot.services.economy import get_realm_production
from bot.services.research import get_research_cost
from bot.services.storage import BASE_CAPACITY


class TestResourceBalance(unittest.TestCase):

    def test_resource_production_order(self):
        buildings = [
            {"building_type": "sawmill", "level": 1},
            {"building_type": "quarry", "level": 1},
            {"building_type": "gold_mine", "level": 1},
            {"building_type": "market", "level": 1},
            {"building_type": "farm", "level": 1},
        ]

        production = get_realm_production(buildings)

        self.assertEqual(production["wood"], 18)
        self.assertEqual(production["stone"], 10)
        self.assertEqual(production["gold"], 3)
        self.assertEqual(production["food"], 15)

        self.assertGreater(production["wood"], production["stone"])
        self.assertGreater(production["stone"], production["gold"])

    def test_building_production_values(self):
        self.assertEqual(BUILDINGS["sawmill"]["production"], 18)
        self.assertEqual(BUILDINGS["quarry"]["production"], 10)
        self.assertEqual(BUILDINGS["gold_mine"]["production"], 2)
        self.assertEqual(BUILDINGS["market"]["production"], 1)

    def test_building_gold_costs_are_reduced(self):
        self.assertEqual(get_upgrade_cost("sawmill", 1)["gold"], 30)
        self.assertEqual(get_upgrade_cost("quarry", 1)["gold"], 35)
        self.assertEqual(get_upgrade_cost("gold_mine", 1)["gold"], 50)

    def test_research_gold_cost_is_reduced(self):
        cost = get_research_cost("agriculture", 1)
        self.assertEqual(cost["gold"], 84)

    def test_gold_storage_is_the_smallest(self):
        self.assertGreater(BASE_CAPACITY["wood"], BASE_CAPACITY["stone"])
        self.assertGreater(BASE_CAPACITY["stone"], BASE_CAPACITY["gold"])


if __name__ == "__main__":
    unittest.main()

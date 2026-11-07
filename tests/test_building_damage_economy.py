import unittest

from bot.services.economy import get_realm_production
from bot.services.storage import get_storage_capacity


class BuildingDamageEconomyTests(unittest.TestCase):

    def test_production_uses_effective_building_level(self):
        buildings = [
            {
                "building_type": "sawmill",
                "level": 3,
            },
        ]

        production = get_realm_production(buildings)

        self.assertEqual(production["wood"], 54)

    def test_storage_uses_effective_building_levels(self):
        buildings = [
            {
                "building_type": "warehouse",
                "level": 1,
            },
            {
                "building_type": "treasury",
                "level": 2,
            },
            {
                "building_type": "granary",
                "level": 1,
            },
        ]

        capacity = get_storage_capacity(buildings)

        self.assertEqual(capacity["wood"], 31000)
        self.assertEqual(capacity["stone"], 23250)
        self.assertEqual(capacity["gold"], 19220)
        self.assertEqual(capacity["food"], 18600)

    def test_fully_damaged_building_has_no_production(self):
        buildings = [
            {
                "building_type": "sawmill",
                "level": 0,
            },
        ]

        production = get_realm_production(buildings)

        self.assertEqual(production["wood"], 0)

    def test_fully_damaged_storage_building_gives_base_capacity(self):
        buildings = [
            {
                "building_type": "warehouse",
                "level": 0,
            },
            {
                "building_type": "treasury",
                "level": 0,
            },
            {
                "building_type": "granary",
                "level": 0,
            },
        ]

        capacity = get_storage_capacity(buildings)

        self.assertEqual(capacity["wood"], 20000)
        self.assertEqual(capacity["stone"], 15000)
        self.assertEqual(capacity["gold"], 8000)
        self.assertEqual(capacity["food"], 12000)


if __name__ == "__main__":
    unittest.main()

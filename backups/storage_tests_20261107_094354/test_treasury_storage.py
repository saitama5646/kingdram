import unittest

from bot.services.storage import get_storage_capacity


class TreasuryStorageTests(unittest.TestCase):

    def test_warehouse_only_increases_wood_and_stone(self):
        capacity = get_storage_capacity([
            {"building_type": "warehouse", "level": 2},
        ])

        self.assertEqual(capacity["wood"], 40000)
        self.assertEqual(capacity["stone"], 35000)
        self.assertEqual(capacity["gold"], 8000)

    def test_treasury_only_increases_gold(self):
        capacity = get_storage_capacity([
            {"building_type": "treasury", "level": 2},
        ])

        self.assertEqual(capacity["wood"], 20000)
        self.assertEqual(capacity["stone"], 15000)
        self.assertEqual(capacity["gold"], 28000)

    def test_all_storage_buildings_are_independent(self):
        capacity = get_storage_capacity([
            {"building_type": "warehouse", "level": 1},
            {"building_type": "treasury", "level": 3},
            {"building_type": "granary", "level": 2},
        ])

        self.assertEqual(capacity["wood"], 30000)
        self.assertEqual(capacity["stone"], 25000)
        self.assertEqual(capacity["gold"], 38000)
        self.assertEqual(capacity["food"], 42000)


if __name__ == "__main__":
    unittest.main()

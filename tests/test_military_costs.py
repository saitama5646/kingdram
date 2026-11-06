import unittest

from bot.services.military import UNITS


class MilitaryCostsTests(unittest.TestCase):

    EXPECTED = {
        "spearman": (12, 3, 16, 20, 20),
        "archer": (17, 2, 22, 25, 30),
        "cavalry": (10, 6, 58, 65, 60),
        "royal_guard": (30, 12, 71, 80, 90),
    }

    def test_updated_unit_costs(self):
        for unit_type, expected in self.EXPECTED.items():
            with self.subTest(unit=unit_type):
                unit = UNITS[unit_type]
                actual = (
                    unit["wood"],
                    unit["stone"],
                    unit["gold"],
                    unit["food"],
                    unit["seconds"],
                )
                self.assertEqual(actual, expected)

    def test_wood_and_stone_decreased(self):
        original = {
            "spearman": (35, 10),
            "archer": (50, 5),
            "cavalry": (30, 20),
            "royal_guard": (80, 60),
        }

        for unit_type, (wood, stone) in original.items():
            with self.subTest(unit=unit_type):
                self.assertLess(UNITS[unit_type]["wood"], wood)
                self.assertLess(UNITS[unit_type]["stone"], stone)

    def test_gold_increased(self):
        original = {
            "spearman": 8,
            "archer": 13,
            "cavalry": 45,
            "royal_guard": 60,
        }

        for unit_type, gold in original.items():
            with self.subTest(unit=unit_type):
                self.assertGreater(UNITS[unit_type]["gold"], gold)


if __name__ == "__main__":
    unittest.main()

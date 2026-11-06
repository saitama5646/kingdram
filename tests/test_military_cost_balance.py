import unittest

from bot.services.military import UNITS
from bot.services.bazaar import RESOURCES


def resource_value(unit):
    return sum(
        unit[resource] * RESOURCES[resource]["value"]
        for resource in ("wood", "stone", "gold", "food")
    )


class MilitaryCostBalanceTests(unittest.TestCase):

    EXPECTED = {
        "spearman": (12, 3, 16, 20),
        "archer": (17, 2, 22, 25),
        "cavalry": (10, 6, 58, 65),
        "royal_guard": (30, 12, 71, 80),
    }

    def test_unit_costs(self):
        for unit_type, expected in self.EXPECTED.items():
            with self.subTest(unit=unit_type):
                unit = UNITS[unit_type]
                actual = (
                    unit["wood"],
                    unit["stone"],
                    unit["gold"],
                    unit["food"],
                )
                self.assertEqual(actual, expected)

    def test_royal_guard_costs_slightly_more_than_four_spearmen(self):
        spearman_value = resource_value(UNITS["spearman"])
        guard_value = resource_value(UNITS["royal_guard"])

        four_spearmen_value = spearman_value * 4

        self.assertGreater(guard_value, four_spearmen_value)
        self.assertLessEqual(
            guard_value,
            four_spearmen_value * 1.05,
        )

    def test_guard_is_not_priced_like_five_spearmen(self):
        spearman_value = resource_value(UNITS["spearman"])
        guard_value = resource_value(UNITS["royal_guard"])

        self.assertLess(guard_value, spearman_value * 5)


if __name__ == "__main__":
    unittest.main()

import unittest
from decimal import Decimal

from bot.services.economy import (
    VASSAL_TRIBUTE_RATE,
    calculate_vassal_tribute,
    calculate_realm_income,
)


class TestVassalTribute(unittest.TestCase):

    def test_tribute_rate_is_twenty_percent(self):
        self.assertEqual(
            VASSAL_TRIBUTE_RATE,
            Decimal("0.20"),
        )

    def test_vassal_keeps_eighty_percent(self):
        produced = {
            "wood": 1000,
            "stone": 500,
            "gold": 250,
            "food": 2000,
        }

        tribute, retained = calculate_vassal_tribute(
            produced
        )

        self.assertEqual(tribute["wood"], 200)
        self.assertEqual(retained["wood"], 800)

        self.assertEqual(tribute["stone"], 100)
        self.assertEqual(retained["stone"], 400)

        self.assertEqual(tribute["gold"], 50)
        self.assertEqual(retained["gold"], 200)

        self.assertEqual(tribute["food"], 400)
        self.assertEqual(retained["food"], 1600)

    def test_fractional_tribute_rounds_down(self):
        produced = {
            "wood": 9,
            "stone": 0,
            "gold": 0,
            "food": 0,
        }

        tribute, retained = calculate_vassal_tribute(
            produced
        )

        self.assertEqual(tribute["wood"], 1)
        self.assertEqual(retained["wood"], 8)

    def test_negative_production_does_not_create_tribute(self):
        produced = {
            "wood": -100,
            "stone": 0,
            "gold": 0,
            "food": 0,
        }

        tribute, retained = calculate_vassal_tribute(
            produced
        )

        self.assertEqual(tribute["wood"], 0)
        self.assertEqual(retained["wood"], 0)

    def test_non_vassal_keeps_all_production(self):
        buildings = []

        income = calculate_realm_income(
            buildings,
            elapsed_minutes=60,
            is_vassal=False,
        )

        self.assertEqual(income["tribute"]["wood"], 0)
        self.assertEqual(income["retained"]["wood"], 0)


if __name__ == "__main__":
    unittest.main()

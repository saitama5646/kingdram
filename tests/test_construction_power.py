import unittest
from pathlib import Path

from bot.workers.construction import (
    calculate_construction_power_gain,
)


class ConstructionPowerTests(unittest.TestCase):

    def test_new_building_level_one(self):
        self.assertEqual(
            calculate_construction_power_gain(0, 1),
            25,
        )

    def test_normal_upgrade(self):
        self.assertEqual(
            calculate_construction_power_gain(1, 2),
            25,
        )

    def test_multiple_levels(self):
        self.assertEqual(
            calculate_construction_power_gain(1, 4),
            75,
        )

    def test_same_level_gives_no_power(self):
        self.assertEqual(
            calculate_construction_power_gain(3, 3),
            0,
        )

    def test_lower_target_gives_no_power(self):
        self.assertEqual(
            calculate_construction_power_gain(4, 2),
            0,
        )

    def test_negative_previous_level_is_normalized(self):
        self.assertEqual(
            calculate_construction_power_gain(-2, 1),
            25,
        )

    def test_worker_serializes_realm_construction(self):
        source = Path(
            "bot/workers/construction.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "SELECT id\n                    FROM realms",
            source,
        )

        self.assertIn(
            "FOR UPDATE",
            source,
        )

        self.assertIn(
            "power = power + $1",
            source,
        )

        self.assertIn(
            "if power_gain > 0:",
            source,
        )


if __name__ == "__main__":
    unittest.main()

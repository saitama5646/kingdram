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

        normalized_source = " ".join(source.split())

        self.assertIn(
            "SELECT id FROM realms",
            normalized_source,
        )

        self.assertIn("FOR UPDATE", source)
        self.assertIn("power = power + $1", source)
        self.assertIn("if power_gain > 0:", source)

    def test_each_construction_has_its_own_transaction(self):
        source = Path(
            "bot/workers/construction.py"
        ).read_text(encoding="utf-8")

        self.assertIn("for candidate in due_ids:", source)
        self.assertIn("async with connection.transaction():", source)
        self.assertIn("FOR UPDATE OF cq SKIP LOCKED", source)

    def test_individual_construction_error_does_not_stop_batch(self):
        source = Path(
            "bot/workers/construction.py"
        ).read_text(encoding="utf-8")

        self.assertIn("except asyncio.CancelledError:", source)
        self.assertIn(
            "Se continuará con las demás construcciones.",
            source,
        )
        self.assertIn("                continue", source)

    def test_notification_is_sent_after_transaction(self):
        source = Path(
            "bot/workers/construction.py"
        ).read_text(encoding="utf-8")

        function_source = source[
            source.index("async def finish_constructions"):
            source.index("async def construction_worker")
        ]

        notification_position = function_source.index("notification = {")
        send_position = function_source.index("await bot.send_message(")

        self.assertLess(notification_position, send_position)
        self.assertIn("if notification is None:", function_source)


if __name__ == "__main__":
    unittest.main()

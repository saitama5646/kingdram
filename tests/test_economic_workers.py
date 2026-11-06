import unittest
from pathlib import Path

from bot.workers.production import split_tribute


class EconomicWorkerTests(unittest.TestCase):

    def test_tribute_split_preserves_total_production(self):
        production = {
            "wood": 101,
            "stone": 99,
            "gold": 50,
            "food": 1,
        }

        tribute, retained = split_tribute(
            production,
            0.20,
        )

        for resource in production:
            self.assertEqual(
                tribute[resource] + retained[resource],
                production[resource],
            )

    def test_tribute_rounds_down(self):
        tribute, retained = split_tribute(
            {
                "wood": 9,
                "stone": 4,
                "gold": 1,
                "food": 0,
            },
            0.20,
        )

        self.assertEqual(tribute["wood"], 1)
        self.assertEqual(tribute["stone"], 0)
        self.assertEqual(tribute["gold"], 0)
        self.assertEqual(tribute["food"], 0)
        self.assertEqual(retained["wood"], 8)

    def test_zero_tribute_rate(self):
        production = {
            "wood": 100,
            "stone": 50,
            "gold": 25,
            "food": 10,
        }

        tribute, retained = split_tribute(production, 0)

        self.assertTrue(all(value == 0 for value in tribute.values()))
        self.assertEqual(retained, production)

    def test_full_tribute_rate(self):
        production = {
            "wood": 100,
            "stone": 50,
            "gold": 25,
            "food": 10,
        }

        tribute, retained = split_tribute(production, 1)

        self.assertEqual(tribute, production)
        self.assertTrue(all(value == 0 for value in retained.values()))

    def test_production_processes_realms_independently(self):
        source = Path(
            "bot/workers/production.py"
        ).read_text(encoding="utf-8")

        function = source[
            source.index("async def produce_resources"):
            source.index("async def production_worker")
        ]

        self.assertIn("for candidate in realm_ids:", function)
        self.assertIn("async with connection.transaction():", function)
        self.assertIn("except asyncio.CancelledError:", function)
        self.assertIn(
            "Se continuará con los demás reinos.",
            function,
        )
        self.assertIn("ORDER BY realm_id", function)
        self.assertIn("FOR UPDATE", function)

    def test_tribute_and_vassal_resources_are_atomic(self):
        source = Path(
            "bot/workers/production.py"
        ).read_text(encoding="utf-8")

        function = source[
            source.index("async def produce_resources"):
            source.index("async def production_worker")
        ]

        self.assertIn("vassalage_tribute_log", function)
        self.assertIn("get_realm_storage_capacity", function)
        self.assertIn("resource_realm_ids", function)
        self.assertIn("connection.transaction()", function)

    def test_research_uses_independent_transactions(self):
        source = Path(
            "bot/workers/research.py"
        ).read_text(encoding="utf-8")

        function = source[
            source.index("async def finish_research"):
            source.index("async def research_worker")
        ]

        self.assertIn("for candidate in due_ids:", function)
        self.assertIn("async with connection.transaction():", function)
        self.assertIn("FOR UPDATE OF rq SKIP LOCKED", function)
        self.assertIn("FOR UPDATE", function)
        self.assertIn("except asyncio.CancelledError:", function)
        self.assertIn(
            "Se continuará con las demás investigaciones.",
            function,
        )

    def test_research_notification_is_after_transaction(self):
        source = Path(
            "bot/workers/research.py"
        ).read_text(encoding="utf-8")

        function = source[
            source.index("async def finish_research"):
            source.index("async def research_worker")
        ]

        notification_position = function.index("notification = {")
        send_position = function.index("await bot.send_message(")

        self.assertLess(notification_position, send_position)
        self.assertIn("if notification is None:", function)


if __name__ == "__main__":
    unittest.main()

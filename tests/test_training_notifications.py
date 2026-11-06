import unittest
from pathlib import Path


class TrainingNotificationTests(unittest.TestCase):
    def setUp(self):
        self.service = Path(
            "bot/services/military.py"
        ).read_text(encoding="utf-8")

        self.worker = Path(
            "bot/workers/military.py"
        ).read_text(encoding="utf-8")

    def test_training_rows_are_locked(self):
        self.assertIn("FOR UPDATE OF tq", self.service)

    def test_only_deleted_queue_entries_are_returned(self):
        self.assertIn(
            "DELETE FROM training_queue",
            self.service,
        )
        self.assertIn("RETURNING id", self.service)
        self.assertIn("if deleted_id is not None:", self.service)
        self.assertIn("processed.append(item)", self.service)
        self.assertIn("return processed", self.service)

    def test_worker_notifies_processed_entries(self):
        self.assertIn(
            "completed = await finish_training(",
            self.worker,
        )
        self.assertIn(
            "notifications.extend(completed)",
            self.worker,
        )
        self.assertNotIn(
            "notifications = due_entries",
            self.worker,
        )

    def test_worker_discovers_due_realms(self):
        self.assertIn(
            "SELECT DISTINCT realm_id",
            self.worker,
        )
        self.assertIn(
            "WHERE finishes_at <= NOW()",
            self.worker,
        )


if __name__ == "__main__":
    unittest.main()

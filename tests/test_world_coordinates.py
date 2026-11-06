import unittest
from pathlib import Path

from bot.services.world import (
    MAX_CONTINENTS,
    TERRITORIES_PER_CONTINENT,
    POSITIONS_PER_TERRITORY,
    TOTAL_WORLD_POSITIONS,
    normalize_coordinates,
)


class WorldCoordinatesTests(unittest.TestCase):

    def test_world_dimensions(self):
        self.assertEqual(MAX_CONTINENTS, 100)
        self.assertEqual(TERRITORIES_PER_CONTINENT, 3)
        self.assertEqual(POSITIONS_PER_TERRITORY, 20)
        self.assertEqual(TOTAL_WORLD_POSITIONS, 6000)

    def test_first_coordinate(self):
        self.assertEqual(
            normalize_coordinates((1, 1, 1)),
            (1, 1, 1),
        )

    def test_last_coordinate(self):
        self.assertEqual(
            normalize_coordinates((100, 3, 20)),
            (100, 3, 20),
        )

    def test_invalid_continent(self):
        for value in (0, 101):
            with self.subTest(continent=value):
                with self.assertRaises(ValueError):
                    normalize_coordinates((value, 1, 1))

    def test_invalid_territory(self):
        for value in (0, 4):
            with self.subTest(territory=value):
                with self.assertRaises(ValueError):
                    normalize_coordinates((1, value, 1))

    def test_invalid_position(self):
        for value in (0, 21):
            with self.subTest(position=value):
                with self.assertRaises(ValueError):
                    normalize_coordinates((1, 1, value))

    def test_incomplete_coordinates(self):
        with self.assertRaises(ValueError):
            normalize_coordinates((1, 2))

    def test_missing_coordinates(self):
        with self.assertRaises(ValueError):
            normalize_coordinates(None)

    def test_sql_migration_matches_world_dimensions(self):
        sql = Path("bot/database/world.sql").read_text(
            encoding="utf-8"
        )

        self.assertIn("selected_continent IN 1..100", sql)
        self.assertIn("selected_region IN 1..3", sql)
        self.assertIn("selected_position IN 1..20", sql)
        self.assertIn("ROW_NUMBER() OVER", sql)
        self.assertIn("chk_realms_world_coordinates", sql)

        migration_position = sql.index(
            "-- Normalizar y asignar coordenadas del mundo."
        )
        index_position = sql.index(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_realms_world_position"
        )

        self.assertLess(migration_position, index_position)


if __name__ == "__main__":
    unittest.main()

import unittest

from bot.services.combat_simulator import (
    simulate_battle,
    validate_roster,
)


class CombatSimulatorTests(unittest.TestCase):

    def setUp(self):
        self.attackers = [
            {
                "unit_type": "spearman",
                "quantity": 20,
            },
            {
                "unit_type": "archer",
                "quantity": 10,
            },
        ]

        self.defenders = [
            {
                "unit_type": "spearman",
                "quantity": 15,
            },
            {
                "unit_type": "royal_guard",
                "quantity": 5,
            },
        ]

    def test_simulation_returns_expected_structure(self):
        result = simulate_battle(
            self.attackers,
            self.defenders,
            battles=5,
            seed=100,
        )

        self.assertEqual(result["battles"], 5)

        self.assertIn(
            "attacker_victory",
            result["outcomes"],
        )

        self.assertIn(
            "attacker_losses",
            result["averages"],
        )

        self.assertIn(
            "defender_survivors",
            result["averages"],
        )

    def test_simulation_is_reproducible(self):
        first = simulate_battle(
            self.attackers,
            self.defenders,
            battles=5,
            seed=1234,
        )

        second = simulate_battle(
            self.attackers,
            self.defenders,
            battles=5,
            seed=1234,
        )

        self.assertEqual(first, second)

    def test_outcome_percentages_sum_to_one_hundred(self):
        result = simulate_battle(
            self.attackers,
            self.defenders,
            battles=10,
            seed=200,
        )

        percentage = sum(
            item["percentage"]
            for item in result["outcomes"].values()
        )

        self.assertAlmostEqual(
            percentage,
            100.0,
        )

    def test_simulation_rejects_empty_army(self):
        with self.assertRaises(ValueError):
            simulate_battle(
                [],
                self.defenders,
                battles=1,
            )

    def test_simulation_rejects_unknown_unit(self):
        invalid = [
            {
                "unit_type": "dragon_unknown",
                "quantity": 5,
            },
        ]

        with self.assertRaises(ValueError):
            validate_roster(
                invalid,
                "Atacante",
            )

    def test_simulation_rejects_duplicate_units(self):
        invalid = [
            {
                "unit_type": "spearman",
                "quantity": 5,
            },
            {
                "unit_type": "spearman",
                "quantity": 10,
            },
        ]

        with self.assertRaises(ValueError):
            validate_roster(
                invalid,
                "Atacante",
            )

    def test_simulation_rejects_invalid_quantity(self):
        invalid = [
            {
                "unit_type": "spearman",
                "quantity": -5,
            },
        ]

        with self.assertRaises(ValueError):
            validate_roster(
                invalid,
                "Atacante",
            )

    def test_simulation_rejects_zero_battles(self):
        with self.assertRaises(ValueError):
            simulate_battle(
                self.attackers,
                self.defenders,
                battles=0,
            )


if __name__ == "__main__":
    unittest.main()

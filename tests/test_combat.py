import unittest
from unittest.mock import patch

from bot.workers.missions import (
    army_quantity,
    army_power,
    calculate_damage,
    calculate_losses,
    apply_losses,
    initial_morale,
    update_morale,
    losses_map,
)


class CombatTests(unittest.TestCase):

    def setUp(self):
        self.attackers = [
            {"unit_type": "spearman", "quantity": 20},
            {"unit_type": "archer", "quantity": 10},
        ]

        self.defenders = [
            {"unit_type": "spearman", "quantity": 15},
            {"unit_type": "royal_guard", "quantity": 5},
        ]

    def test_army_quantity(self):
        troops = [
            {"unit_type": "spearman", "quantity": 10},
            {"unit_type": "archer", "quantity": 5},
            {"unit_type": "cavalry", "quantity": -3},
        ]

        self.assertEqual(army_quantity(troops), 15)

    def test_army_power(self):
        troops = [
            {"unit_type": "spearman", "quantity": 10},
            {"unit_type": "archer", "quantity": 5},
        ]

        expected_attack = (
            10 * 8
            + 5 * 15
        )

        expected_defense = (
            10 * 12
            + 5 * 5
        )

        self.assertEqual(
            army_power(troops, "attack"),
            expected_attack,
        )

        self.assertEqual(
            army_power(troops, "defense"),
            expected_defense,
        )

    def test_damage_without_defenders_is_zero(self):
        damage = calculate_damage(
            self.attackers,
            [],
            1.0,
        )

        self.assertEqual(damage, 0.0)

    def test_damage_with_defenders_is_positive(self):
        with patch(
            "bot.workers.missions.random.uniform",
            return_value=1.0,
        ):
            damage = calculate_damage(
                self.attackers,
                self.defenders,
                1.0,
            )

        self.assertGreater(damage, 0)

    def test_losses_never_exceed_available_units(self):
        troops = [
            {"unit_type": "spearman", "quantity": 10},
            {"unit_type": "archer", "quantity": 5},
        ]

        losses = calculate_losses(
            troops,
            100000,
        )

        self.assertLessEqual(
            sum(losses.values()),
            army_quantity(troops),
        )

        for troop in troops:
            self.assertLessEqual(
                losses.get(troop["unit_type"], 0),
                troop["quantity"],
            )

    def test_zero_damage_causes_no_losses(self):
        losses = calculate_losses(
            self.attackers,
            0,
        )

        self.assertEqual(losses, {})

    def test_apply_losses_preserves_survivors(self):
        troops = [
            {"unit_type": "spearman", "quantity": 10},
            {"unit_type": "archer", "quantity": 5},
        ]

        losses = {
            "spearman": 4,
            "archer": 2,
        }

        survivors = apply_losses(
            troops,
            losses,
        )

        self.assertEqual(
            survivors,
            [
                {"unit_type": "spearman", "quantity": 6},
                {"unit_type": "archer", "quantity": 3},
            ],
        )

    def test_destroyed_unit_is_removed(self):
        troops = [
            {"unit_type": "spearman", "quantity": 10},
            {"unit_type": "archer", "quantity": 5},
        ]

        losses = {
            "spearman": 10,
            "archer": 2,
        }

        survivors = apply_losses(
            troops,
            losses,
        )

        self.assertEqual(
            survivors,
            [
                {"unit_type": "archer", "quantity": 3},
            ],
        )

    def test_losses_map_calculates_real_losses(self):
        original = [
            {"unit_type": "spearman", "quantity": 10},
            {"unit_type": "archer", "quantity": 5},
        ]

        survivors = [
            {"unit_type": "spearman", "quantity": 7},
            {"unit_type": "archer", "quantity": 2},
        ]

        losses = losses_map(
            original,
            survivors,
        )

        self.assertEqual(
            losses,
            {
                "spearman": 3,
                "archer": 3,
            },
        )

    def test_initial_morale_stays_within_limits(self):
        morale = initial_morale(
            100,
            10,
        )

        self.assertGreaterEqual(morale, 0.25)
        self.assertLessEqual(morale, 1.25)

    def test_updated_morale_stays_within_limits(self):
        morale = update_morale(
            1.0,
            100,
            100,
            0,
            100,
        )

        self.assertGreaterEqual(morale, 0.25)
        self.assertLessEqual(morale, 1.25)


if __name__ == "__main__":
    unittest.main()

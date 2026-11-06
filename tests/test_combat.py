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
    expand_combat_units,
    aggregate_combat_units,
    resolve_volley,
    resolve_battle_round,
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

        improved_defense = army_power(
            troops,
            "defense",
            {"military_hull": 0.20},
        )

        self.assertAlmostEqual(
            improved_defense,
            expected_defense * 1.20,
        )

        improved_defense = army_power(
            troops,
            "defense",
            {"military_hull": 0.20},
        )

        self.assertAlmostEqual(
            improved_defense,
            expected_defense * 1.20,
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

    def test_morale_falls_more_when_losses_are_heavy(self):
        light_losses = update_morale(
            1.0,
            10,
            100,
            0,
            100,
        )

        heavy_losses = update_morale(
            1.0,
            70,
            100,
            0,
            100,
        )

        self.assertLess(heavy_losses, light_losses)

    def test_morale_improves_when_enemy_losses_are_heavy(self):
        morale = update_morale(
            1.0,
            0,
            100,
            50,
            100,
        )

        self.assertGreater(morale, 1.0)

    def test_morale_is_capped_at_maximum(self):
        morale = update_morale(
            1.25,
            0,
            100,
            100,
            100,
        )

        self.assertEqual(morale, 1.25)

    def test_morale_is_capped_at_minimum(self):
        morale = update_morale(
            0.25,
            100,
            100,
            0,
            100,
        )

        self.assertEqual(morale, 0.25)


    def test_research_improves_attack_and_hull(self):
        units = expand_combat_units(
            [{"unit_type": "spearman", "quantity": 1}],
            {
                "military_attack": 0.50,
                "military_defense": 0.25,
            },
        )

        self.assertEqual(units[0]["attack"], 12)
        self.assertEqual(units[0]["shield"], 12)
        self.assertEqual(units[0]["hull"], 150)

    def test_aggregate_combat_units_counts_survivors(self):
        units = [
            {"unit_type": "spearman", "destroyed": False},
            {"unit_type": "spearman", "destroyed": True},
            {"unit_type": "archer", "destroyed": False},
        ]

        self.assertEqual(
            aggregate_combat_units(units),
            [
                {"unit_type": "archer", "quantity": 1},
                {"unit_type": "spearman", "quantity": 1},
            ],
        )

    def test_survivor_validation_returns_exact_losses(self):
        from bot.workers.missions import (
            validate_survivor_quantities,
        )

        original = [
            {"unit_type": "spearman", "quantity": 10},
            {"unit_type": "archer", "quantity": 5},
        ]
        survivors = [
            {"unit_type": "spearman", "quantity": 7},
            {"unit_type": "archer", "quantity": 2},
        ]

        self.assertEqual(
            validate_survivor_quantities(
                original,
                survivors,
                "Atacante",
            ),
            6,
        )

    def test_survivor_validation_rejects_extra_troops(self):
        from bot.workers.missions import (
            validate_survivor_quantities,
        )

        original = [
            {"unit_type": "spearman", "quantity": 10},
        ]
        survivors = [
            {"unit_type": "spearman", "quantity": 11},
        ]

        with self.assertRaises(RuntimeError):
            validate_survivor_quantities(
                original,
                survivors,
                "Atacante",
            )

    def test_survivor_validation_rejects_unknown_unit_type(self):
        from bot.workers.missions import (
            validate_survivor_quantities,
        )

        original = [
            {"unit_type": "spearman", "quantity": 10},
        ]
        survivors = [
            {"unit_type": "archer", "quantity": 1},
        ]

        with self.assertRaises(RuntimeError):
            validate_survivor_quantities(
                original,
                survivors,
                "Defensor",
            )

    def test_shield_absorbs_damage_before_hull(self):
        shooters = [
            {"attack": 15, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 6,
                "hull": 120,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch("bot.workers.missions.random.randrange", return_value=0):
            with patch("bot.workers.missions.random.uniform", return_value=1.0):
                resolve_volley(shooters, targets, 1.0)

        self.assertEqual(targets[0]["hull_damage"], 9)

    def test_shields_regenerate_between_rounds(self):
        shooters = [
            {"attack": 8, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 10,
                "hull": 120,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch("bot.workers.missions.random.randrange", return_value=0):
            with patch("bot.workers.missions.random.uniform", return_value=1.0):
                resolve_volley(shooters, targets, 1.0)
                resolve_volley(shooters, targets, 1.0)

        self.assertEqual(targets[0]["hull_damage"], 0)

    def test_explosion_probability_uses_remaining_hull(self):
        shooters = [
            {"attack": 80, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch("bot.workers.missions.random.randrange", return_value=0):
            with patch("bot.workers.missions.random.uniform", return_value=1.0):
                with patch("bot.workers.missions.random.random", return_value=0.79):
                    resolve_volley(shooters, targets, 1.0)

        self.assertTrue(targets[0]["destroyed"])
    def test_unit_at_exactly_thirty_percent_hull_does_not_roll_explosion(self):
        shooters = [
            {"attack": 70, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch("bot.workers.missions.random.randrange", return_value=0):
            with patch("bot.workers.missions.random.uniform", return_value=1.0):
                with patch("bot.workers.missions.random.random") as random_roll:
                    resolve_volley(shooters, targets, 1.0)

        random_roll.assert_not_called()
        self.assertFalse(targets[0]["destroyed"])
    def test_both_armies_fire_before_losses_are_removed(self):
        attackers = [
            {
                "unit_type": "spearman",
                "attack": 100,
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        defenders = [
            {
                "unit_type": "archer",
                "attack": 100,
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch("bot.workers.missions.random.randrange", return_value=0):
            with patch("bot.workers.missions.random.uniform", return_value=1.0):
                with patch("bot.workers.missions.random.random", return_value=1.0):
                    result = resolve_battle_round(
                        attackers,
                        defenders,
                        1.0,
                        1.0,
                    )

        attacker_survivors, defender_survivors = result[0], result[1]

        self.assertEqual(attacker_survivors, [])
        self.assertEqual(defender_survivors, [])

    def test_small_battle_does_not_automatically_destroy_everyone(self):
        attackers = expand_combat_units([
            {"unit_type": "spearman", "quantity": 20},
        ])

        defenders = expand_combat_units([
            {"unit_type": "royal_guard", "quantity": 5},
        ])

        with patch("bot.workers.missions.random.randrange", return_value=0):
            with patch("bot.workers.missions.random.random", return_value=1.0):
                attacker_survivors, defender_survivors, _, _ = (
                    resolve_battle_round(
                        attackers,
                        defenders,
                        1.0,
                        1.0,
                    )
                )

        self.assertGreater(
            len(attacker_survivors) + len(defender_survivors),
            0,
        )


    def test_shield_research_improves_shield(self):
        units = expand_combat_units(
            [{"unit_type": "spearman", "quantity": 1}],
            {
                "military_attack": 0.10,
                "military_hull": 0.20,
                "military_shield": 0.50,
            },
        )

        self.assertAlmostEqual(units[0]["attack"], 8.8)
        self.assertAlmostEqual(units[0]["shield"], 18)
        self.assertAlmostEqual(units[0]["hull"], 144)

    def test_legacy_defense_research_still_improves_hull(self):
        units = expand_combat_units(
            [{"unit_type": "spearman", "quantity": 1}],
            {"military_defense": 0.25},
        )

        self.assertAlmostEqual(units[0]["hull"], 150)

    def test_volley_only_targets_living_units(self):
        shooters = [
            {"attack": 5, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "destroyed": True,
            },
            {
                "unit_type": "archer",
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch(
            "bot.workers.missions.random.randrange",
            return_value=0,
        ) as target_roll:
            with patch(
                "bot.workers.missions.random.uniform",
                return_value=1.0,
            ):
                resolve_volley(shooters, targets, 1.0)

        target_roll.assert_called_once_with(1)
        self.assertEqual(targets[0]["hull_damage"], 0)
        self.assertEqual(targets[1]["hull_damage"], 5)

    def test_volley_tracks_shield_and_hull_damage(self):
        shooters = [
            {"attack": 15, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 6,
                "hull": 120,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch(
            "bot.workers.missions.random.randrange",
            return_value=0,
        ):
            with patch(
                "bot.workers.missions.random.uniform",
                return_value=1.0,
            ):
                resolve_volley(shooters, targets, 1.0)

        self.assertEqual(targets[0]["round_shield_damage"], 6)
        self.assertEqual(targets[0]["round_hull_damage"], 9)

    def test_damage_multiplier_has_maximum_morale_penalty(self):
        from bot.workers.missions import morale_damage_multiplier

        self.assertAlmostEqual(
            morale_damage_multiplier(0.20),
            0.90,
        )

        self.assertAlmostEqual(
            morale_damage_multiplier(0.10),
            0.90,
        )

    def test_damage_multiplier_preserves_positive_morale_bonus(self):
        from bot.workers.missions import morale_damage_multiplier

        self.assertAlmostEqual(
            morale_damage_multiplier(1.10),
            1.10,
        )

    def test_zero_attack_does_not_damage_targets(self):
        shooters = [
            {"attack": 0, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 12,
                "hull": 120,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch("bot.workers.missions.random.randrange", return_value=0):
            resolve_volley(shooters, targets, 1.0)

        self.assertEqual(targets[0]["hull_damage"], 0)
        self.assertFalse(targets[0]["destroyed"])

    def test_round_attacks_are_simultaneous(self):
        from bot.workers.missions import (
            resolve_battle_round_detailed,
        )

        attackers = [
            {
                "unit_type": "spearman",
                "attack": 100,
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "destroyed": False,
                "quantity": 1,
            },
        ]

        defenders = [
            {
                "unit_type": "archer",
                "attack": 30,
                "shield": 0,
                "hull": 50,
                "hull_damage": 0,
                "destroyed": False,
                "quantity": 1,
            },
        ]

        with patch(
            "bot.workers.missions.random.randrange",
            return_value=0,
        ):
            with patch(
                "bot.workers.missions.random.uniform",
                return_value=1.0,
            ):
                with patch(
                    "bot.workers.missions.random.random",
                    return_value=1.0,
                ):
                    (
                        attackers_after,
                        defenders_after,
                        attacker_damage,
                        defender_damage,
                        details,
                    ) = resolve_battle_round_detailed(
                        attackers,
                        defenders,
                        1.0,
                        1.0,
                    )

        # El atacante destruye al defensor durante la salva.
        self.assertEqual(defenders_after, [])

        # Pero el defensor ya tenía su salva preparada:
        # sus disparos de esta ronda también deben resolverse.
        self.assertEqual(len(attackers_after), 1)
        self.assertEqual(
            attackers_after[0]["hull_damage"],
            30,
        )

        self.assertEqual(attacker_damage, 50)
        self.assertEqual(defender_damage, 30)

        self.assertEqual(
            details["attacker_hull_damage"],
            30,
        )

    def test_destroyed_units_do_not_receive_more_shots(self):
        shooters = [
            {"attack": 100, "destroyed": False},
            {"attack": 100, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 0,
                "hull": 50,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch("bot.workers.missions.random.choice", side_effect=[0]):
            with patch("bot.workers.missions.random.uniform", return_value=1.0):
                with patch("bot.workers.missions.random.random", return_value=1.0):
                    resolve_volley(shooters, targets, 1.0)

        self.assertTrue(targets[0]["destroyed"])


    def test_large_army_is_stored_as_combat_groups(self):
        units = expand_combat_units([
            {"unit_type": "spearman", "quantity": 2500},
        ])

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["quantity"], 2500)

        survivors = aggregate_combat_units(units)

        self.assertEqual(
            survivors,
            [{"unit_type": "spearman", "quantity": 2500}],
        )

    def test_grouped_army_loses_only_the_targeted_unit(self):
        shooters = [
            {
                "unit_type": "archer",
                "attack": 101,
                "destroyed": False,
                "quantity": 1,
            },
        ]

        targets = [
            {
                "unit_type": "spearman",
                "attack": 8,
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "destroyed": False,
                "quantity": 2000,
            },
        ]

        with patch(
            "bot.workers.missions.random.randrange",
            return_value=0,
        ):
            with patch(
                "bot.workers.missions.random.uniform",
                return_value=1.0,
            ):
                with patch(
                    "bot.workers.missions.random.random",
                    return_value=1.0,
                ):
                    resolve_volley(shooters, targets, 1.0)

        remaining = sum(
            int(unit.get("quantity", 1))
            for unit in targets
            if not unit.get("destroyed", False)
        )

        self.assertEqual(remaining, 1999)

    def test_grouped_target_preserves_total_quantity_after_hit(self):
        shooters = [
            {"attack": 10, "quantity": 1, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "attack": 8,
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "round_shield_damage": 0,
                "round_hull_damage": 0,
                "quantity": 2000,
                "destroyed": False,
            },
        ]

        with patch(
            "bot.workers.missions.random.randrange",
            return_value=0,
        ):
            with patch(
                "bot.workers.missions.random.uniform",
                return_value=1.0,
            ):
                resolve_volley(shooters, targets, 1.0)

        total_quantity = sum(
            int(target.get("quantity", 1))
            for target in targets
        )

        self.assertEqual(total_quantity, 2000)

        damaged_quantity = sum(
            int(target.get("quantity", 1))
            for target in targets
            if float(target.get("hull_damage", 0)) > 0
        )

        self.assertEqual(damaged_quantity, 1)

    def test_destroyed_target_is_preserved_and_skipped(self):
        shooters = [
            {"attack": 100, "quantity": 2, "destroyed": False},
        ]

        targets = [
            {
                "unit_type": "spearman",
                "shield": 0,
                "hull": 50,
                "hull_damage": 0,
                "destroyed": False,
            },
            {
                "unit_type": "archer",
                "shield": 0,
                "hull": 200,
                "hull_damage": 0,
                "destroyed": False,
            },
        ]

        with patch(
            "bot.workers.missions.random.randrange",
            side_effect=[0, 0],
        ) as target_roll:
            with patch(
                "bot.workers.missions.random.uniform",
                return_value=1.0,
            ):
                with patch(
                    "bot.workers.missions.random.random",
                    return_value=1.0,
                ):
                    resolve_volley(shooters, targets, 1.0)

        self.assertEqual(target_roll.call_args_list[0].args, (2,))
        self.assertEqual(target_roll.call_args_list[1].args, (1,))

        destroyed = [
            target for target in targets
            if target.get("destroyed", False)
        ]

        survivors = [
            target for target in targets
            if not target.get("destroyed", False)
        ]

        self.assertEqual(len(destroyed), 1)
        self.assertEqual(destroyed[0]["unit_type"], "spearman")
        self.assertEqual(destroyed[0]["hull_damage"], 50)

        self.assertEqual(len(survivors), 1)
        self.assertEqual(survivors[0]["unit_type"], "archer")
        self.assertEqual(survivors[0]["hull_damage"], 100)


    def test_fenwick_selection_preserves_large_group_quantity(self):
        shooters = [
            {
                "attack": 10,
                "quantity": 200,
                "destroyed": False,
            },
        ]

        targets = [
            {
                "unit_type": "spearman",
                "attack": 8,
                "shield": 0,
                "hull": 100,
                "hull_damage": 0,
                "round_shield_damage": 0,
                "round_hull_damage": 0,
                "quantity": 2000,
                "destroyed": False,
            },
        ]

        with patch(
            "bot.workers.missions.random.randrange",
            return_value=0,
        ):
            with patch(
                "bot.workers.missions.random.uniform",
                return_value=1.0,
            ):
                with patch(
                    "bot.workers.missions.random.random",
                    return_value=1.0,
                ):
                    resolve_volley(
                        shooters,
                        targets,
                        1.0,
                    )

        total_quantity = sum(
            int(target.get("quantity", 1))
            for target in targets
        )

        damaged_quantity = sum(
            int(target.get("quantity", 1))
            for target in targets
            if float(target.get("hull_damage", 0)) > 0
        )

        self.assertEqual(total_quantity, 2000)
        self.assertEqual(damaged_quantity, 200)


if __name__ == "__main__":
    unittest.main()

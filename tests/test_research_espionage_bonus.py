import unittest

from bot.services.research import get_research_effects


class EspionageResearchBonusTests(unittest.TestCase):

    def test_network_success_bonus_is_not_double_counted(self):
        effects = get_research_effects({
            "espionage_network": 1,
        })

        self.assertAlmostEqual(
            effects["spy_success_bonus"],
            0.02,
        )

    def test_network_success_bonus_scales_by_level(self):
        for level in range(1, 6):
            with self.subTest(level=level):
                effects = get_research_effects({
                    "espionage_network": level,
                })

                self.assertAlmostEqual(
                    effects["spy_success_bonus"],
                    level * 0.02,
                )

    def test_infiltration_bonus_is_added_once(self):
        effects = get_research_effects({
            "espionage_network": 2,
            "infiltration": 1,
        })

        self.assertAlmostEqual(
            effects["spy_success_bonus"],
            0.09,
        )

    def test_network_cost_reduction_levels(self):
        self.assertEqual(
            get_research_effects({
                "espionage_network": 1,
            })["spy_cost_reduction"],
            0.0,
        )

        self.assertEqual(
            get_research_effects({
                "espionage_network": 2,
            })["spy_cost_reduction"],
            0.05,
        )

        self.assertEqual(
            get_research_effects({
                "espionage_network": 4,
            })["spy_cost_reduction"],
            0.10,
        )

    def test_network_training_speed_levels(self):
        self.assertEqual(
            get_research_effects({
                "espionage_network": 2,
            })["spy_training_speed"],
            0.0,
        )

        self.assertEqual(
            get_research_effects({
                "espionage_network": 3,
            })["spy_training_speed"],
            0.10,
        )

        self.assertEqual(
            get_research_effects({
                "espionage_network": 5,
            })["spy_training_speed"],
            0.15,
        )


if __name__ == "__main__":
    unittest.main()

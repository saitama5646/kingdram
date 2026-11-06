
import unittest

from bot.services.espionage import (
    calculate_spy_success,
    calculate_mission_duration,
    clamp,
    calculate_spy_training_duration,
)


class EspionageTests(unittest.TestCase):

    def test_success_probability_is_bounded(self):
        self.assertGreaterEqual(
            calculate_spy_success(1),
            0.15,
        )

        self.assertLessEqual(
            calculate_spy_success(100),
            0.90,
        )

    def test_infiltration_increases_success(self):
        base = calculate_spy_success(3)

        improved = calculate_spy_success(
            3,
            infiltration_bonus=0.15,
        )

        self.assertGreater(improved, base)

    def test_counterespionage_reduces_success(self):
        base = calculate_spy_success(3)

        protected = calculate_spy_success(
            3,
            counter_bonus=0.15,
        )

        self.assertLess(protected, base)

    def test_probability_clamps_at_maximum(self):
        self.assertEqual(
            calculate_spy_success(
                100,
                infiltration_bonus=1,
            ),
            0.90,
        )

    def test_probability_clamps_at_minimum(self):
        self.assertEqual(
            calculate_spy_success(
                1,
                counter_bonus=1,
            ),
            0.15,
        )

    def test_clamp(self):
        self.assertEqual(clamp(2, 0, 1), 1)
        self.assertEqual(clamp(-2, 0, 1), 0)
        self.assertEqual(clamp(0.5, 0, 1), 0.5)

    def test_duration_is_positive(self):
        self.assertGreater(
            calculate_mission_duration(0),
            0,
        )

    def test_duration_increases_with_distance(self):
        near = calculate_mission_duration(100)
        far = calculate_mission_duration(1000)

        self.assertGreater(far, near)


    def test_training_duration_positive(self):
        self.assertGreater(
            calculate_spy_training_duration(1),
            0,
        )

    def test_training_duration_scales_with_quantity(self):
        one = calculate_spy_training_duration(1)
        five = calculate_spy_training_duration(5)
        ten = calculate_spy_training_duration(10)

        self.assertGreater(five, one)
        self.assertGreater(ten, five)

    def test_training_research_reduces_duration(self):
        base = calculate_spy_training_duration(5)
        improved = calculate_spy_training_duration(
            5,
            speed_bonus=0.10,
        )

        self.assertLess(improved, base)

    def test_training_bonus_has_cap(self):
        capped = calculate_spy_training_duration(
            10,
            speed_bonus=0.75,
        )
        excessive = calculate_spy_training_duration(
            10,
            speed_bonus=10,
        )

        self.assertEqual(capped, excessive)

    def test_training_invalid_quantity(self):
        for quantity in (0, 2, 3, -1, 11):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    calculate_spy_training_duration(quantity)

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ambulance_dispatch.metrics import (
    bootstrap_mean_interval,
    paired_b3_gaps,
    signed_cost_gap,
    signed_metric_difference,
    signed_relative_loss_gap,
)


class GapTests(unittest.TestCase):
    def test_cost_gap_is_signed_and_zero_baseline_ratio_is_undefined(self) -> None:
        self.assertEqual(signed_cost_gap(12.0, 10.0).absolute, 2.0)
        self.assertAlmostEqual(signed_cost_gap(12.0, 10.0).relative, 0.2)
        self.assertEqual(signed_cost_gap(8.0, 10.0).absolute, -2.0)
        self.assertIsNone(signed_cost_gap(8.0, 0.0).relative)

    def test_higher_is_better_metrics_preserve_direction(self) -> None:
        self.assertAlmostEqual(signed_metric_difference(0.8, 0.7), 0.1)
        self.assertAlmostEqual(signed_relative_loss_gap(0.8, 0.6), -0.5)
        self.assertIsNone(signed_relative_loss_gap(0.8, 1.0))

    def test_paired_gap_uses_matching_b3_and_keeps_heuristic_sign(self) -> None:
        rows = [
            {"experiment": "comm", "level": "full", "seed": 1, "demand_knowledge": "learned", "policy": "B3", "total_cost": 10, "service_rate": 0.8, "mean_coverage": 0.7},
            {"experiment": "comm", "level": "full", "seed": 1, "demand_knowledge": "learned", "policy": "BID", "total_cost": 8, "service_rate": 0.9, "mean_coverage": 0.8},
            {"experiment": "comm", "level": "none", "seed": 1, "demand_knowledge": "learned", "policy": "BID", "total_cost": 12, "service_rate": 0.6, "mean_coverage": 0.5},
        ]
        gaps = paired_b3_gaps(rows)
        self.assertEqual(gaps[1]["b3_cost_gap_absolute"], -2)
        self.assertAlmostEqual(gaps[1]["b3_cost_gap_relative"], -0.2)
        self.assertNotIn("b3_cost_gap_absolute", gaps[2])


class BootstrapTests(unittest.TestCase):
    def test_interval_is_deterministic_and_contains_sample_mean(self) -> None:
        first = bootstrap_mean_interval([1, 2, 3, 4], resamples=500, seed=51)
        second = bootstrap_mean_interval([1, 2, 3, 4], resamples=500, seed=51)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 2.5)
        self.assertLessEqual(first[1], first[0])
        self.assertGreaterEqual(first[2], first[0])
        self.assertEqual(first[3], 4)

    def test_empty_and_singleton(self) -> None:
        self.assertEqual(bootstrap_mean_interval([], resamples=10)[3], 0)
        self.assertEqual(bootstrap_mean_interval([7.0], resamples=10), (7.0, 7.0, 7.0, 1))


if __name__ == "__main__":
    unittest.main()

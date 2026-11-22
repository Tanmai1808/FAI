from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ambulance_dispatch.metrics import (
    bootstrap_mean_interval,
    compute_unilateral_deviation_statistics,
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

    def test_compute_unilateral_deviation_statistics_synthetic(self) -> None:
        # Hand-computed synthetic test:
        # 2 seeds (1, 2) and 2 agents (0, 1)
        # seed 1: baseline = 100, agent 0 dev = 80 (gain 20), agent 1 dev = 110 (gain -10)
        # seed 2: baseline = 200, agent 0 dev = 190 (gain 10), agent 1 dev = 150 (gain 50)
        # mean baseline cost = (100 + 200) / 2 = 150.0
        # agent 0 mean gain = (20 + 10) / 2 = 15.0, relative = 15/150 = 0.1
        # agent 1 mean gain = (-10 + 50) / 2 = 20.0, relative = 20/150 = 0.13333...
        # epsilon_hat = max(15.0, 20.0) = 20.0, relative = 20/150
        rows = [
            {"seed": 1, "deviator_id": 0, "baseline_cost": 100.0, "deviation_cost": 80.0, "team_payoff_improvement": 20.0},
            {"seed": 1, "deviator_id": 1, "baseline_cost": 100.0, "deviation_cost": 110.0, "team_payoff_improvement": -10.0},
            {"seed": 2, "deviator_id": 0, "baseline_cost": 200.0, "deviation_cost": 190.0, "team_payoff_improvement": 10.0},
            {"seed": 2, "deviator_id": 1, "baseline_cost": 200.0, "deviation_cost": 150.0, "team_payoff_improvement": 50.0},
        ]
        summary = compute_unilateral_deviation_statistics(rows, resamples=200, seed=42)
        self.assertEqual(len(summary), 3)

        # Row 0: epsilon_hat overall
        overall = summary[0]
        self.assertEqual(overall["metric"], "restricted_empirical_unilateral_deviation_epsilon_hat")
        self.assertEqual(overall["analysis"], "restricted empirical unilateral-deviation analysis (nearest-time-only rule)")
        self.assertEqual(overall["deviator_id"], "max")
        self.assertAlmostEqual(overall["mean"], 20.0)
        self.assertAlmostEqual(overall["mean_baseline_cost"], 150.0)
        self.assertAlmostEqual(overall["relative_gain"], 20.0 / 150.0)
        self.assertEqual(overall["n_seeds"], 2)
        self.assertEqual(overall["tested_deviations"], 2)
        self.assertLessEqual(overall["ci95_low"], overall["mean"])
        self.assertGreaterEqual(overall["ci95_high"], overall["mean"])

        # Row 1: agent 0
        ag0 = summary[1]
        self.assertEqual(ag0["metric"], "agent_0_unilateral_deviation")
        self.assertEqual(ag0["deviator_id"], "0")
        self.assertAlmostEqual(ag0["mean"], 15.0)
        self.assertAlmostEqual(ag0["relative_gain"], 15.0 / 150.0)

        # Row 2: agent 1
        ag1 = summary[2]
        self.assertEqual(ag1["metric"], "agent_1_unilateral_deviation")
        self.assertEqual(ag1["deviator_id"], "1")
        self.assertAlmostEqual(ag1["mean"], 20.0)
        self.assertAlmostEqual(ag1["relative_gain"], 20.0 / 150.0)


if __name__ == "__main__":
    unittest.main()

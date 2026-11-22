from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ambulance_dispatch.config import ScenarioConfig
from tools.run_weight_sensitivity import run_weight_sensitivity, weight_sweep


class WeightSensitivityTests(unittest.TestCase):
    def test_axes_vary_one_weight_at_a_time_with_default_values_included(self) -> None:
        base = ScenarioConfig()
        sweep = weight_sweep(base)
        self.assertEqual(len(sweep), 9)
        for factor, levels in (("alpha", {0.5, 1.0, 2.0}), ("beta", {4.0, 8.0, 16.0}), ("gamma", {4.0, 8.0, 16.0})):
            entries = [(level, config.weights) for name, level, config in sweep if name == factor]
            self.assertEqual({level for level, _weights in entries}, levels)
            for level, weights in entries:
                self.assertEqual(weights.alpha, level if factor == "alpha" else base.weights.alpha)
                self.assertEqual(weights.beta, level if factor == "beta" else base.weights.beta)
                self.assertEqual(weights.gamma, level if factor == "gamma" else base.weights.gamma)
                self.assertEqual(weights.rho, base.weights.rho)

    def test_small_run_writes_paired_rows_and_complete_manifest(self) -> None:
        base = ScenarioConfig(n_ambulances=3, horizon_minutes=180.0, total_rate_per_hour=2.0)
        with tempfile.TemporaryDirectory() as temporary:
            output = run_weight_sensitivity(Path(temporary) / "run", base, [23], bootstrap_resamples=20)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            with (output / "raw_results.csv").open(encoding="utf-8", newline="") as stream:
                raw = list(csv.DictReader(stream))
            with (output / "b3_comparisons.csv").open(encoding="utf-8", newline="") as stream:
                comparisons = list(csv.DictReader(stream))
            self.assertEqual(len(raw), 9 * 4)
            self.assertEqual(len(comparisons), len(raw))
            self.assertEqual(manifest["completed_case_count"], 36)
            self.assertEqual(manifest["seed_list"], [23])
            self.assertEqual(manifest["communication_settings"]["regime"], "full")
            self.assertIn("src/ambulance_dispatch/simulator.py", manifest["source_sha256"])
            self.assertIn("tools/run_weight_sensitivity.py", manifest["source_sha256"])
            for row in comparisons:
                self.assertNotEqual(row["b3_cost_gap_absolute"], "")
                self.assertNotEqual(row["b3_service_rate_difference"], "")
            for row in raw:
                self.assertEqual(int(row["n_incidents"]), int(row["served"]) + int(row["expired"]))
                self.assertEqual(row["config_sha256"], hashlib.sha256(row["config_json"].encode()).hexdigest())

    def test_weight_sensitivity_refuses_final_run_on_dirty_tree(self) -> None:
        import unittest.mock
        base = ScenarioConfig(n_ambulances=3, horizon_minutes=60.0)
        with tempfile.TemporaryDirectory() as temporary:
            with unittest.mock.patch("tools.run_weight_sensitivity._git_status", return_value=("mock_rev", True)):
                with self.assertRaises(RuntimeError) as ctx:
                    run_weight_sensitivity(
                        Path(temporary) / "run",
                        base,
                        range(20),
                        allow_dirty=False,
                    )
                self.assertIn("dirty", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()

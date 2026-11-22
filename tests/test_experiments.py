from __future__ import annotations

import csv
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ambulance_dispatch.config import ScenarioConfig
from ambulance_dispatch.experiments import build_experiment_cases, run_experiment_suite


class ExperimentDesignTests(unittest.TestCase):
    def test_seven_families_have_paired_policies_and_seeds(self) -> None:
        base = ScenarioConfig(width=3, height=3, n_ambulances=3, horizon_minutes=60.0)
        cases = build_experiment_cases(base, [17, 18])
        self.assertEqual({case.experiment for case in cases}, {f"exp{i}_" + suffix for i, suffix in (
            (1, "ambulance_count"), (2, "total_demand"), (3, "demand_pattern"),
            (4, "communication"), (5, "demand_knowledge"), (6, "criticality_mix"),
            (7, "weight_tradeoff"),
        )})
        self.assertEqual({case.seed for case in cases}, {17, 18})
        exp4 = [case for case in cases if case.experiment == "exp4_communication"]
        self.assertEqual(len(exp4), 4 * 4 * 2)
        self.assertEqual({case.policy for case in exp4}, {"B1", "B2", "B3", "BID"})
        exp5_bid = [case for case in cases if case.experiment == "exp5_demand_knowledge" and case.policy == "BID"]
        self.assertEqual({case.oracle_demand for case in exp5_bid}, {False, True})
        with self.assertRaises(ValueError):
            build_experiment_cases(base, [1], {"exp8"})

    def test_small_real_suite_writes_raw_summary_and_plot_files(self) -> None:
        base = ScenarioConfig(width=3, height=3, n_ambulances=3, horizon_minutes=60.0, total_rate_per_hour=2.0)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            project = pathlib.Path(__file__).resolve().parents[1]
            out = run_experiment_suite(
                project,
                root / "results",
                base,
                [101],
                selected={"exp4"},
                bootstrap_resamples=100,
            )
            self.assertTrue((out / "manifest.json").exists())
            self.assertTrue((out / "raw_results.csv").exists())
            self.assertTrue((out / "b3_comparisons.csv").exists())
            self.assertTrue((out / "summary_metrics.csv").exists())
            self.assertTrue((out / "plots" / "results_contact_sheet.png").exists())
            self.assertTrue((out / "deviations" / "deviation_cases.csv").exists())
            self.assertTrue((out / "deviations" / "deviation_summary.csv").exists())
            with (out / "deviations" / "deviation_cases.csv").open(encoding="utf-8", newline="") as handle:
                deviations = list(csv.DictReader(handle))
            self.assertEqual(len(deviations), base.n_ambulances)
            with (out / "raw_results.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 16)
            self.assertTrue(all(row["seed"] == "101" for row in rows))
            with self.assertRaises(FileExistsError):
                run_experiment_suite(project, out, base, [101], selected={"exp4"})


if __name__ == "__main__":
    unittest.main()

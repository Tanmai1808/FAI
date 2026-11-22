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
        self.assertEqual({case.experiment for case in cases}, {
            "exp1_ambulance_count",
            "exp2_total_demand",
            "exp3_demand_pattern",
            "exp4_communication",
            "exp4b_communication_radius",
            "exp4c_communication_loss",
            "exp5_demand_knowledge",
            "exp5b_learning_shifting",
            "exp6_criticality_mix",
            "exp7_weight_tradeoff",
        })
        self.assertEqual({case.seed for case in cases}, {17, 18})
        for exp_id in ("exp1_ambulance_count", "exp2_total_demand", "exp6_criticality_mix"):
            exp_cases = [case for case in cases if case.experiment == exp_id]
            self.assertEqual({case.policy for case in exp_cases}, {"B1", "B2", "B2q", "B3", "BID"})
        for exp_id in ("exp3_demand_pattern", "exp4_communication", "exp5_demand_knowledge", "exp7_weight_tradeoff"):
            exp_cases = [case for case in cases if case.experiment == exp_id]
            self.assertEqual({case.policy for case in exp_cases}, {"B1", "B2", "B3", "BID"})
        for exp_id in ("exp4b_communication_radius", "exp4c_communication_loss", "exp5b_learning_shifting"):
            exp_cases = [case for case in cases if case.experiment == exp_id]
            self.assertEqual({case.policy for case in exp_cases}, {"BID"})
        exp4 = [case for case in cases if case.experiment == "exp4_communication"]
        self.assertEqual(len(exp4), 4 * 4 * 2)
        exp4b = [case for case in cases if case.experiment == "exp4b_communication_radius"]
        self.assertEqual(len(exp4b), 7 * 1 * 2)  # full, none, r=2,4,6,8,12
        exp4c = [case for case in cases if case.experiment == "exp4c_communication_loss"]
        self.assertEqual(len(exp4c), 8 * 1 * 2)  # full, none, p=0,0.1,0.25,0.5,0.75,1.0
        exp5b = [case for case in cases if case.experiment == "exp5b_learning_shifting"]
        self.assertEqual(len(exp5b), 2 * 1 * 2)  # learned, oracle
        exp5_bid = [case for case in cases if case.experiment == "exp5_demand_knowledge" and case.policy == "BID"]
        self.assertEqual({case.oracle_demand for case in exp5_bid}, {False, True})
        with self.assertRaises(ValueError):
            build_experiment_cases(base, [1], {"exp99"})

    def test_small_real_suite_writes_raw_summary_and_plot_files(self) -> None:
        base = ScenarioConfig(
            width=3,
            height=3,
            n_ambulances=3,
            horizon_minutes=60.0,
            learning_bin_minutes=30.0,
            total_rate_per_hour=5.0,
        )
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
            self.assertTrue((out / "incident_outcomes.csv.gz").exists())
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
            for field in (
                "response_cost",
                "external_coverage_cost",
                "home_demand_cost",
                "expiration_cost",
                "dispatch_cost",
                "total_cost",
                "median_response_minutes",
                "p90_response_minutes",
                "critical_service_rate",
                "duplicate_commitments",
                "duplicate_scene_arrivals",
                "duplicate_rate",
                "expired_rate",
                "messages_sent_bid",
                "messages_delivered_bid",
                "messages_dropped_bid",
                "messages_sent_status",
                "messages_delivered_status",
                "messages_dropped_status",
                "messages_sent_rate",
                "messages_delivered_rate",
                "messages_dropped_rate",
            ):
                self.assertTrue(all(field in row for row in rows), f"missing {field} in raw_results.csv")

            self.assertTrue((out / "learning_rmse_timeseries.csv").exists())
            with (out / "learning_rmse_timeseries.csv").open(encoding="utf-8", newline="") as rmse_handle:
                rmse_rows = list(csv.DictReader(rmse_handle))
            self.assertGreater(len(rmse_rows), 0)
            self.assertEqual(
                list(rmse_rows[0].keys()),
                ["experiment", "level", "policy", "seed", "time_minutes", "rmse"],
            )

            import gzip
            with gzip.open(out / "incident_outcomes.csv.gz", "rt", encoding="utf-8", newline="") as gz_handle:
                gz_rows = list(csv.DictReader(gz_handle))
            self.assertGreater(len(gz_rows), 0)
            expected_fields = [
                "seed",
                "policy",
                "experiment",
                "level",
                "incident_id",
                "criticality",
                "arrival_time",
                "deadline",
                "response_time",
                "responder_count",
                "outcome",
            ]
            self.assertEqual(list(gz_rows[0].keys()), expected_fields)
            self.assertTrue(all(r["outcome"] in ("served", "expired") for r in gz_rows))
            with self.assertRaises(FileExistsError):
                run_experiment_suite(project, out, base, [101], selected={"exp4"})

    def test_rng_independence_across_communication_parameters(self) -> None:
        """Changing packet_loss_probability or radius does NOT change emergency arrivals, criticalities, or positions."""
        from ambulance_dispatch.simulator import RunSettings, Simulator

        config = ScenarioConfig(width=3, height=3, n_ambulances=3, horizon_minutes=300.0, total_rate_per_hour=5.0)
        seed = 42

        sim1 = Simulator(
            config,
            RunSettings(policy="BID", communication="full", communication_radius_minutes=12.0, packet_loss_probability=0.0, seed=seed),
        )
        sim2 = Simulator(
            config,
            RunSettings(policy="BID", communication="radius-limited", communication_radius_minutes=2.0, packet_loss_probability=0.0, seed=seed),
        )
        sim3 = Simulator(
            config,
            RunSettings(policy="BID", communication="lossy", communication_radius_minutes=12.0, packet_loss_probability=0.75, seed=seed),
        )

        # 1. Compare initial ambulance positions
        pos1 = [a.node for a in sim1.ambulances]
        pos2 = [a.node for a in sim2.ambulances]
        pos3 = [a.node for a in sim3.ambulances]
        self.assertEqual(pos1, pos2)
        self.assertEqual(pos1, pos3)

        # 2. Compare incident tape (arrivals, zones, criticalities)
        incidents1 = [(inc.incident_id, inc.arrival_minute, inc.zone, inc.criticality) for inc in sim1.tape.incidents]
        incidents2 = [(inc.incident_id, inc.arrival_minute, inc.zone, inc.criticality) for inc in sim2.tape.incidents]
        incidents3 = [(inc.incident_id, inc.arrival_minute, inc.zone, inc.criticality) for inc in sim3.tape.incidents]
        self.assertGreater(len(incidents1), 0)
        self.assertEqual(incidents1, incidents2)
        self.assertEqual(incidents1, incidents3)

    def test_bid_lossy_p1_equals_bid_none(self) -> None:
        """BID lossy p=1 gives identical service rate, duplicate rate, and total cost as BID none."""
        from ambulance_dispatch.simulator import RunSettings, simulate

        config = ScenarioConfig(horizon_minutes=600.0)
        for seed in (1000, 1001, 7, 42):
            res_none = simulate(config, RunSettings(policy="BID", communication="none", seed=seed))
            res_lossy = simulate(
                config,
                RunSettings(policy="BID", communication="lossy", packet_loss_probability=1.0, seed=seed),
            )
            self.assertEqual(
                res_none.service_rate,
                res_lossy.service_rate,
                msg=f"Service rate mismatch for seed {seed}",
            )
            self.assertEqual(
                res_none.duplicate_rate,
                res_lossy.duplicate_rate,
                msg=f"Duplicate rate mismatch for seed {seed}",
            )
            self.assertAlmostEqual(
                res_none.total_cost,
                res_lossy.total_cost,
                places=9,
                msg=f"Total cost mismatch for seed {seed}",
            )

    def test_demand_learning_shifting_boundary_convention(self) -> None:
        """At midpoint shift (e.g. t=3000), interval estimate compares with OLD rates, later with NEW rates."""
        from ambulance_dispatch.simulator import RunSettings, Simulator

        config = ScenarioConfig(
            width=3,
            height=3,
            n_ambulances=3,
            horizon_minutes=6000.0,
            learning_bin_minutes=60.0,
            demand_pattern="shifting",
        )
        sim = Simulator(config, RunSettings(policy="BID", communication="full", seed=100))
        sim.run()

        ts = sim.learning_rmse_timeseries()
        self.assertEqual(len(ts), 99)  # 60, 120, ..., 5940 (boundaries strictly before horizon 6000)
        timestamps = [item["time_minutes"] for item in ts]
        expected_timestamps = [float(b) for b in range(60, 6000, 60)]
        self.assertEqual(timestamps, expected_timestamps)

        # Midpoint is at t=3000.0 (index 49: 50th boundary)
        idx_3000 = timestamps.index(3000.0)
        self.assertEqual(idx_3000, 49)

        # At t=3000, sim._true_rates(3000 - 1e-9) should equal the pre-shift rates
        pre_shift_rates = sim.tape.rate_schedule[0].rates_per_hour
        post_shift_rates = sim.tape.rate_schedule[1].rates_per_hour
        self.assertNotEqual(pre_shift_rates, post_shift_rates)
        self.assertEqual(sim._true_rates(3000.0 - 1e-9), pre_shift_rates)
        self.assertEqual(sim._true_rates(3060.0 - 1e-9), post_shift_rates)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from report.build_report_assets import (
    write_communication_table,
    write_deviation_table,
    write_message_table,
    write_policy_comparison_table,
    write_proposal_results_table,
    write_weight_sensitivity_table,
)
from report.plot_results import (
    chart_communication_sweeps,
    chart_rmse_timeseries,
    chart_stacked_cost,
)


class ReportAssetsTests(unittest.TestCase):
    def test_proposal_table_caption_matches_its_reported_columns(self) -> None:
        experiment_levels = {
            "exp1_ambulance_count": "n=3",
            "exp2_total_demand": "low:2.5/h",
            "exp3_demand_pattern": "uniform",
            "exp4_communication": "full",
            "exp5_demand_knowledge": "learned",
            "exp6_criticality_mix": "low-heavy",
            "exp7_weight_tradeoff": "coverage-light",
        }
        summary = []
        for experiment, level in experiment_levels.items():
            for policy in ("B1", "B2", "B3", "BID"):
                for metric in ("service_rate", "b3_cost_gap_relative"):
                    summary.append(
                        {
                            "experiment": experiment,
                            "level": level,
                            "policy": policy,
                            "metric": metric,
                            "mean": "0.8",
                            "ci95_low": "0.7",
                            "ci95_high": "0.9",
                        }
                    )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "proposal_results_table.tex"
            write_proposal_results_table(summary, output)
            rendered = output.read_text(encoding="utf-8")

        self.assertIn("Service and relative cost gap show mean", rendered)
        self.assertNotIn("Response means", rendered)

    def test_table_contains_csv_derived_joint_outcomes(self) -> None:
        levels = ("full", "radius-limited", "lossy", "none")
        metrics = {
            "service_rate": 0.825,
            "mean_response_minutes": 16.6,
            "mean_coverage": 0.2205,
            "utilization": 0.878,
            "messages_per_incident": 0.0,
        }
        summary = [
            {
                "experiment": "exp4_communication",
                "level": level,
                "policy": "BID",
                "metric": metric,
                "mean": str(value),
                "n": "4",
            }
            for level in levels
            for metric, value in metrics.items()
        ]
        derived = [
            {
                "experiment": "exp4_communication",
                "level": level,
                "policy": "BID",
                "metric": metric,
                "mean": str(value),
            }
            for level in levels
            for metric, value in (
                ("duplicate_dispatch_rate", 0.411),
                ("missed_dispatch_rate", 0.175),
            )
        ]

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "communication_table.tex"
            write_communication_table(summary, derived, output)
            rendered = output.read_text(encoding="utf-8")

        self.assertIn("Service (\\%) & Response (min) & Coverage (\\%)", rendered)
        self.assertIn("means across 4 paired seeds", rendered)
        self.assertIn("none & 82.5 & 16.6 & 22.1 & 87.8 & 0.0 & 41.1 & 17.5", rendered)

    def test_weight_table_is_proper_float_for_ordered_captions(self) -> None:
        summary = []
        for factor in ("alpha", "beta", "gamma"):
            for value in ("0.5", "1", "2"):
                level = f"{factor}={value}"
                for metric, mean in (("service_rate", "0.998"), ("b3_cost_gap_relative", "0.005")):
                    summary.append(
                        {
                            "experiment": "exp8_weight_sensitivity",
                            "level": level,
                            "weight_factor": factor,
                            "policy": "BID",
                            "metric": metric,
                            "mean": mean,
                            "ci95_low": "0.004",
                            "ci95_high": "0.006",
                        }
                    )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "weight_sensitivity_table.tex"
            write_weight_sensitivity_table(summary, output)
            rendered = output.read_text(encoding="utf-8")

        self.assertIn(r"\begin{table}", rendered)
        self.assertIn(r"\caption{", rendered)
        self.assertNotIn(r"\captionof{table}", rendered)

    def test_policy_comparison_table_contains_all_five_policies(self) -> None:
        raw = []
        for pol in ("B1", "B2", "B2q", "B3", "BID"):
            raw.append(
                {
                    "experiment": "exp1_ambulance_count",
                    "level": "n=5",
                    "seed": "101",
                    "demand_condition": "stationary",
                    "policy": pol,
                    "total_cost": "150.0",
                    "mean_response_minutes": "8.5",
                    "median_response_minutes": "7.2",
                    "p90_response_minutes": "14.1",
                    "critical_mean_response_minutes": "6.0",
                    "service_rate": "0.98",
                    "expired_rate": "0.02",
                }
            )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "policy_comparison_table.tex"
            write_policy_comparison_table(raw, output)
            rendered = output.read_text(encoding="utf-8")

        for pol in ("B1", "B2", "B2q", "B3", "BID"):
            self.assertIn(pol, rendered)
        self.assertIn("Total Cost", rendered)
        self.assertIn("Crit. Resp.", rendered)
        self.assertIn("Service (\\%)", rendered)
        self.assertIn("Expired (\\%)", rendered)

    def test_deviation_table_renders_overall_and_per_agent(self) -> None:
        rows = [
            {
                "deviator_id": "max",
                "mean": "12.34",
                "ci95_low": "4.56",
                "ci95_high": "20.12",
                "relative_gain": "0.0075",
            },
            {
                "deviator_id": "0",
                "mean": "5.67",
                "ci95_low": "1.23",
                "ci95_high": "10.45",
                "relative_gain": "0.0034",
            },
        ]

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "deviation_table.tex"
            write_deviation_table(rows, output)
            rendered = output.read_text(encoding="utf-8")

        self.assertIn(r"Overall ($\widehat{\epsilon}$)", rendered)
        self.assertIn("Agent 0", rendered)
        self.assertIn("12.34", rendered)
        self.assertIn("[4.56, 20.12]", rendered)
        self.assertIn("0.75\\%", rendered)

    def test_message_table_renders_message_kinds(self) -> None:
        raw = []
        for reg in ("full", "radius-limited", "lossy", "none"):
            raw.append(
                {
                    "experiment": "exp4_communication",
                    "level": reg,
                    "communication": reg,
                    "policy": "BID",
                    "messages_sent_bid": "120",
                    "messages_delivered_bid": "110",
                    "messages_dropped_bid": "10",
                    "messages_sent_status": "50",
                    "messages_delivered_status": "45",
                    "messages_dropped_status": "5",
                    "messages_sent_rate": "30",
                    "messages_delivered_rate": "28",
                    "messages_dropped_rate": "2",
                    "messages_sent": "200",
                    "messages_delivered": "183",
                }
            )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "message_table.tex"
            write_message_table(raw, output)
            rendered = output.read_text(encoding="utf-8")

        self.assertIn("Bid Messages", rendered)
        self.assertIn("Status Messages", rendered)
        self.assertIn("Rate Messages", rendered)
        self.assertIn("Total Messages", rendered)
        for reg in ("full", "radius-limited", "lossy", "none"):
            self.assertIn(reg, rendered)

    def test_stacked_cost_chart_creates_png(self) -> None:
        raw = []
        for lvl in ("n=7", "n=10"):
            for pol in ("B1", "B2", "B3", "BID"):
                raw.append(
                    {
                        "experiment": "exp1_ambulance_count",
                        "level": lvl,
                        "policy": pol,
                        "response_cost": "45.0",
                        "external_coverage_cost": "30.0",
                        "home_demand_cost": "25.0",
                        "expiration_cost": "10.0",
                    }
                )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "cost_breakdown_stacked_n7_n10.png"
            success = chart_stacked_cost(raw, output)
            self.assertTrue(success)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1000)

    def test_communication_sweeps_create_pngs(self) -> None:
        raw = []
        for r_lvl in ("r=2", "r=4", "r=6", "r=8", "r=12"):
            raw.append(
                {
                    "experiment": "exp4b_radius_sweep",
                    "level": r_lvl,
                    "policy": "BID",
                    "duplicate_rate": "0.15",
                    "expired_rate": "0.05",
                }
            )
        for p_lvl in ("p=0", "p=0.1", "p=0.25", "p=0.5", "p=0.75", "p=1.0"):
            raw.append(
                {
                    "experiment": "exp4c_loss_sweep",
                    "level": p_lvl,
                    "policy": "BID",
                    "duplicate_rate": "0.20",
                    "expired_rate": "0.08",
                }
            )

        with tempfile.TemporaryDirectory() as temporary_dir:
            outputs = chart_communication_sweeps(raw, Path(temporary_dir))
            self.assertEqual(len(outputs), 2)
            for out in outputs:
                self.assertTrue(out.exists())
                self.assertGreater(out.stat().st_size, 1000)

    def test_rmse_timeseries_chart_creates_png(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            csv_path = Path(temporary_dir) / "learning_rmse_timeseries.csv"
            csv_path.write_text(
                "experiment,level,policy,seed,time_minutes,rmse\n"
                "exp5b_shifting_demand,learned,BID,101,0.0,0.85\n"
                "exp5b_shifting_demand,learned,BID,101,1500.0,0.22\n"
                "exp5b_shifting_demand,learned,BID,101,3000.0,0.48\n"
                "exp5b_shifting_demand,learned,BID,101,4500.0,0.18\n"
                "exp5b_shifting_demand,learned,BID,101,6000.0,0.15\n",
                encoding="utf-8",
            )
            out_png = Path(temporary_dir) / "exp5b_learning_rmse_timeseries.png"
            success = chart_rmse_timeseries(csv_path, out_png)
            self.assertTrue(success)
            self.assertTrue(out_png.exists())
            self.assertGreater(out_png.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()

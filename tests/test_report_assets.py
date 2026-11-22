from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from report.build_report_assets import (
    write_communication_table,
    write_proposal_results_table,
    write_weight_sensitivity_table,
)


class CommunicationTableTests(unittest.TestCase):
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

    def test_weight_table_is_nonfloating_to_preserve_caption_order(self) -> None:
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

        self.assertIn(r"\captionof{table}", rendered)
        self.assertNotIn(r"\begin{table}", rendered)


if __name__ == "__main__":
    unittest.main()

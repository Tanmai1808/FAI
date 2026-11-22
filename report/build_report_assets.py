"""Generate report tables and numeric macros directly from a completed run."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from ambulance_dispatch.metrics import bootstrap_mean_interval, summarize_by  # noqa: E402


def latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def num(value: str | None) -> float | None:
    if value is None or value in {"", "NA", "None", "null"}:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def family_order() -> list[str]:
    return [
        "exp1_ambulance_count",
        "exp2_total_demand",
        "exp3_demand_pattern",
        "exp4_communication",
        "exp5_demand_knowledge",
        "exp6_criticality_mix",
        "exp7_weight_tradeoff",
    ]


def family_short(name: str) -> str:
    return {
        "exp1_ambulance_count": "E1 Fleet",
        "exp2_total_demand": "E2 Demand",
        "exp3_demand_pattern": "E3 Pattern",
        "exp4_communication": "E4 Communication",
        "exp5_demand_knowledge": "E5 Knowledge",
        "exp6_criticality_mix": "E6 Criticality",
        "exp7_weight_tradeoff": "E7 Weights",
    }.get(name, name)


def level_order(experiment: str, level: str) -> tuple[int, str]:
    """Keep each one-factor sweep in its declared, interpretable order."""
    orders = {
        "exp1_ambulance_count": {"n=3": 0, "n=5": 1, "n=7": 2, "n=10": 3},
        "exp2_total_demand": {"low:2.5/h": 0, "medium:5/h": 1, "high:10/h": 2},
        "exp3_demand_pattern": {"uniform": 0, "hotspots": 1, "shifting": 2},
        "exp4_communication": {"full": 0, "radius-limited": 1, "lossy": 2, "none": 3},
        "exp5_demand_knowledge": {"learned": 0, "oracle": 1},
        "exp6_criticality_mix": {"low-heavy": 0, "balanced": 1, "high-heavy": 2},
        "exp7_weight_tradeoff": {"coverage-light": 0, "balanced": 1, "coverage-heavy": 2},
    }
    return orders.get(experiment, {}).get(level, 999), level


def find_summary(
    rows: list[dict[str, str]],
    experiment: str,
    level: str,
    policy: str,
    metric: str,
) -> dict[str, str] | None:
    for row in rows:
        if (
            row["experiment"] == experiment
            and row["level"] == level
            and row["policy"] == policy
            and row["metric"] == metric
        ):
            return row
    return None


def interval_cell(row: dict[str, str] | None, percent: bool = False) -> str:
    if row is None:
        return "--"
    mean, low, high = (num(row.get(key)) for key in ("mean", "ci95_low", "ci95_high"))
    if mean is None:
        return "--"
    scale = 100.0 if percent else 1.0
    suffix = r"\%" if percent else ""
    return f"{mean*scale:.1f}{suffix} [{low*scale:.1f},{high*scale:.1f}]" if low is not None and high is not None else f"{mean*scale:.1f}{suffix}"


def derive_rate_summaries(raw: list[dict[str, str]], resamples: int = 1000) -> list[dict[str, Any]]:
    derived = []
    for row in raw:
        n = int(row.get("n_incidents", 0))
        exp_rate = float(row.get("expired_rate", int(row.get("expired", 0)) / n if n else 0.0))
        dup_rate = float(row.get("duplicate_rate", int(row.get("duplicate_incidents", 0)) / n if n else 0.0))
        item = {
            **row,
            "duplicate_dispatch_rate": dup_rate,
            "expired_dispatch_rate": exp_rate,
            "missed_dispatch_rate": exp_rate,
        }
        derived.append(item)
    group_keys = ("experiment", "level", "policy", "communication", "demand_condition")
    summaries = []
    for metric in ("duplicate_dispatch_rate", "expired_dispatch_rate", "missed_dispatch_rate"):
        summaries.extend(summarize_by(derived, group_keys, metric, resamples=resamples, seed=491))
    return summaries


def write_service_table(summary: list[dict[str, str]], target: Path) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering\small",
        r"\caption{Service-before-deadline rate by experiment level. Cells show mean percentage and 95\% bootstrap interval across paired scenario seeds.}",
        r"\label{tab:service}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Experiment & Level & B1 & B2 & B3 & BID \\",
        r"\midrule",
    ]
    for experiment in family_order():
        levels = sorted(
            {row["level"] for row in summary if row["experiment"] == experiment},
            key=lambda level: level_order(experiment, level),
        )
        for level in levels:
            cells = []
            for policy in ("B1", "B2", "B3", "BID"):
                row = find_summary(summary, experiment, level, policy, "service_rate")
                cells.append(interval_cell(row, percent=True))
            lines.append(f"{family_short(experiment)} & {latex_escape(level)} & " + " & ".join(cells) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"}", r"\end{table*}"])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_gap_table(summary: list[dict[str, str]], target: Path) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering\small",
        r"\caption{Signed relative total-cost gap versus heuristic B3. Positive values indicate higher policy cost; negative values indicate that the policy beat B3 on those paired seeds. Cells show percent mean and 95\% bootstrap interval.}",
        r"\label{tab:cost-gap}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Experiment & Level & B1 & B2 & BID \\",
        r"\midrule",
    ]
    for experiment in family_order():
        levels = sorted(
            {row["level"] for row in summary if row["experiment"] == experiment},
            key=lambda level: level_order(experiment, level),
        )
        for level in levels:
            cells = []
            for policy in ("B1", "B2", "BID"):
                row = find_summary(summary, experiment, level, policy, "b3_cost_gap_relative")
                cells.append(interval_cell(row, percent=True))
            lines.append(f"{family_short(experiment)} & {latex_escape(level)} & " + " & ".join(cells) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"}", r"\end{table*}"])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_communication_table(
    summary: list[dict[str, str]], derived: list[dict[str, str]], target: Path
) -> None:
    """Write the communication-sweep BID means from retained summary rows."""
    levels = ("full", "radius-limited", "lossy", "none")
    summary_metrics = (
        ("service_rate", 100.0),
        ("mean_response_minutes", 1.0),
        ("mean_coverage", 100.0),
        ("utilization", 100.0),
        ("messages_per_incident", 1.0),
    )
    derived_metrics = ("duplicate_dispatch_rate", "expired_dispatch_rate")
    values: dict[tuple[str, str], float | None] = {}
    seed_counts: set[int] = set()
    for level in levels:
        for metric, _scale in summary_metrics:
            row = find_summary(summary, "exp4_communication", level, "BID", metric)
            values[(level, metric)] = num(row.get("mean")) if row else None
            if row and row.get("n"):
                seed_counts.add(int(row["n"]))
        for metric in derived_metrics:
            search_metrics = (metric, "missed_dispatch_rate") if metric == "expired_dispatch_rate" else (metric,)
            row = next(
                (
                    row for row in derived
                    if row["experiment"] == "exp4_communication"
                    and row["level"] == level
                    and row["policy"] == "BID"
                    and row["metric"] in search_metrics
                ),
                None,
            )
            values[(level, metric)] = num(row["mean"]) if row else None
    missing = [key for key, value in values.items() if value is None]
    if missing:
        # If exp4_communication not present in summary, write a stub
        lines = [
            r"\begin{center}",
            r"\scriptsize",
            r"\captionof{table}{BID communication outcomes.}",
            r"\label{tab:communication-rates}",
            r"\begin{tabular}{lrrrrrrr}",
            r"\toprule",
            r"Regime & Service (\%) & Response (min) & Coverage (\%) & Util. (\%) & Msg./call & Duplicate (\%) & Expired (\%) \\",
            r"\midrule",
            r"none & -- & -- & -- & -- & -- & -- & -- \\",
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
        ]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    seed_count = seed_counts.pop() if seed_counts else 0

    lines = [
        r"\begin{center}",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{2.5pt}",
        rf"\captionof{{table}}{{BID communication outcomes (means across {seed_count} paired seeds). Response is conditional on service; message count is directed attempts per incident.}}",
        r"\label{tab:communication-rates}",
        r"\begin{tabular}{lrrrrrrr}",
        r"\toprule",
        r"Regime & Service (\%) & Response (min) & Coverage (\%) & Util. (\%) & Msg./call & Duplicate (\%) & Expired (\%) \\",
        r"\midrule",
    ]
    for level in levels:
        cells = []
        for metric, scale in summary_metrics:
            value = values[(level, metric)]
            cells.append(f"{value * scale:.1f}" if value is not None else "--")
        for metric in derived_metrics:
            value = values[(level, metric)]
            cells.append(f"{value * 100:.1f}" if value is not None else "--")
        lines.append(" & ".join([latex_escape(level), *cells]) + " " + r"\\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{center}"])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_proposal_results_table(summary: list[dict[str, str]], target: Path) -> None:
    """Compact all seven proposal sweeps around BID service and signed cost gap."""
    lines = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\caption{Proposal experiment results. Service and relative cost gap show mean [95\% paired-seed bootstrap interval]. The relative cost gap is signed versus heuristic B3.}",
        r"\label{tab:proposal-results}",
        r"\begin{tabular}{p{1.47in}p{1.47in}p{1.47in}p{1.47in}}",
        r"\toprule",
        r"Experiment level & BID service (\%) & B3 service (\%) & BID cost gap to B3 (\%) \\",
        r"\midrule",
    ]
    for experiment in family_order():
        levels = sorted(
            {row["level"] for row in summary if row["experiment"] == experiment},
            key=lambda level: level_order(experiment, level),
        )
        for level in levels:
            bid_service = find_summary(summary, experiment, level, "BID", "service_rate")
            b3_service = find_summary(summary, experiment, level, "B3", "service_rate")
            bid_gap = find_summary(summary, experiment, level, "BID", "b3_cost_gap_relative")
            cells = (
                f"{family_short(experiment)}, {latex_escape(level)}",
                interval_cell(bid_service, percent=True),
                interval_cell(b3_service, percent=True),
                interval_cell(bid_gap, percent=True),
            )
            lines.append(" & ".join(cells) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_weight_sensitivity_table(summary: list[dict[str, str]], target: Path) -> None:
    """Write the independently varied alpha, beta, and gamma outcomes in source order."""
    lines = [
        r"\begin{center}",
        r"\scriptsize",
        r"\captionof{table}{Independent one-factor weight sensitivity. Other weights remain at the default while each listed coefficient varies. Cells show mean [95\% paired-seed bootstrap interval].}",
        r"\label{tab:weight-sensitivity}",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Weight & Level & BID service (\%) & BID signed gap to B3 (\%) \\",
        r"\midrule",
    ]
    for factor in ("alpha", "beta", "gamma"):
        levels = sorted(
            {row["level"] for row in summary if row["experiment"] == "exp8_weight_sensitivity" and row.get("weight_factor") == factor},
            key=lambda level: float(level.split("=", 1)[1]),
        )
        for level in levels:
            service = next((row for row in summary if row["experiment"] == "exp8_weight_sensitivity" and row["level"] == level and row["policy"] == "BID" and row["metric"] == "service_rate"), None)
            gap = next((row for row in summary if row["experiment"] == "exp8_weight_sensitivity" and row["level"] == level and row["policy"] == "BID" and row["metric"] == "b3_cost_gap_relative"), None)
            factor_value = level.split("=", 1)[1]
            lines.append(" & ".join((factor, factor_value, interval_cell(service, percent=True), interval_cell(gap, percent=True))) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{center}"])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_policy_comparison_table(raw: list[dict[str, str]], target: Path) -> None:
    """Five-policy comparison table (B1, B2, B2q, B3, BID) with bootstrap CIs."""
    b2q_families = [
        ("exp1_ambulance_count", "Exp 1: Fleet Size"),
        ("exp2_total_demand", "Exp 2: Total Demand"),
        ("exp6_criticality_mix", "Exp 6: Criticality Mix"),
    ]
    policies = ("B1", "B2", "B2q", "B3", "BID")
    metrics = (
        ("total_cost", False, 1.0),
        ("mean_response_minutes", False, 1.0),
        ("median_response_minutes", False, 1.0),
        ("p90_response_minutes", False, 1.0),
        ("critical_mean_response_minutes", False, 1.0),
        ("service_rate", True, 100.0),
        ("expired_rate", True, 100.0),
    )

    lines = [
        r"\begin{table*}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\caption{Five-policy comparison across benchmark configurations where B2q was evaluated. Cells show mean [95\% bootstrap CI] across matched scenario seeds.}",
        r"\label{tab:policy-comparison}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrrrrr}",
        r"\toprule",
        r"Experiment & Policy & Total Cost & Mean Resp. (min) & Median (min) & P90 (min) & Crit. Resp. (min) & Service (\%) & Expired (\%) \\",
        r"\midrule",
    ]

    has_data = False
    for fam_id, fam_label in b2q_families:
        fam_rows = [r for r in raw if r.get("experiment") == fam_id]
        if not fam_rows:
            continue
        has_data = True
        for pol in policies:
            pol_rows = [r for r in fam_rows if r.get("policy") == pol]
            if not pol_rows:
                continue
            cells = []
            for col, is_pct, scale in metrics:
                vals = [float(r[col]) for r in pol_rows if r.get(col) not in (None, "", "NA")]
                if vals:
                    mean_val, low_val, high_val, _ = bootstrap_mean_interval(vals, resamples=1000)
                    pct_str = r"\%" if is_pct else ""
                    cells.append(f"{mean_val*scale:.1f}{pct_str} [{low_val*scale:.1f},{high_val*scale:.1f}]")
                else:
                    cells.append("--")
            lines.append(f"{fam_label} & {pol} & " + " & ".join(cells) + r" \\")
        lines.append(r"\midrule")

    # Pooled Benchmark Section
    valid_fams = {f[0] for f in b2q_families}
    pooled_rows = [r for r in raw if r.get("experiment") in valid_fams and r.get("policy") in policies]
    if not pooled_rows:
        pooled_rows = [r for r in raw if r.get("policy") in policies]

    if pooled_rows:
        has_data = True
        for pol in policies:
            pol_rows = [r for r in pooled_rows if r.get("policy") == pol]
            if not pol_rows:
                continue
            cells = []
            for col, is_pct, scale in metrics:
                vals = [float(r[col]) for r in pol_rows if r.get(col) not in (None, "", "NA")]
                if vals:
                    mean_val, low_val, high_val, _ = bootstrap_mean_interval(vals, resamples=1000)
                    pct_str = r"\%" if is_pct else ""
                    cells.append(f"{mean_val*scale:.1f}{pct_str} [{low_val*scale:.1f},{high_val*scale:.1f}]")
                else:
                    cells.append("--")
            lines.append(f"\\textbf{{Pooled Benchmark}} & \\textbf{{{pol}}} & " + " & ".join(cells) + r" \\")

    if not has_data:
        lines.append(r"No data & -- & -- & -- & -- & -- & -- & -- & -- \\")

    lines.extend([r"\bottomrule", r"\end{tabular}", r"}", r"\end{table*}"])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_deviation_table(deviation_rows: list[dict[str, str]], target: Path) -> None:
    """Write corrected unilateral deviation results table."""
    lines = [
        r"\begin{table}[t]",
        r"\centering\small",
        r"\caption{Restricted empirical unilateral-deviation analysis (nearest-time-only selfish deviation). $\widehat{\epsilon}$ denotes the maximum empirical mean payoff improvement across all agents. Cells report mean payoff gain ($\bar{\Delta}_i$) with 95\% paired-seed bootstrap interval and relative gain versus mean baseline cost.}",
        r"\label{tab:deviation}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Agent / Statistic & Mean Gain ($\bar{\Delta}$) & 95\% Bootstrap Interval & Relative Gain (\%) \\",
        r"\midrule",
    ]
    if not deviation_rows:
        lines.append(r"Overall ($\widehat{\epsilon}$) & -- & -- & -- \\")
    else:
        for row in deviation_rows:
            dev_id = row.get("deviator_id", "")
            if dev_id == "max" or row.get("metric", "").startswith("per_seed_max") or "epsilon_hat" in row.get("metric", ""):
                label = r"Overall ($\widehat{\epsilon}$)"
            else:
                label = f"Agent {dev_id}"
            mean_val = num(row.get("mean"))
            low_val = num(row.get("ci95_low"))
            high_val = num(row.get("ci95_high"))
            rel_val = num(row.get("relative_gain"))

            mean_str = f"{mean_val:.2f}" if mean_val is not None else "--"
            ci_str = f"[{low_val:.2f}, {high_val:.2f}]" if low_val is not None and high_val is not None else "--"
            rel_str = f"{rel_val * 100:.2f}\\%" if rel_val is not None else "--"

            lines.append(f"{label} & {mean_str} & {ci_str} & {rel_str} \\\\")
            if dev_id == "max":
                lines.append(r"\midrule")

    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_message_table(raw: list[dict[str, str]], target: Path) -> None:
    """Write message sent, delivered, and dropped breakdown table by communication regime."""
    regimes = ("full", "radius-limited", "lossy", "none")
    lines = [
        r"\begin{table}[t]",
        r"\centering\scriptsize",
        r"\setlength{\tabcolsep}{2.5pt}",
        r"\caption{Message transmission by communication regime and message kind under BID policy. Cells show mean count per scenario across paired seeds.}",
        r"\label{tab:messages}",
        r"\begin{tabular}{lrrrrrrrrrrrr}",
        r"\toprule",
        r"& \multicolumn{3}{c}{Bid Messages} & \multicolumn{3}{c}{Status Messages} & \multicolumn{3}{c}{Rate Messages} & \multicolumn{3}{c}{Total Messages} \\",
        r"\cmidrule(lr){2-4} \cmidrule(lr){5-7} \cmidrule(lr){8-10} \cmidrule(lr){11-13}",
        r"Regime & Sent & Deliv. & Drop & Sent & Deliv. & Drop & Sent & Deliv. & Drop & Sent & Deliv. & Drop \\",
        r"\midrule",
    ]

    bid_rows = [r for r in raw if r.get("experiment") == "exp4_communication" and r.get("policy") == "BID"]
    for reg in regimes:
        reg_rows = [r for r in bid_rows if r.get("level") == reg or r.get("communication") == reg]
        if not reg_rows:
            lines.append(f"{latex_escape(reg)} & -- & -- & -- & -- & -- & -- & -- & -- & -- & -- & -- & -- \\\\")
            continue

        def _mean_col(col_name: str) -> float:
            vals = [float(r[col_name]) for r in reg_rows if r.get(col_name) not in (None, "", "NA")]
            return sum(vals) / len(vals) if vals else 0.0

        b_s = _mean_col("messages_sent_bid")
        b_d = _mean_col("messages_delivered_bid")
        b_dr = _mean_col("messages_dropped_bid")

        s_s = _mean_col("messages_sent_status")
        s_d = _mean_col("messages_delivered_status")
        s_dr = _mean_col("messages_dropped_status")

        r_s = _mean_col("messages_sent_rate")
        r_d = _mean_col("messages_delivered_rate")
        r_dr = _mean_col("messages_dropped_rate")

        t_s = _mean_col("messages_sent")
        t_d = _mean_col("messages_delivered")
        t_dr = t_s - t_d

        cells = [
            f"{b_s:.0f}", f"{b_d:.0f}", f"{b_dr:.0f}",
            f"{s_s:.0f}", f"{s_d:.0f}", f"{s_dr:.0f}",
            f"{r_s:.0f}", f"{r_d:.0f}", f"{r_dr:.0f}",
            f"{t_s:.0f}", f"{t_d:.0f}", f"{t_dr:.0f}",
        ]
        lines.append(f"{latex_escape(reg)} & " + " & ".join(cells) + r" \\")

    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def macro(name: str, value: str) -> str:
    return f"\\newcommand{{\\{name}}}{{{value}}}"


def write_macros(
    summary: list[dict[str, str]],
    raw: list[dict[str, str]],
    deviation_rows: list[dict[str, str]],
    manifest: dict[str, Any],
    weight_manifest: dict[str, Any],
    target: Path,
) -> None:
    macros = [
        "% Generated by build_report_assets.py from raw_results.csv and summary_metrics.csv.",
        macro("NScenarioSeeds", str(len(manifest.get("seed_list", [])))),
        macro("NPolicyRuns", str(manifest.get("completed_case_count", 0))),
        macro("NWeightRuns", str(weight_manifest.get("completed_case_count", 0))),
    ]
    unique_scenarios = {}
    for row in raw:
        key = (row.get("experiment"), row.get("level"), row.get("seed"), row.get("demand_condition"))
        unique_scenarios[key] = int(row.get("n_incidents", 0))
    macros.append(macro("NMatchedScenarioGroups", str(len(unique_scenarios))))
    average_incidents = sum(unique_scenarios.values()) / len(unique_scenarios) if unique_scenarios else 0.0
    macros.append(macro("MeanIncidentsPerScenario", f"{average_incidents:.1f}"))

    def summary_value(experiment: str, level: str, policy: str, metric: str) -> float | None:
        row = find_summary(summary, experiment, level, policy, metric)
        return num(row.get("mean")) if row else None

    full_service = summary_value("exp4_communication", "full", "BID", "service_rate")
    none_service = summary_value("exp4_communication", "none", "BID", "service_rate")
    if full_service is not None:
        macros.append(macro("FullBIDServicePercent", f"{full_service * 100:.1f}"))
    if none_service is not None:
        macros.append(macro("NoneBIDServicePercent", f"{none_service * 100:.1f}"))
    if full_service is not None and none_service is not None:
        macros.append(macro("FullNoneServiceDifferencePP", f"{(full_service-none_service)*100:.1f}"))

    for level, name in (("learned", "Learned"), ("oracle", "Oracle")):
        cost_gap = summary_value("exp5_demand_knowledge", level, "BID", "b3_cost_gap_relative")
        if cost_gap is not None:
            macros.append(macro(f"{name}BIDCostGapPercent", f"{100*cost_gap:.1f}"))
        service = summary_value("exp5_demand_knowledge", level, "BID", "service_rate")
        if service is not None:
            macros.append(macro(f"{name}BIDServicePercent", f"{100*service:.1f}"))

    if deviation_rows:
        row = deviation_rows[0]
        value = num(row.get("mean"))
        ci_low = num(row.get("ci95_low"))
        ci_high = num(row.get("ci95_high"))
        maximum = num(row.get("max_observed"))
        rel = num(row.get("relative_gain"))
        if value is not None:
            macros.append(macro("DeviationMeanImprovement", f"{value:.2f}"))
        if ci_low is not None and ci_high is not None:
            macros.append(macro("DeviationMeanCILow", f"{ci_low:.2f}"))
            macros.append(macro("DeviationMeanCIHigh", f"{ci_high:.2f}"))
        if maximum is not None:
            macros.append(macro("DeviationMaximumObserved", f"{maximum:.2f}"))
        if rel is not None:
            macros.append(macro("DeviationRelativeGainPercent", f"{rel * 100:.2f}"))

    b2q_rows = [r for r in raw if r.get("policy") == "B2q" and r.get("critical_mean_response_minutes") not in (None, "", "NA")]
    b2_rows = [r for r in raw if r.get("policy") == "B2" and r.get("experiment") in ("exp1_ambulance_count", "exp2_total_demand", "exp6_criticality_mix") and r.get("critical_mean_response_minutes") not in (None, "", "NA")]
    if b2q_rows:
        b2q_crit = sum(float(r["critical_mean_response_minutes"]) for r in b2q_rows) / len(b2q_rows)
        macros.append(macro("BTwoQMeanCriticalResponseMinutes", f"{b2q_crit:.1f}"))
    if b2_rows:
        b2_crit = sum(float(r["critical_mean_response_minutes"]) for r in b2_rows) / len(b2_rows)
        macros.append(macro("BTwoMeanCriticalResponseMinutes", f"{b2_crit:.1f}"))

    target.write_text("\n".join(macros) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--weight-sensitivity-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "generated")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    weight_dir = args.weight_sensitivity_dir.resolve()
    weight_manifest = json.loads((weight_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("completed_case_count") != manifest.get("case_count"):
        raise SystemExit("run manifest is incomplete; refusing to generate report assets")
    if weight_manifest.get("experiment") != "exp8_weight_sensitivity" or weight_manifest.get("completed_case_count") != weight_manifest.get("case_count"):
        raise SystemExit("weight-sensitivity manifest is incomplete or has the wrong experiment")
    summary = read_csv(run_dir / "summary_metrics.csv")
    raw = read_csv(run_dir / "raw_results.csv")
    derived_path = run_dir / "derived_rates_summary.csv"
    if derived_path.exists():
        derived = read_csv(derived_path)
    else:
        derived = derive_rate_summaries(raw)
    weight_summary = read_csv(weight_dir / "summary_metrics.csv")
    dev_summary_path = run_dir / "deviations" / "deviation_summary.csv"
    deviation_rows = read_csv(dev_summary_path) if dev_summary_path.exists() else []

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_service_table(summary, args.output_dir / "service_table.tex")
    write_gap_table(summary, args.output_dir / "cost_gap_table.tex")
    write_communication_table(summary, derived, args.output_dir / "communication_table.tex")
    write_proposal_results_table(summary, args.output_dir / "proposal_results_table.tex")
    write_weight_sensitivity_table(weight_summary, args.output_dir / "weight_sensitivity_table.tex")
    write_policy_comparison_table(raw, args.output_dir / "policy_comparison_table.tex")
    write_deviation_table(deviation_rows, args.output_dir / "deviation_table.tex")
    write_message_table(raw, args.output_dir / "message_table.tex")
    write_macros(summary, raw, deviation_rows, manifest, weight_manifest, args.output_dir / "result_macros.tex")
    print(f"Generated report assets from {run_dir} and {weight_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

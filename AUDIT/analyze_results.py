"""Create a deterministic audit summary from one completed experiment directory."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def metric_summary(rows: list[dict[str, str]], experiment: str, level: str, policy: str, metric: str) -> dict[str, str]:
    return next(
        row for row in rows
        if row["experiment"] == experiment and row["level"] == level
        and row["policy"] == policy and row["metric"] == metric
    )


def cell(row: dict[str, str], metric: str, scale: float = 1.0, digits: int = 2) -> str:
    value = float(row["mean"]) * scale
    low = float(row["ci95_low"]) * scale
    high = float(row["ci95_high"]) * scale
    return f"{value:.{digits}f} [{low:.{digits}f}, {high:.{digits}f}]"


def render(run_dir: Path) -> str:
    raw = read_csv(run_dir / "raw_results.csv")
    summaries = read_csv(run_dir / "summary_metrics.csv")
    manifest = __import__("json").loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in raw:
        key = (row["experiment"], row["level"], row["seed"], row["demand_condition"])
        grouped[key][row["policy"]] = row
    compared = 0
    differences = []
    fields = (
        "served", "expired", "duplicate_incidents", "service_rate",
        "mean_response_minutes", "critical_mean_response_minutes", "mean_coverage",
        "utilization", "total_cost", "messages_sent", "messages_delivered",
    )
    for policies in grouped.values():
        if "B1" in policies and "B2" in policies:
            compared += 1
            differences.extend(
                (field, policies["B1"][field], policies["B2"][field])
                for field in fields if policies["B1"][field] != policies["B2"][field]
            )

    try:
        display_path = run_dir.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        display_path = run_dir.name
    lines = [
        "# Baseline Result Summary (Generated)",
        "",
        f"Input: `{display_path}`. Regenerate with `python AUDIT/analyze_results.py {display_path} --output AUDIT/BASELINE_RESULT_SUMMARY.md`.",
        "",
        f"- Raw policy rows: {len(raw)}; seed groups: {len(grouped)}; paired seeds: {len(manifest['seed_list'])}; families: {manifest['experiment_count']}; manifest runtime sum: {manifest['total_wall_seconds']:.3f} seconds.",
        f"- B1/B2 matched groups checked: {compared}; unequal metric cells: {len(differences)}.",
        "- Intervals in this file are the committed seed-level percentile-bootstrap intervals. They resample seeds, not calls. The B3 cost-gap and service/coverage-difference rows are paired at the seed level before aggregation.",
        "- `mean_response_minutes` and its critical counterpart are conditional on being served; no response value is assigned to missed calls.",
        "",
        "## Policy summaries by experiment level",
        "",
        "Percent values are followed by 95% seed-bootstrap intervals in brackets. Cost gap is signed relative to heuristic B3. Response is minutes among served calls. Coverage, utilization, and RMSE are in their native units.",
        "",
        "| Experiment | Level | Policy | Service % [95% CI] | Signed cost gap % [95% CI] | Response min [95% CI] | Critical response min [95% CI] | Coverage [95% CI] | Utilization [95% CI] | RMSE [95% CI] |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    order = [
        "exp1_ambulance_count", "exp2_total_demand", "exp3_demand_pattern",
        "exp4_communication", "exp5_demand_knowledge", "exp6_criticality_mix",
        "exp7_weight_tradeoff",
    ]
    level_order = {
        "exp1_ambulance_count": ["n=3", "n=5", "n=7", "n=10"],
        "exp2_total_demand": ["low:2.5/h", "medium:5/h", "high:10/h"],
        "exp3_demand_pattern": ["uniform", "hotspots", "shifting"],
        "exp4_communication": ["full", "radius-limited", "lossy", "none"],
        "exp5_demand_knowledge": ["learned", "oracle"],
        "exp6_criticality_mix": ["low-heavy", "balanced", "high-heavy"],
        "exp7_weight_tradeoff": ["coverage-light", "balanced", "coverage-heavy"],
    }
    levels_by_family: dict[str, set[str]] = defaultdict(set)
    for row in summaries:
        levels_by_family[row["experiment"]].add(row["level"])
    for experiment in order:
        for level in level_order[experiment]:
            if level not in levels_by_family[experiment]:
                continue
            for policy in ("B1", "B2", "B3", "BID"):
                service = metric_summary(summaries, experiment, level, policy, "service_rate")
                gap = metric_summary(summaries, experiment, level, policy, "b3_cost_gap_relative")
                response = metric_summary(summaries, experiment, level, policy, "mean_response_minutes")
                critical = metric_summary(summaries, experiment, level, policy, "critical_mean_response_minutes")
                coverage = metric_summary(summaries, experiment, level, policy, "mean_coverage")
                utilization = metric_summary(summaries, experiment, level, policy, "utilization")
                rmse = metric_summary(summaries, experiment, level, policy, "demand_rmse")
                lines.append(
                    f"| {experiment} | {level} | {policy} | {cell(service, 'service_rate', 100)} | "
                    f"{cell(gap, 'b3_cost_gap_relative', 100)} | {cell(response, 'mean_response_minutes')} | "
                    f"{cell(critical, 'critical_mean_response_minutes')} | {cell(coverage, 'mean_coverage')} | "
                    f"{cell(utilization, 'utilization')} | {cell(rmse, 'demand_rmse')} |"
                )

    comparisons = read_csv(run_dir / "b3_comparisons.csv")
    key_summary = defaultdict(list)
    for row in comparisons:
        if row["policy"] == "BID":
            key_summary[(row["experiment"], row["level"], row["demand_condition"], "service_diff")].append(float(row["b3_service_rate_difference"]))
            if row["b3_cost_gap_relative"] not in {"", "NA", "None"}:
                key_summary[(row["experiment"], row["level"], row["demand_condition"], "cost_gap")].append(float(row["b3_cost_gap_relative"]))
    lines.extend(["", "## Paired BID contrasts", "", "The means below are calculated from paired per-seed differences; this summary includes the seed-level spread and does not treat incidents as independent replicates.", "", "| Experiment | Level | Demand condition | Service difference vs B3 (pp) | Mean signed cost gap vs B3 (%) |", "|---|---|---|---:|---:|"])
    for key in sorted(key_summary):
        if key[3] != "service_diff":
            continue
        service_values = key_summary[key]
        cost_values = key_summary.get((key[0], key[1], key[2], "cost_gap"), [])
        service_mean = sum(service_values) / len(service_values) * 100
        cost_mean = sum(cost_values) / len(cost_values) * 100 if cost_values else float("nan")
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {service_mean:.2f} (n={len(service_values)}) | {cost_mean:.2f} (n={len(cost_values)}) |")

    lines.extend(["", "## Identity check", ""])
    if differences:
        lines.extend(["B1 and B2 differ in the following matched cells:", "", "| Metric | B1 | B2 |", "|---|---:|---:|"])
        lines.extend(f"| {field} | {left} | {right} |" for field, left, right in differences)
    else:
        lines.append(f"B1 and B2 matched exactly on {compared} seed-condition groups across served/missed counts, response summaries, coverage, utilization, total cost, and message counts. Their distinct names do not imply distinct behavior under this fixed-call selector.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = render(args.run_dir.resolve())
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

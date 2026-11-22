"""Validate a completed independent alpha/beta/gamma sensitivity batch."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICIES = {"B1", "B2", "B3", "BID"}
METRIC_EQUALITY_FIELDS = (
    "service_rate", "mean_response_minutes", "critical_mean_response_minutes",
    "mean_coverage", "utilization", "total_cost",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def check_close(actual: str, expected: float, label: str) -> None:
    if actual in ("", "NA", "None", "null"):
        raise ValueError(f"{label} is missing")
    if not math.isclose(float(actual), expected, rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError(f"{label}: observed {actual}, expected {expected}")


def validate(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("experiment") != "exp8_weight_sensitivity":
        raise ValueError("wrong experiment name")
    if manifest.get("completed_case_count") != manifest.get("case_count"):
        raise ValueError("manifest case count is incomplete")
    if manifest["case_count"] != 9 * 20 * len(POLICIES):
        raise ValueError(f"unexpected case count: {manifest['case_count']}")
    seeds = set(manifest["seed_list"])
    if len(seeds) != 20:
        raise ValueError("expected 20 unique paired seeds")
    if manifest["bootstrap_resamples"] != 2000:
        raise ValueError("unexpected bootstrap resample count")

    raw = read_csv(run_dir / "raw_results.csv")
    comparisons = read_csv(run_dir / "b3_comparisons.csv")
    logs = [json.loads(line) for line in (run_dir / "run.log.jsonl").read_text(encoding="utf-8").splitlines() if line]
    recovered_path = run_dir / "run.log.recovered.jsonl"
    recovered = [json.loads(line) for line in recovered_path.read_text(encoding="utf-8").splitlines() if line] if recovered_path.exists() else []
    if len(raw) != manifest["case_count"] or len(comparisons) != len(raw) or len(logs) + len(recovered) != len(raw):
        raise ValueError("raw, comparison, original/recovered log, and manifest counts disagree")
    all_logs = logs + recovered
    if {int(entry["index"]) for entry in all_logs} != set(range(1, len(raw) + 1)):
        raise ValueError("original and recovered log indices do not cover every raw case")
    if recovered:
        audit = json.loads((run_dir / "log_recovery.json").read_text(encoding="utf-8"))
        if audit.get("status") != "RECOVERED_FROM_RAW_RECORD" or sha256(recovered_path) != audit.get("sidecar_sha256"):
            raise ValueError("log recovery sidecar audit does not match")
        if any(not entry.get("recovered_from_raw_results") for entry in recovered):
            raise ValueError("a reconstructed log entry is not marked")
    if any(entry.get("status") != "completed" for entry in all_logs):
        raise ValueError("run log contains a non-completed case")

    for relative, expected in manifest["source_sha256"].items():
        path = PROJECT_ROOT / Path(relative)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"source hash mismatch: {relative}")

    groups: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in raw:
        if int(row["seed"]) not in seeds:
            raise ValueError(f"unexpected seed {row['seed']}")
        groups[(row["level"], int(row["seed"]))].append(row)
        if int(row["n_incidents"]) != int(row["served"]) + int(row["expired"]):
            raise ValueError("incident accounting does not partition into served and expired")
        if hashlib.sha256(row["config_json"].encode("utf-8")).hexdigest() != row["config_sha256"]:
            raise ValueError("row config hash mismatch")
        if bool(row["policy_oracle_input"] == "True") != (row["policy"] == "B3"):
            raise ValueError("oracle input flag does not match policy")

    if len(groups) != 9 * 20:
        raise ValueError(f"expected 180 matched level/seed groups; observed {len(groups)}")
    for (level, seed), rows in groups.items():
        if {row["policy"] for row in rows} != POLICIES or len(rows) != len(POLICIES):
            raise ValueError(f"policy set incomplete for {level}, seed {seed}")
        if len({int(row["n_incidents"]) for row in rows}) != 1:
            raise ValueError(f"policies saw different incident counts for {level}, seed {seed}")
        if len({row["config_sha256"] for row in rows}) != 1:
            raise ValueError(f"policies used different configs for {level}, seed {seed}")
        by_policy = {row["policy"]: row for row in rows}
        for field in METRIC_EQUALITY_FIELDS:
            if by_policy["B1"][field] != by_policy["B2"][field]:
                raise ValueError(f"B1/B2 differ in {field} for {level}, seed {seed}")

    comparisons_by_key = {(row["policy"], row["level"], int(row["seed"])): row for row in comparisons}
    for (level, seed), rows in groups.items():
        b3_cost = float(next(row for row in rows if row["policy"] == "B3")["total_cost"])
        for source_row in rows:
            joined = comparisons_by_key[(source_row["policy"], level, seed)]
            if source_row["policy"] == "B3":
                check_close(joined["b3_cost_gap_absolute"], 0.0, "B3 absolute gap")
                continue
            policy_cost = float(source_row["total_cost"])
            check_close(joined["b3_cost_gap_absolute"], policy_cost - b3_cost, "absolute B3 gap")
            if b3_cost > 0:
                check_close(joined["b3_cost_gap_relative"], (policy_cost - b3_cost) / b3_cost, "relative B3 gap")
            elif joined["b3_cost_gap_relative"] not in ("", "NA", "None", "null"):
                raise ValueError("relative gap must be undefined when B3 cost is zero")

    summary = read_csv(run_dir / "summary_metrics.csv")
    bid_gaps = [row for row in summary if row["policy"] == "BID" and row["metric"] == "b3_cost_gap_relative"]
    if len(bid_gaps) != 9:
        raise ValueError(f"expected nine BID weight-gap summaries; observed {len(bid_gaps)}")
    if any(int(row["n"]) != 20 for row in bid_gaps):
        raise ValueError("a weight-gap interval is not based on all 20 seeds")
    if len(list((run_dir / "report_plots").glob("*.png"))) != 24:
        raise ValueError("expected 24 regenerated sensitivity plots")

    return {
        "status": "PASS",
        "raw_cases": len(raw),
        "matched_level_seed_groups": len(groups),
        "paired_policy_cases": len(comparisons),
        "original_logs": len(logs),
        "recovered_log_entries": len(recovered),
        "completed_logs_and_recoveries": len(all_logs),
        "bid_gap_intervals": len(bid_gaps),
        "plots": len(list((run_dir / "report_plots").glob("*.png"))),
        "seeds": sorted(seeds),
        "source_hashes_verified": len(manifest["source_sha256"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.run_dir.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

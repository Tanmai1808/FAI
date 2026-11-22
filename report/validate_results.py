"""Audit completed experiment outputs against their manifest and source hashes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_PROPOSAL_SHA256 = "8CECF4051109FE21F1E4EC3AE764C1AB86C27D84A4D26100061878EED3404EF2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def audit(run_dir: Path, project_root: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    raw = read_csv(run_dir / "raw_results.csv")
    comparisons = read_csv(run_dir / "b3_comparisons.csv")
    summaries = read_csv(run_dir / "summary_metrics.csv")
    deviations = read_csv(run_dir / "deviations" / "deviation_cases.csv")
    deviation_summary = read_csv(run_dir / "deviations" / "deviation_summary.csv")

    require(manifest.get("case_count") == manifest.get("completed_case_count"), "manifest run count is incomplete")
    require(len(raw) == manifest.get("completed_case_count"), "raw CSV row count does not match manifest")
    require(len(comparisons) == len(raw), "paired comparison CSV row count differs from raw data")
    require(bool(summaries), "summary metrics file is empty")
    require(len(deviations) == len(manifest.get("seed_list", [])) * int(manifest["base_config"]["n_ambulances"]), "deviation run count is incomplete")
    require(
        len(deviation_summary) in (1, 1 + int(manifest["base_config"]["n_ambulances"])),
        "expected restricted deviation summary rows (overall and per-agent)",
    )

    expected_source = manifest.get("source_sha256", {})
    for relative, expected_hash in expected_source.items():
        path = project_root / Path(relative)
        require(path.exists(), f"hashed source is missing: {relative}")
        require(sha256(path) == str(expected_hash).upper(), f"source hash changed since the run: {relative}")

    proposal = project_root / "docs" / "reference" / "original-proposal.pdf"
    require(proposal.exists(), "preserved proposal PDF is missing")
    require(sha256(proposal) == EXPECTED_PROPOSAL_SHA256, "preserved proposal PDF does not match supplied source")

    policies_by_group: dict[tuple[str, str, str, str], set[str]] = {}
    incidents_by_group: dict[tuple[str, str, str, str], set[int]] = {}
    raw_by_key: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in raw:
        config_text = row["config_json"]
        digest = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
        require(digest == row["config_sha256"], f"configuration hash mismatch for {row['experiment']} {row['level']}")
        config = json.loads(config_text)
        require(config["n_ambulances"] == int(row["n_ambulances"]), "config/fleet column mismatch")
        n_calls = int(row["n_incidents"])
        served = int(row["served"])
        expired = int(row["expired"])
        duplicates = int(row["duplicate_incidents"])
        commitments = int(row["total_responder_commitments"])
        require(served + expired == n_calls, f"calls are not partitioned into served/expired for seed {row['seed']}")
        require(0 <= duplicates <= n_calls, "duplicate incident count outside valid bounds")
        require(commitments >= served, "commitments cannot be fewer than served calls")
        require(0 <= float(row["service_rate"]) <= 1, "service rate outside [0,1]")
        require(-1e-9 <= float(row["mean_coverage"]) <= 1 + 1e-9, "coverage outside [0,1]")
        require(0 <= float(row["utilization"]) <= 1 + 1e-9, "utilization outside [0,1]")
        require(int(row["messages_delivered"]) <= int(row["messages_sent"]), "delivered message count exceeds sent count")
        require(abs(float(row["service_rate"]) - (served / n_calls if n_calls else 1.0)) < 1e-9, "service rate formula mismatch")
        group = (row["experiment"], row["level"], row["seed"], row["demand_condition"])
        policies_by_group.setdefault(group, set()).add(row["policy"])
        incidents_by_group.setdefault(group, set()).add(n_calls)
        raw_by_key[(*group, row["policy"])] = row
    for group, policies in policies_by_group.items():
        require(policies == {"B1", "B2", "B3", "BID"}, f"incomplete method set for {group}")
        require(len(incidents_by_group[group]) == 1, f"matched methods did not share one incident tape count for {group}")
        b3 = raw_by_key[(*group, "B3")]
        bid = raw_by_key[(*group, "BID")]
        if bid["communication"] == "full":
            require(int(bid["duplicate_incidents"]) == 0, f"full-communication BID had duplicates for {group}")

    comparison_by_key = {
        (row["experiment"], row["level"], row["seed"], row["demand_condition"], row["policy"]): row
        for row in comparisons
    }
    for key, row in raw_by_key.items():
        comp = comparison_by_key.get(key)
        require(comp is not None, f"missing paired comparison row for {key}")
        baseline = float(raw_by_key[(*key[:4], "B3")]["total_cost"])
        expected = float(row["total_cost"]) - baseline
        actual = float(comp["b3_cost_gap_absolute"])
        require(abs(expected - actual) < 1e-8, f"absolute B3 gap mismatch for {key}")
        relative_text = comp.get("b3_cost_gap_relative")
        if baseline > 0:
            require(relative_text not in {"", "NA", "None"}, f"relative B3 gap unexpectedly missing for {key}")
            require(abs(float(relative_text) - expected / baseline) < 1e-8, f"relative B3 gap mismatch for {key}")
        else:
            require(relative_text in {"", "NA", "None"}, f"zero-baseline relative gap is not NA for {key}")

    image_dir = run_dir / "plots"
    image_files = list(image_dir.glob("*.png"))
    require(any(path.name == "results_contact_sheet.png" for path in image_files), "result contact sheet is missing")
    for path in image_files:
        require(path.stat().st_size > 1000, f"empty or suspiciously small PNG: {path.name}")
        require(path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"invalid PNG signature: {path.name}")
    require({f"exp{i}_" for i in range(1, 8)} <= {row["experiment"].split("_", 1)[0] + "_" for row in raw}, "one or more experiment families are absent")

    try:
        run_dir_label = run_dir.relative_to(project_root).as_posix()
    except ValueError:
        # Keep externally located audit runs portable and avoid embedding a
        # machine-specific absolute path in a committed artifact.
        run_dir_label = run_dir.name

    audit_report = {
        "audited_utc": datetime.now(timezone.utc).isoformat(),
        "run_dir": run_dir_label,
        "policy_run_count": len(raw),
        "matched_scenario_groups": len(policies_by_group),
        "scenario_seed_count": len(manifest.get("seed_list", [])),
        "experiment_families": sorted({row["experiment"] for row in raw}),
        "summary_row_count": len(summaries),
        "deviation_run_count": len(deviations),
        "plot_count": len(image_files),
        "source_hashes_verified": len(expected_source),
        "original_proposal_sha256": sha256(proposal),
        "status": "passed",
    }
    (run_dir / "audit.json").write_text(json.dumps(audit_report, indent=2, sort_keys=True), encoding="utf-8")
    return audit_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(audit(args.run_dir.resolve(), args.project_root.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

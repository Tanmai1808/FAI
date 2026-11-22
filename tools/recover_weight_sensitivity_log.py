"""Create an explicitly marked sidecar for any missing batch-log line.

The script never edits the original run.log.jsonl. Recovered entries are
derived only from complete raw_results.csv records and recorded in a separate
JSONL file with a hash audit note.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recover(run_dir: Path) -> dict[str, object]:
    log_path = run_dir / "run.log.jsonl"
    raw_path = run_dir / "raw_results.csv"
    existing = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    entries = list(csv.DictReader(raw_path.open(encoding="utf-8", newline="")))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    expected_total = int(manifest["case_count"])
    logged = {int(entry["index"]): entry for entry in existing}
    if len(logged) != len(existing):
        raise ValueError("original log contains duplicate indices")
    missing = sorted(set(range(1, expected_total + 1)) - set(logged))
    if not missing:
        return {"status": "NO_RECOVERY_NEEDED", "existing_log_entries": len(existing)}
    if len(missing) != 1 or len(existing) != expected_total - 1 or len(entries) != expected_total:
        raise ValueError("unexpected log discrepancy; refusing to reconstruct")

    levels = manifest["weight_levels"]
    seeds = manifest["seed_list"]
    policy_order = manifest["policy_settings"]["policies"]
    reconstructed = []
    for index in missing:
        zero_based = index - 1
        cell_index, within_cell = divmod(zero_based, len(seeds) * len(policy_order))
        seed_index, policy_index = divmod(within_cell, len(policy_order))
        cell = levels[cell_index]
        factor = cell["factor"]
        level = cell["level"]
        seed = seeds[seed_index]
        policy = policy_order[policy_index]
        row = next(
            row for row in entries
            if row["weight_factor"] == factor
            and float(row["weight_level"]) == float(level)
            and int(row["seed"]) == int(seed)
            and row["policy"] == policy
        )
        reconstructed.append({
            "index": index,
            "total": expected_total,
            "factor": factor,
            "level": level,
            "policy": policy,
            "seed": seed,
            "incidents": int(row["n_incidents"]),
            "served": int(row["served"]),
            "total_cost": float(row["total_cost"]),
            "wall_seconds": float(row["wall_seconds"]),
            "status": "completed",
            "recovered_from_raw_results": True,
        })

    sidecar = run_dir / "run.log.recovered.jsonl"
    if sidecar.exists():
        raise FileExistsError(f"refusing to overwrite existing recovery sidecar: {sidecar}")
    sidecar.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in reconstructed), encoding="utf-8")
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RECOVERED_FROM_RAW_RECORD",
        "original_log_path": "run.log.jsonl",
        "original_log_sha256": sha256(log_path),
        "raw_results_path": "raw_results.csv",
        "raw_results_sha256": sha256(raw_path),
        "missing_indices": missing,
        "sidecar_path": sidecar.name,
        "sidecar_sha256": sha256(sidecar),
        "reconstruction_tool_sha256": sha256(Path(__file__).resolve()),
        "note": "Original log was not edited. Recovered metadata rows are deterministically mapped to raw result rows by manifest ordering and marked explicitly.",
    }
    (run_dir / "log_recovery.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "RECOVERED_FROM_RAW_RECORD",
        "original_log_entries": len(existing),
        "recovered_entries": len(reconstructed),
        "missing_indices": missing,
        "sidecar": sidecar.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(recover(args.run_dir.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run independent one-factor-at-a-time sensitivity checks for alpha, beta, gamma."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ambulance_dispatch.config import ScenarioConfig, Weights  # noqa: E402
from ambulance_dispatch.metrics import paired_b3_gaps, summarize_by  # noqa: E402
from ambulance_dispatch.simulator import BASE_POLICIES, RunSettings, simulate  # noqa: E402


def weight_sweep(
    base: ScenarioConfig,
    levels: dict[str, Iterable[float]] | None = None,
) -> tuple[tuple[str, float, ScenarioConfig], ...]:
    """Return independent axes, with every non-varied weight at the base value."""
    levels = levels or {"alpha": (0.5, 1.0, 2.0), "beta": (4.0, 8.0, 16.0), "gamma": (4.0, 8.0, 16.0)}
    if set(levels) != {"alpha", "beta", "gamma"}:
        raise ValueError("weight sensitivity must define alpha, beta, and gamma axes")
    settings: list[tuple[str, float, ScenarioConfig]] = []
    for value in levels["alpha"]:
        settings.append(("alpha", value, replace(base, weights=replace(base.weights, alpha=value))))
    for value in levels["beta"]:
        settings.append(("beta", value, replace(base, weights=replace(base.weights, beta=value))))
    for value in levels["gamma"]:
        settings.append(("gamma", value, replace(base, weights=replace(base.weights, gamma=value))))
    for factor, value, config in settings:
        if value <= 0 or len(tuple(levels[factor])) != 3:
            raise ValueError("each weight axis must have three positive levels")
    return tuple(settings)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_hashes() -> dict[str, str]:
    paths = sorted((PROJECT_ROOT / "src").rglob("*.py")) + [Path(__file__).resolve()]
    return {path.relative_to(PROJECT_ROOT).as_posix(): _sha256(path) for path in paths}


def _revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write an empty CSV: {path}")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_config(path: Path) -> ScenarioConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["severity_probabilities"] = tuple(raw["severity_probabilities"])
    raw["deadlines_minutes"] = tuple(raw["deadlines_minutes"])
    raw["weights"] = Weights(**raw["weights"])
    return ScenarioConfig(**raw)


def run_weight_sensitivity(
    output_dir: str | Path,
    base: ScenarioConfig,
    seeds: Iterable[int],
    bootstrap_resamples: int = 2_000,
    weight_levels: dict[str, Iterable[float]] | None = None,
    experiment_config: dict[str, Any] | None = None,
) -> Path:
    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty results directory: {output}")
    seed_list = tuple(int(seed) for seed in seeds)
    if not seed_list or len(set(seed_list)) != len(seed_list):
        raise ValueError("provide at least one unique seed")
    cells = weight_sweep(base, weight_levels)
    experiment_config = experiment_config or {}
    communication = experiment_config.get("communication", {})
    communication_radius = float(communication.get("radius_minutes", 12.0))
    packet_loss = float(communication.get("packet_loss_probability", 0.25))
    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "exp8_weight_sensitivity",
        "design": "three independent one-factor-at-a-time sweeps; other weights fixed at base values",
        "seed_list": list(seed_list),
        "bootstrap_resamples": bootstrap_resamples,
        "experiment_config": experiment_config,
        "experiment_config_sha256": hashlib.sha256(
            json.dumps(experiment_config, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "base_config": asdict(base),
        "weight_levels": [
            {"factor": factor, "level": value, "weights": asdict(config.weights)}
            for factor, value, config in cells
        ],
        "case_count": len(cells) * len(seed_list) * len(BASE_POLICIES),
        "communication_settings": {
            "regime": "full",
            "radius_minutes": communication_radius,
            "packet_loss_probability": packet_loss,
            "note": "radius and loss defaults are recorded but inactive under full communication",
        },
        "policy_settings": {
            "policies": list(BASE_POLICIES),
            "demand_knowledge": "B1/B2 learned diagnostic only; B3 true-rate oracle; BID learned-rate input",
            "deviation": None,
        },
        "code_revision_at_run": _revision(),
        "source_sha256": _source_hashes(),
        "base_config_sha256": hashlib.sha256(
            json.dumps(asdict(base), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "case_semantics": "same seed creates the same exogenous incident tape for all weight cells and policies",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    raw_rows: list[dict[str, Any]] = []
    log_path = output / "run.log.jsonl"
    total = manifest["case_count"]
    index = 0
    for factor, level, config in cells:
        for seed in seed_list:
            for policy in BASE_POLICIES:
                index += 1
                demand = "oracle" if policy == "B3" else "learned"
                scenario_id = f"exp8_weight_sensitivity:{factor}={level:g}"
                started = time.perf_counter()
                result = simulate(
                    config,
                    RunSettings(
                        policy=policy,
                        communication="full",
                        communication_radius_minutes=communication_radius,
                        packet_loss_probability=packet_loss,
                        oracle_demand=(policy == "B3"),
                        seed=seed,
                        scenario_id=scenario_id,
                    ),
                )
                elapsed = time.perf_counter() - started
                config_text = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
                row = {
                    **result.to_dict(),
                    "experiment": "exp8_weight_sensitivity",
                    "level": f"{factor}={level:g}",
                    "weight_factor": factor,
                    "weight_level": level,
                    "demand_condition": demand,
                    "policy_oracle_input": policy == "B3",
                    "config_json": config_text,
                    "config_sha256": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
                    "wall_seconds": elapsed,
                }
                raw_rows.append(row)
                with (output / "raw_results.csv").open("a", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    if stream.tell() == 0:
                        writer.writeheader()
                    writer.writerow(row)
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({
                        "index": index, "total": total, "factor": factor, "level": level,
                        "policy": policy, "seed": seed, "incidents": result.n_incidents,
                        "served": result.served, "total_cost": result.total_cost,
                        "wall_seconds": elapsed, "status": "completed",
                    }, sort_keys=True) + "\n")
                if index == 1 or index % 40 == 0 or index == total:
                    print(f"[{index}/{total}] {factor}={level:g} {policy} seed={seed}: {elapsed:.2f}s")

    comparisons = paired_b3_gaps(
        raw_rows,
        # B3 is intentionally oracle-informed while the other policies use
        # learned rates.  Knowledge condition is therefore not a pairing key:
        # within one level and seed, all policies share the same call tape.
        match_keys=("experiment", "level", "seed"),
    )
    _write_csv(output / "b3_comparisons.csv", comparisons)
    group_keys = ("experiment", "level", "weight_factor", "policy", "communication", "demand_condition")
    metrics = (
        "total_cost", "service_rate", "expired_rate", "duplicate_rate",
        "mean_response_minutes", "median_response_minutes", "p90_response_minutes",
        "critical_mean_response_minutes", "critical_service_rate",
        "mean_coverage", "utilization", "messages_per_incident", "duplicate_incidents", "expired",
        "demand_rmse", "b3_cost_gap_absolute", "b3_cost_gap_relative",
        "b3_service_rate_difference", "b3_coverage_difference",
    )
    summaries = []
    for metric in metrics:
        summaries.extend(summarize_by(comparisons, group_keys, metric, bootstrap_resamples, seed=4096 + len(metric)))
    _write_csv(output / "summary_metrics.csv", summaries)
    manifest["completed_case_count"] = len(raw_rows)
    manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["total_wall_seconds"] = sum(float(row["wall_seconds"]) for row in raw_rows)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-config", type=Path, default=PROJECT_ROOT / "configs" / "weight_sensitivity.json")
    parser.add_argument("--seed-start", type=int)
    parser.add_argument("--seed-count", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    experiment_config = json.loads(args.experiment_config.read_text(encoding="utf-8"))
    if experiment_config["experiment"] != "exp8_weight_sensitivity":
        parser.error("experiment config must name exp8_weight_sensitivity")
    if experiment_config.get("communication", {}).get("regime") != "full":
        parser.error("the weight sensitivity config must use full communication")
    if tuple(experiment_config.get("policies", ())) != BASE_POLICIES:
        parser.error("the configured policy list must match the implemented four base policies")
    seed_start = experiment_config["seed_start"] if args.seed_start is None else args.seed_start
    seed_count = experiment_config["seed_count"] if args.seed_count is None else args.seed_count
    if seed_count < 1:
        parser.error("--seed-count must be positive")
    base_config_path = args.experiment_config.resolve().parent / experiment_config["base_config"]
    base_config = _load_config(base_config_path)
    if asdict(base_config.weights) != experiment_config["fixed_weights"]:
        parser.error("fixed weight values must match the linked base config")
    levels = {key: tuple(values) for key, values in experiment_config["weight_levels"].items()}
    run_weight_sensitivity(
        args.output,
        base_config,
        range(seed_start, seed_start + seed_count),
        bootstrap_resamples=int(experiment_config["bootstrap_resamples"]),
        weight_levels=levels,
        experiment_config=experiment_config,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

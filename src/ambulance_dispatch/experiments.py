"""Seven reproducible experiment families and incremental result persistence."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import ScenarioConfig, Weights, severity_mix
from .metrics import (
    bootstrap_mean_interval,
    compute_unilateral_deviation_statistics,
    paired_b3_gaps,
    summarize_by,
)
from .simulator import BASE_POLICIES, POLICIES, RunResult, RunSettings, Simulator, simulate


@dataclass(frozen=True)
class ExperimentCase:
    experiment: str
    level: str
    seed: int
    demand_condition: str
    config: ScenarioConfig
    policy: str
    communication: str = "full"
    communication_radius_minutes: float = 12.0
    packet_loss_probability: float = 0.25
    oracle_demand: bool = False

    @property
    def scenario_id(self) -> str:
        return f"{self.experiment}:{self.level}"


def _family(
    experiment: str,
    level: str,
    config: ScenarioConfig,
    seeds: Iterable[int],
    policies: tuple[str, ...] = BASE_POLICIES,
    communication: str = "full",
    communication_radius_minutes: float = 12.0,
    packet_loss_probability: float = 0.25,
    demand_condition: str = "learned",
) -> Iterable[ExperimentCase]:
    for seed in seeds:
        for policy in policies:
            oracle = policy == "B3" or (policy == "BID" and demand_condition == "oracle")
            yield ExperimentCase(
                experiment,
                level,
                seed,
                demand_condition,
                config,
                policy,
                communication,
                communication_radius_minutes,
                packet_loss_probability,
                oracle,
            )


def build_experiment_cases(
    base: ScenarioConfig,
    seeds: Iterable[int],
    selected: set[str] | None = None,
) -> tuple[ExperimentCase, ...]:
    """Build a one-factor-at-a-time design with paired seed streams."""
    seed_list = tuple(int(seed) for seed in seeds)
    if not seed_list:
        raise ValueError("at least one seed is required")
    family_names = {
        "exp1": "exp1_ambulance_count",
        "exp2": "exp2_total_demand",
        "exp3": "exp3_demand_pattern",
        "exp4": "exp4_communication",
        "exp4b": "exp4b_communication_radius",
        "exp4c": "exp4c_communication_loss",
        "exp5": "exp5_demand_knowledge",
        "exp5b": "exp5b_learning_shifting",
        "exp6": "exp6_criticality_mix",
        "exp7": "exp7_weight_tradeoff",
    }
    if selected is not None and not selected.issubset(set(family_names)):
        raise ValueError("experiment selection must use exp1 through exp7, exp4b, exp4c, exp5b")
    selected_families = {family_names[name] for name in selected} if selected is not None else None
    cases: list[ExperimentCase] = []

    def add(experiment: str, level: str, config: ScenarioConfig, **kwargs: Any) -> None:
        if selected_families is None or experiment in selected_families:
            cases.extend(_family(experiment, level, config, seed_list, **kwargs))

    exp_policies_with_b2q = ("B1", "B2", "B2q", "B3", "BID")

    for n in (3, 5, 7, 10):
        add("exp1_ambulance_count", f"n={n}", replace(base, n_ambulances=n), policies=exp_policies_with_b2q)
    for rate, label in ((2.5, "low"), (5.0, "medium"), (10.0, "high")):
        add("exp2_total_demand", f"{label}:{rate:g}/h", replace(base, total_rate_per_hour=rate), policies=exp_policies_with_b2q)
    for pattern in ("uniform", "hotspots", "shifting"):
        add("exp3_demand_pattern", pattern, replace(base, demand_pattern=pattern))
    for regime in ("full", "radius-limited", "lossy", "none"):
        add(
            "exp4_communication",
            regime,
            base,
            communication=regime,
        )
    # exp4b: radius sweep for BID only (r in {2,4,6,8,12}), with BID full and none reference rows
    add("exp4b_communication_radius", "full", base, policies=("BID",), communication="full")
    add("exp4b_communication_radius", "none", base, policies=("BID",), communication="none")
    for r in (2, 4, 6, 8, 12):
        add(
            "exp4b_communication_radius",
            f"r={r}",
            base,
            policies=("BID",),
            communication="radius-limited",
            communication_radius_minutes=float(r),
        )
    # exp4c: loss sweep for BID only (p in {0,0.1,0.25,0.5,0.75,1.0}), with BID full and none reference rows
    add("exp4c_communication_loss", "full", base, policies=("BID",), communication="full")
    add("exp4c_communication_loss", "none", base, policies=("BID",), communication="none")
    for p in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0):
        add(
            "exp4c_communication_loss",
            f"p={p:g}",
            base,
            policies=("BID",),
            communication="lossy",
            packet_loss_probability=p,
        )
    for condition in ("learned", "oracle"):
        add(
            "exp5_demand_knowledge",
            condition,
            base,
            demand_condition=condition,
        )
    # exp5b: demand learning under shifting demand (oracle vs learned BID)
    shifting_base = replace(base, demand_pattern="shifting")
    for condition in ("learned", "oracle"):
        add(
            "exp5b_learning_shifting",
            condition,
            shifting_base,
            policies=("BID",),
            demand_condition=condition,
        )
    for mix in ("low-heavy", "balanced", "high-heavy"):
        add(
            "exp6_criticality_mix",
            mix,
            replace(base, severity_probabilities=severity_mix(mix)),
            policies=exp_policies_with_b2q,
        )
    for label, weights in (
        ("coverage-light", Weights(alpha=1.0, beta=4.0, gamma=4.0, rho=base.weights.rho)),
        ("balanced", Weights(alpha=1.0, beta=8.0, gamma=8.0, rho=base.weights.rho)),
        ("coverage-heavy", Weights(alpha=1.0, beta=16.0, gamma=16.0, rho=base.weights.rho)),
    ):
        add("exp7_weight_tradeoff", label, replace(base, weights=weights))
    return tuple(cases)


def _config_dict(config: ScenarioConfig) -> dict[str, Any]:
    return asdict(config)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_manifest(project_root: Path) -> dict[str, str]:
    source_root = project_root / "src"
    return {
        path.relative_to(project_root).as_posix(): _sha256(path)
        for path in sorted(source_root.rglob("*.py"))
    }


def _git_revision(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _append_csv(path: Path, row: dict[str, Any]) -> None:
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()), extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow(row)
        handle.flush()


def _row_for_case(case: ExperimentCase, result: RunResult, wall_seconds: float) -> dict[str, Any]:
    config_text = json.dumps(_config_dict(case.config), sort_keys=True, separators=(",", ":"))
    return {
        **result.to_dict(),
        "experiment": case.experiment,
        "level": case.level,
        "demand_condition": case.demand_condition,
        "communication": case.communication,
        "policy_oracle_input": case.oracle_demand,
        "config_json": config_text,
        "config_sha256": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
        "wall_seconds": wall_seconds,
    }


def run_experiment_suite(
    project_root: str | Path,
    output_dir: str | Path,
    base: ScenarioConfig,
    seeds: Iterable[int],
    selected: set[str] | None = None,
    bootstrap_resamples: int = 2_000,
) -> Path:
    """Run cases in order, saving each completed raw row and an append-only JSONL log."""
    project_root = Path(project_root).resolve()
    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty results directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "plots").mkdir(exist_ok=True)
    cases = build_experiment_cases(base, seeds, selected)
    seed_list = sorted({case.seed for case in cases})
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "command_line": sys.argv,
        "python_version": sys.version,
        "platform": platform.platform(),
        "git_revision": _git_revision(project_root),
        "source_sha256": _source_manifest(project_root),
        "seed_list": seed_list,
        "bootstrap_resamples": bootstrap_resamples,
        "base_config": _config_dict(base),
        "experiment_count": len({case.experiment for case in cases}),
        "case_count": len(cases),
        "selected_experiments": sorted(selected) if selected is not None else sorted(family_names.keys()),
        "case_semantics": "one-factor-at-a-time; identical scenario seeds are reused across methods",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    raw_path = output / "raw_results.csv"
    log_path = output / "run.log.jsonl"
    gz_path = output / "incident_outcomes.csv.gz"
    gz_handle = gzip.open(gz_path, "wt", newline="", encoding="utf-8")
    gz_fieldnames = [
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
    gz_writer = csv.DictWriter(gz_handle, fieldnames=gz_fieldnames)
    gz_writer.writeheader()

    rmse_ts_path = output / "learning_rmse_timeseries.csv"
    rmse_ts_handle = rmse_ts_path.open("w", newline="", encoding="utf-8")
    rmse_ts_fieldnames = ["experiment", "level", "policy", "seed", "time_minutes", "rmse"]
    rmse_ts_writer = csv.DictWriter(rmse_ts_handle, fieldnames=rmse_ts_fieldnames)
    rmse_ts_writer.writeheader()

    raw_rows: list[dict[str, Any]] = []
    total = len(cases)
    for index, case in enumerate(cases, start=1):
        settings = RunSettings(
            policy=case.policy,
            communication=case.communication,
            communication_radius_minutes=case.communication_radius_minutes,
            packet_loss_probability=case.packet_loss_probability,
            oracle_demand=case.oracle_demand,
            seed=case.seed,
            scenario_id=case.scenario_id,
        )
        started = time.perf_counter()
        sim = Simulator(case.config, settings)
        result = sim.run()
        elapsed = time.perf_counter() - started
        for item in sim.incident_outcomes():
            gz_writer.writerow({
                "seed": case.seed,
                "policy": case.policy,
                "experiment": case.experiment,
                "level": case.level,
                **item,
            })
        for item in sim.learning_rmse_timeseries():
            rmse_ts_writer.writerow({
                "experiment": case.experiment,
                "level": case.level,
                "policy": case.policy,
                "seed": case.seed,
                "time_minutes": f"{item['time_minutes']:.1f}",
                "rmse": f"{item['rmse']:.6f}",
            })
        row = _row_for_case(case, result, elapsed)
        raw_rows.append(row)
        _append_csv(raw_path, row)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(
                json.dumps(
                    {
                        "index": index,
                        "total": total,
                        "experiment": case.experiment,
                        "level": case.level,
                        "policy": case.policy,
                        "communication": case.communication,
                        "demand_condition": case.demand_condition,
                        "seed": case.seed,
                        "incidents": result.n_incidents,
                        "served": result.served,
                        "total_cost": result.total_cost,
                        "wall_seconds": elapsed,
                        "status": "completed",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        if index == 1 or index % 20 == 0 or index == total:
            print(f"[{index}/{total}] {case.experiment} {case.level} {case.policy} seed={case.seed}: {elapsed:.2f}s")

    gz_handle.close()
    rmse_ts_handle.close()
    comparisons = paired_b3_gaps(
        raw_rows,
        match_keys=("experiment", "level", "seed", "demand_condition"),
    )
    _write_csv(output / "b3_comparisons.csv", comparisons)
    group_keys = ("experiment", "level", "policy", "communication", "demand_condition")
    metrics = (
        "total_cost",
        "service_rate",
        "expired_rate",
        "duplicate_rate",
        "mean_response_minutes",
        "median_response_minutes",
        "p90_response_minutes",
        "critical_mean_response_minutes",
        "critical_service_rate",
        "mean_coverage",
        "utilization",
        "messages_per_incident",
        "duplicate_incidents",
        "expired",
        "demand_rmse",
        "b3_cost_gap_absolute",
        "b3_cost_gap_relative",
        "b3_service_rate_difference",
        "b3_coverage_difference",
    )
    summary_rows: list[dict[str, object]] = []
    for metric in metrics:
        summary_rows.extend(
            summarize_by(comparisons, group_keys, metric, bootstrap_resamples, seed=base.n_ambulances + len(metric))
        )
    _write_csv(output / "summary_metrics.csv", summary_rows)
    manifest["completed_case_count"] = len(raw_rows)
    manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["total_wall_seconds"] = sum(float(row["wall_seconds"]) for row in raw_rows)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    from .plotting import create_experiment_plots

    create_experiment_plots(summary_rows, output / "plots")
    run_unilateral_deviations(project_root, output / "deviations", base, seed_list)
    return output


def run_unilateral_deviations(
    project_root: str | Path,
    output_dir: str | Path,
    config: ScenarioConfig,
    seeds: Iterable[int],
    communication: str = "full",
    bootstrap_resamples: int = 2_000,
) -> Path:
    """Compare BID against one agent at a time replacing its bid with nearest/time-only."""
    from .simulator import RunSettings, simulate

    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty deviation directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    source_root = Path(project_root).resolve()
    seed_list = tuple(int(seed) for seed in seeds)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": _git_revision(source_root),
        "source_sha256": _source_manifest(source_root),
        "seeds": seed_list,
        "analysis": "restricted empirical unilateral-deviation analysis (nearest-time-only rule)",
        "deviation_rule": "one ambulance substitutes the alpha*K*response time-only bid; all other agents use BID",
        "communication": communication,
        "epsilon_interpretation": "maximum over agents of mean team-payoff improvement; not an equilibrium proof",
        "config": _config_dict(config),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    case_rows: list[dict[str, Any]] = []
    log_path = output / "run.log.jsonl"
    for seed in seed_list:
        baseline = simulate(
            config,
            RunSettings("BID", communication, seed=seed, scenario_id="unilateral-deviation"),
        )
        for agent_id in range(config.n_ambulances):
            started = time.perf_counter()
            deviation = simulate(
                config,
                RunSettings(
                    "BID",
                    communication,
                    seed=seed,
                    scenario_id="unilateral-deviation",
                    deviator_id=agent_id,
                    deviation_rule="nearest",
                ),
            )
            elapsed = time.perf_counter() - started
            improvement = baseline.total_cost - deviation.total_cost
            case_rows.append(
                {
                    "seed": seed,
                    "deviator_id": agent_id,
                    "deviation_rule": "nearest_time_only_bid",
                    "communication": communication,
                    "baseline_cost": baseline.total_cost,
                    "deviation_cost": deviation.total_cost,
                    "team_payoff_improvement": improvement,
                    "deviation_service_rate": deviation.service_rate,
                    "deviation_duplicate_incidents": deviation.duplicate_incidents,
                    "wall_seconds": elapsed,
                }
            )
            _append_csv(output / "deviation_cases.csv", case_rows[-1])
            with log_path.open("a", encoding="utf-8") as log:
                log.write(
                    json.dumps(
                        {
                            "seed": seed,
                            "deviator_id": agent_id,
                            "improvement": improvement,
                            "status": "completed",
                            "wall_seconds": elapsed,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
    summary = compute_unilateral_deviation_statistics(
        case_rows,
        resamples=bootstrap_resamples,
        confidence=0.95,
        seed=7341,
    )
    _write_csv(output / "deviation_summary.csv", summary)
    manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["case_count"] = len(case_rows)
    manifest["total_wall_seconds"] = sum(float(row["wall_seconds"]) for row in case_rows)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return output


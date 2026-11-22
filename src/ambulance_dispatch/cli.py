"""Command-line entry points for single runs and experiment suites."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .config import ScenarioConfig
from .experiments import run_experiment_suite
from .simulator import COMMUNICATION_REGIMES, POLICIES, RunSettings, simulate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ambulance-dispatch")
    commands = parser.add_subparsers(dest="command", required=True)

    single = commands.add_parser("simulate", help="run one reproducible episode")
    single.add_argument("--policy", choices=POLICIES, default="BID")
    single.add_argument("--communication", choices=COMMUNICATION_REGIMES, default="full")
    single.add_argument("--seed", type=int, default=0)
    single.add_argument("--horizon", type=float, default=600.0)
    single.add_argument("--ambulances", type=int, default=5)
    single.add_argument("--rate", type=float, default=5.0)
    single.add_argument("--pattern", choices=("uniform", "hotspots", "shifting"), default="hotspots")
    single.add_argument("--oracle-demand", action="store_true")

    suite = commands.add_parser("experiments", help="run experiment families")
    suite.add_argument("--profile", choices=("quick", "full"), default="quick")
    suite.add_argument("--seeds", type=int, help="number of paired seeds (default: 1 quick, 20 full)")
    suite.add_argument("--seed-start", type=int, default=1000)
    suite.add_argument("--horizon", type=float, help="arrival horizon in minutes (default: 600 quick, 6000 full)")
    suite.add_argument("--ambulances", type=int, default=5)
    suite.add_argument("--rate", type=float, default=5.0)
    suite.add_argument("--pattern", choices=("uniform", "hotspots", "shifting"), default="hotspots")
    suite.add_argument(
        "--experiment",
        choices=("exp1", "exp2", "exp3", "exp4", "exp4b", "exp4c", "exp5", "exp5b", "exp6", "exp7"),
        action="append",
    )
    suite.add_argument("--output-dir", type=Path)
    suite.add_argument("--bootstrap-resamples", type=int, default=2000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "simulate":
        config = replace(
            ScenarioConfig(),
            horizon_minutes=args.horizon,
            n_ambulances=args.ambulances,
            total_rate_per_hour=args.rate,
            demand_pattern=args.pattern,
        )
        result = simulate(
            config,
            RunSettings(
                policy=args.policy,
                communication=args.communication,
                oracle_demand=args.oracle_demand,
                seed=args.seed,
                scenario_id="cli-single",
            ),
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0

    seed_count = args.seeds if args.seeds is not None else (1 if args.profile == "quick" else 20)
    horizon = args.horizon if args.horizon is not None else (600.0 if args.profile == "quick" else 6000.0)
    config = replace(
        ScenarioConfig(),
        horizon_minutes=horizon,
        n_ambulances=args.ambulances,
        total_rate_per_hour=args.rate,
        demand_pattern=args.pattern,
    )
    seeds = range(args.seed_start, args.seed_start + seed_count)
    if args.output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = Path("results") / f"{args.profile}_{stamp}"
    else:
        output = args.output_dir
    result_path = run_experiment_suite(
        Path.cwd(),
        output,
        config,
        seeds,
        selected=set(args.experiment) if args.experiment else None,
        bootstrap_resamples=args.bootstrap_resamples,
    )
    print(f"Results written to {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


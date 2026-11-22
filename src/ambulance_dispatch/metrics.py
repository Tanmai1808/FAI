"""Paired benchmark gaps, confidence intervals, and tabular summaries."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from math import nan
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class SignedGap:
    absolute: float
    relative: float | None


def signed_cost_gap(policy_cost: float, benchmark_cost: float) -> SignedGap:
    """Signed empirical cost difference versus B3; ratio is undefined at zero cost."""
    difference = policy_cost - benchmark_cost
    relative = difference / benchmark_cost if benchmark_cost > 0 else None
    return SignedGap(difference, relative)


def signed_metric_difference(policy_value: float, benchmark_value: float) -> float:
    """Signed raw difference for higher-is-better metrics (policy minus benchmark)."""
    return policy_value - benchmark_value


def signed_relative_loss_gap(policy_value: float, benchmark_value: float) -> float | None:
    """Relative gap for higher-is-better metrics after converting to loss 1-value."""
    policy_loss = 1.0 - policy_value
    benchmark_loss = 1.0 - benchmark_value
    if benchmark_loss == 0:
        return None
    return (policy_loss - benchmark_loss) / benchmark_loss


def bootstrap_mean_interval(
    values: Sequence[float] | Iterable[float],
    confidence: float = 0.95,
    resamples: int = 2_000,
    seed: int = 0,
) -> tuple[float, float, float, int]:
    """Percentile bootstrap interval for a sample mean, using only the standard library."""
    data = [float(value) for value in values]
    if not data:
        return nan, nan, nan, 0
    if not 0 < confidence < 1 or resamples < 1:
        raise ValueError("confidence must be in (0, 1) and resamples positive")
    mean = sum(data) / len(data)
    if len(data) == 1:
        return mean, mean, mean, 1
    rng = random.Random(seed)
    samples = []
    n = len(data)
    for _ in range(resamples):
        samples.append(sum(data[rng.randrange(n)] for _ in range(n)) / n)
    samples.sort()
    tail = (1.0 - confidence) / 2.0

    def quantile(probability: float) -> float:
        position = probability * (len(samples) - 1)
        low = int(position)
        high = min(low + 1, len(samples) - 1)
        fraction = position - low
        return samples[low] * (1.0 - fraction) + samples[high] * fraction

    return mean, quantile(tail), quantile(1.0 - tail), n


def paired_b3_gaps(
    rows: Sequence[Mapping[str, object]],
    match_keys: tuple[str, ...] = ("experiment", "level", "seed", "demand_knowledge"),
) -> list[dict[str, object]]:
    """Attach signed cost and service gaps to each non-B3 record with a matched B3 row."""
    benchmarks: dict[tuple[object, ...], Mapping[str, object]] = {}
    for row in rows:
        if row.get("policy") == "B3":
            key = tuple(row.get(name) for name in match_keys)
            benchmarks[key] = row
    result = []
    for original in rows:
        row = dict(original)
        key = tuple(row.get(name) for name in match_keys)
        benchmark = benchmarks.get(key)
        if row.get("policy") != "B3" and benchmark is not None:
            gap = signed_cost_gap(float(row["total_cost"]), float(benchmark["total_cost"]))
            row["b3_cost_gap_absolute"] = gap.absolute
            row["b3_cost_gap_relative"] = gap.relative
            row["b3_service_rate_difference"] = signed_metric_difference(
                float(row["service_rate"]), float(benchmark["service_rate"])
            )
            row["b3_coverage_difference"] = signed_metric_difference(
                float(row["mean_coverage"]), float(benchmark["mean_coverage"])
            )
        elif row.get("policy") == "B3":
            row["b3_cost_gap_absolute"] = 0.0
            row["b3_cost_gap_relative"] = 0.0 if float(row["total_cost"]) > 0 else None
            row["b3_service_rate_difference"] = 0.0
            row["b3_coverage_difference"] = 0.0
        result.append(row)
    return result


def summarize_by(
    rows: Sequence[Mapping[str, object]],
    group_keys: tuple[str, ...],
    metric: str,
    resamples: int = 2_000,
    seed: int = 0,
) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(metric)
        if value is None:
            continue
        groups[tuple(row.get(key) for key in group_keys)].append(float(value))
    summaries = []
    for key, values in sorted(groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
        mean, low, high, n = bootstrap_mean_interval(values, resamples=resamples, seed=seed)
        summary = dict(zip(group_keys, key))
        summary.update({"metric": metric, "mean": mean, "ci95_low": low, "ci95_high": high, "n": n})
        summaries.append(summary)
    return summaries


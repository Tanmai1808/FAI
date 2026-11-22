"""Reproducible piecewise-Poisson demand scenarios."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .model import Incident, RateInterval


def _normalized_rates(weights: list[float], total_rate_per_hour: float) -> tuple[float, ...]:
    total = sum(weights)
    if total <= 0 or total_rate_per_hour < 0:
        raise ValueError("rate weights must be positive and total rate nonnegative")
    return tuple(total_rate_per_hour * weight / total for weight in weights)


def build_rate_schedule(
    n_zones: int,
    horizon_minutes: float,
    total_rate_per_hour: float,
    pattern: str = "uniform",
) -> tuple[RateInterval, ...]:
    """Build uniform, fixed-hotspot, or midpoint-shifting rates with fixed total rate."""
    if n_zones < 1 or horizon_minutes <= 0:
        raise ValueError("zone count and horizon must be positive")
    if pattern == "uniform":
        rates = _normalized_rates([1.0] * n_zones, total_rate_per_hour)
        return (RateInterval(0.0, horizon_minutes, rates),)
    if pattern not in {"hotspots", "shifting"}:
        raise ValueError(f"unknown demand pattern: {pattern}")

    # Fixed IDs make scenarios stable across Python versions and machines.
    center = n_zones // 2
    hot_a = {center, max(0, center - 1), min(n_zones - 1, center + 1)}
    hot_b = {0, n_zones - 1, n_zones // 3}

    def make(hot: set[int]) -> tuple[float, ...]:
        return _normalized_rates([4.0 if z in hot else 1.0 for z in range(n_zones)], total_rate_per_hour)

    first = make(hot_a)
    if pattern == "hotspots":
        return (RateInterval(0.0, horizon_minutes, first),)
    midpoint = horizon_minutes / 2.0
    second = make(hot_b)
    return (RateInterval(0.0, midpoint, first), RateInterval(midpoint, horizon_minutes, second))


def _sample_category(rng: random.Random, probabilities: tuple[float, ...]) -> int:
    draw = rng.random()
    cumulative = 0.0
    for index, probability in enumerate(probabilities, start=1):
        cumulative += probability
        if draw < cumulative or index == len(probabilities):
            return index
    raise AssertionError("unreachable category sample")


def generate_incident_tape(
    rate_schedule: tuple[RateInterval, ...],
    severity_probabilities: tuple[float, ...],
    seed: int,
) -> tuple[Incident, ...]:
    """Sample independent zone-wise Poisson processes and sort the resulting events."""
    if len(severity_probabilities) != 5 or abs(sum(severity_probabilities) - 1.0) > 1e-9:
        raise ValueError("severity probabilities must contain five values summing to one")
    rng = random.Random(seed)
    raw: list[tuple[float, int, int]] = []
    for interval in rate_schedule:
        for zone, rate_per_hour in enumerate(interval.rates_per_hour):
            if rate_per_hour < 0:
                raise ValueError("arrival rates cannot be negative")
            if rate_per_hour == 0:
                continue
            time = interval.start_minute
            rate_per_minute = rate_per_hour / 60.0
            while True:
                time += rng.expovariate(rate_per_minute)
                if time >= interval.end_minute:
                    break
                raw.append((time, zone, _sample_category(rng, severity_probabilities)))
    raw.sort(key=lambda row: (row[0], row[1], row[2]))
    return tuple(Incident(i, time, zone, severity) for i, (time, zone, severity) in enumerate(raw))


@dataclass
class DemandTape:
    incidents: tuple[Incident, ...]
    rate_schedule: tuple[RateInterval, ...]

    def true_rates_at(self, minute: float) -> tuple[float, ...]:
        for interval in self.rate_schedule:
            if interval.start_minute <= minute < interval.end_minute:
                return interval.rates_per_hour
        if self.rate_schedule and minute == self.rate_schedule[-1].end_minute:
            return self.rate_schedule[-1].rates_per_hour
        raise ValueError(f"no demand rate is defined at minute {minute}")


"""Shared proposal-consistent response and coverage cost calculations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..config import Weights
from ..graph import City


@dataclass(frozen=True)
class MarginalCoverage:
    outside_home_expected_calls: float
    home_expected_calls: float


def marginal_coverage_cost(
    city: City,
    agent_id: int,
    home_zone: int,
    own_node: int,
    believed_idle_positions: Mapping[int, int],
    rates_per_hour: tuple[float, ...] | list[float],
    busy_minutes: float,
    coverage_radius_minutes: float,
) -> MarginalCoverage:
    """Expected uncovered demand over busy time, partitioned by the agent's home zone."""
    if agent_id not in believed_idle_positions:
        positions = dict(believed_idle_positions)
        positions[agent_id] = own_node
    else:
        positions = dict(believed_idle_positions)
        positions[agent_id] = own_node
    before_positions = tuple(positions.values())
    after_positions = tuple(node for other, node in positions.items() if other != agent_id)
    busy_hours = busy_minutes / 60.0
    outside = 0.0
    home = 0.0
    for zone, rate in enumerate(rates_per_hour):
        if zone == home_zone:
            home += busy_hours * rate
            continue
        was_covered = city.covered(before_positions, zone, coverage_radius_minutes)
        remains_covered = city.covered(after_positions, zone, coverage_radius_minutes)
        loss = 1.0 if was_covered and not remains_covered else 0.0
        lost_calls = busy_hours * rate * loss
        outside += lost_calls
    return MarginalCoverage(outside, home)


def weighted_dispatch_cost(
    response_minutes: float,
    criticality: int,
    coverage: MarginalCoverage,
    weights: Weights,
) -> float:
    return (
        weights.alpha * criticality * response_minutes
        + weights.beta * coverage.outside_home_expected_calls
        + weights.gamma * coverage.home_expected_calls
    )


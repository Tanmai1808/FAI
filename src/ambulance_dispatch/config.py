"""Typed configuration for scenarios and policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class Weights:
    alpha: float = 1.0
    beta: float = 8.0
    gamma: float = 8.0
    rho: float = 120.0


@dataclass(frozen=True)
class ScenarioConfig:
    width: int = 5
    height: int = 5
    edge_minutes: float = 2.0
    n_ambulances: int = 5
    horizon_minutes: float = 6_000.0
    total_rate_per_hour: float = 5.0
    demand_pattern: str = "hotspots"
    severity_probabilities: tuple[float, ...] = (0.35, 0.25, 0.20, 0.13, 0.07)
    deadlines_minutes: tuple[float, ...] = (60.0, 45.0, 30.0, 20.0, 15.0)
    on_scene_minutes: float = 20.0
    coverage_radius_minutes: float = 8.0
    learning_eta: float = 0.25
    learning_bin_minutes: float = 60.0
    prior_total_rate_per_hour: float = 5.0
    status_ttl_minutes: float = 120.0
    reposition_epsilon: float = 0.01
    weights: Weights = field(default_factory=Weights)

    def __post_init__(self) -> None:
        if self.width < 2 or self.height < 2:
            raise ValueError("city dimensions must each be at least 2")
        if self.n_ambulances < 1:
            raise ValueError("at least one ambulance is required")
        if self.horizon_minutes <= 0 or self.edge_minutes <= 0:
            raise ValueError("horizon and edge travel time must be positive")
        if len(self.severity_probabilities) != 5 or any(p < 0 for p in self.severity_probabilities):
            raise ValueError("severity probabilities must contain five nonnegative values")
        if abs(sum(self.severity_probabilities) - 1.0) > 1e-9:
            raise ValueError("severity probabilities must sum to 1")
        if len(self.deadlines_minutes) != 5 or any(d <= 0 for d in self.deadlines_minutes):
            raise ValueError("one positive deadline is required for each criticality")
        if not 0 < self.learning_eta <= 1:
            raise ValueError("learning_eta must be in (0, 1]")
        if self.learning_bin_minutes <= 0:
            raise ValueError("learning_bin_minutes must be positive")

    @property
    def n_zones(self) -> int:
        return self.width * self.height

    def deadline_for(self, criticality: int) -> float:
        return self.deadlines_minutes[criticality - 1]


def severity_mix(name: str) -> tuple[float, ...]:
    """Return predeclared low-, balanced-, or high-criticality probabilities."""
    mixes: Mapping[str, tuple[float, ...]] = {
        "low-heavy": (0.55, 0.23, 0.12, 0.07, 0.03),
        "balanced": (0.20, 0.20, 0.20, 0.20, 0.20),
        "high-heavy": (0.05, 0.10, 0.15, 0.25, 0.45),
    }
    try:
        return mixes[name]
    except KeyError as exc:
        raise ValueError(f"unknown severity mix: {name}") from exc

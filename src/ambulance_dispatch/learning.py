"""Causal discounted rate estimates and direct-observation ownership."""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import City
from .model import Ambulance


def assign_zone_observers(city: City, home_nodes: dict[int, int]) -> dict[int, int]:
    """Assign every zone to its nearest fixed home, resolving ties by ambulance ID."""
    if not home_nodes:
        raise ValueError("at least one observer is required")
    return {
        zone: min(home_nodes, key=lambda agent_id: (city.travel(home_nodes[agent_id], zone), agent_id))
        for zone in city.nodes
    }


@dataclass
class DiscountedRateLearner:
    agent_id: int
    n_zones: int
    owned_zones: tuple[int, ...]
    prior_per_hour: float
    eta: float
    bin_minutes: float
    rates: list[float] = field(init=False)
    counts: list[int] = field(init=False)
    last_remote_bin: dict[tuple[int, int], int] = field(default_factory=dict)
    observations: list[tuple[float, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.n_zones < 1 or self.prior_per_hour < 0:
            raise ValueError("zone count must be positive and prior nonnegative")
        if not 0 < self.eta <= 1 or self.bin_minutes <= 0:
            raise ValueError("eta must be in (0, 1] and bin duration positive")
        if any(zone < 0 or zone >= self.n_zones for zone in self.owned_zones):
            raise ValueError("owned zone outside learner range")
        self.rates = [float(self.prior_per_hour)] * self.n_zones
        self.counts = [0] * self.n_zones

    def observe_arrival(self, zone: int, time_minute: float) -> None:
        """Only an owning sensor learns directly from an arrival."""
        if zone not in self.owned_zones:
            return
        self.counts[zone] += 1
        self.observations.append((time_minute, zone))

    def close_bin(self, bin_id: int) -> tuple[tuple[int, float], ...]:
        """Update owned zone rates from counts per hour and return publishable estimates."""
        hours = self.bin_minutes / 60.0
        updates = []
        for zone in self.owned_zones:
            observed_rate = self.counts[zone] / hours
            self.rates[zone] = (1.0 - self.eta) * self.rates[zone] + self.eta * observed_rate
            self.counts[zone] = 0
            updates.append((zone, self.rates[zone]))
        return tuple(updates)

    def receive_rate(self, sender: int, zone: int, bin_id: int, rate_per_hour: float) -> bool:
        """Install a fresh zone-owner estimate once; stale or duplicate bins are ignored."""
        if not 0 <= zone < self.n_zones or rate_per_hour < 0:
            raise ValueError("invalid remote rate update")
        key = (sender, zone)
        if bin_id <= self.last_remote_bin.get(key, -1):
            return False
        self.last_remote_bin[key] = bin_id
        self.rates[zone] = float(rate_per_hour)
        return True

    def rmse(self, true_rates: tuple[float, ...] | list[float]) -> float:
        if len(true_rates) != self.n_zones:
            raise ValueError("true rate vector has the wrong size")
        return (sum((estimate - truth) ** 2 for estimate, truth in zip(self.rates, true_rates)) / self.n_zones) ** 0.5


def initialize_learners(
    ambulances: tuple[Ambulance, ...] | list[Ambulance],
    city: City,
    n_zones: int,
    prior_total_rate_per_hour: float,
    eta: float,
    bin_minutes: float,
) -> tuple[dict[int, DiscountedRateLearner], dict[int, int]]:
    homes = {ambulance.ambulance_id: ambulance.home_zone for ambulance in ambulances}
    owners = assign_zone_observers(city, homes)
    by_agent = {
        ambulance.ambulance_id: tuple(zone for zone, owner in owners.items() if owner == ambulance.ambulance_id)
        for ambulance in ambulances
    }
    prior = prior_total_rate_per_hour / n_zones
    learners = {
        agent_id: DiscountedRateLearner(agent_id, n_zones, by_agent[agent_id], prior, eta, bin_minutes)
        for agent_id in homes
    }
    return learners, owners


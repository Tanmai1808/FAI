"""Decentralized bid scoring and local-minimum commitment rule."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..config import Weights
from ..graph import City
from ..model import Ambulance, Incident
from .costs import marginal_coverage_cost, weighted_dispatch_cost


@dataclass(frozen=True)
class Bid:
    ambulance_id: int
    cost: float
    staging_node: int
    eligible: bool = True

    @property
    def ordering_key(self) -> tuple[float, int]:
        return self.cost, self.ambulance_id


def compute_bid(
    city: City,
    ambulance: Ambulance,
    incident: Incident,
    now: float,
    deadline_minutes: float,
    on_scene_minutes: float,
    weights: Weights,
    believed_idle_positions: Mapping[int, int],
    estimated_rates_per_hour: tuple[float, ...] | list[float],
    coverage_radius_minutes: float,
) -> Bid | None:
    """Return the agent-local score if it can reach the call before its deadline."""
    if ambulance.status.value != "idle":
        return None
    travel = city.travel(ambulance.node, incident.zone)
    response = now - incident.arrival_minute + travel
    if response > deadline_minutes:
        return None
    busy = 2.0 * travel + on_scene_minutes
    marginal = marginal_coverage_cost(
        city,
        ambulance.ambulance_id,
        ambulance.home_zone,
        ambulance.node,
        believed_idle_positions,
        estimated_rates_per_hour,
        busy,
        coverage_radius_minutes,
    )
    cost = weighted_dispatch_cost(response, incident.criticality, marginal, weights)
    return Bid(ambulance.ambulance_id, cost, ambulance.node)


def local_minimum_winners(
    bids: Mapping[int, Bid],
    received_by_agent: Mapping[int, tuple[Bid, ...] | list[Bid]],
) -> tuple[int, ...]:
    """Agents commit iff their own bid is minimal among their own and heard bids."""
    winners = []
    for agent_id, own_bid in sorted(bids.items()):
        heard = {own_bid.ambulance_id: own_bid}
        for bid in received_by_agent.get(agent_id, ()):
            heard[bid.ambulance_id] = bid
        if min(heard.values(), key=lambda bid: bid.ordering_key).ambulance_id == agent_id:
            winners.append(agent_id)
    return tuple(winners)


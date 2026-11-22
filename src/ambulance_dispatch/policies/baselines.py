"""B1/B2 responder selection and B3 assignment primitives."""

from __future__ import annotations

from collections.abc import Sequence

from ..graph import City
from ..model import Ambulance, Incident


def feasible_ambulances(
    city: City,
    incident: Incident,
    now: float,
    deadline_minutes: float,
    ambulances: Sequence[Ambulance],
) -> tuple[Ambulance, ...]:
    remaining = deadline_minutes - (now - incident.arrival_minute)
    return tuple(
        ambulance
        for ambulance in ambulances
        if ambulance.status.value == "idle" and city.travel(ambulance.node, incident.zone) <= remaining
    )


def select_b1(city: City, incident: Incident, candidates: Sequence[Ambulance]) -> Ambulance | None:
    """Nearest feasible responder; ties resolve by ambulance ID."""
    if not candidates:
        return None
    return min(candidates, key=lambda ambulance: (city.travel(ambulance.node, incident.zone), ambulance.ambulance_id))


def select_b2(city: City, incident: Incident, candidates: Sequence[Ambulance], alpha: float = 1.0) -> Ambulance | None:
    """Criticality-aware time baseline; the scalar alpha is retained from the proposal."""
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda ambulance: (alpha * incident.criticality * city.travel(ambulance.node, incident.zone), ambulance.ambulance_id),
    )


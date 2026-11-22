"""Core immutable incident and mutable ambulance state records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Incident:
    incident_id: int
    arrival_minute: float
    zone: int
    criticality: int


class AmbulanceStatus(str, Enum):
    IDLE = "idle"
    RESPONSE_BUSY = "response_busy"
    REPOSITION_BUSY = "reposition_busy"


@dataclass
class Ambulance:
    ambulance_id: int
    home_zone: int
    node: int
    status: AmbulanceStatus = AmbulanceStatus.IDLE
    free_at: float = 0.0
    dispatch_origin: int | None = None
    target_node: int | None = None


@dataclass(frozen=True)
class RateInterval:
    start_minute: float
    end_minute: float
    rates_per_hour: tuple[float, ...]


@dataclass(frozen=True)
class IncidentOutcome:
    incident_id: int
    arrival_minute: float
    zone: int
    criticality: int
    deadline_minute: float
    response_minute: float | None
    responder_ids: tuple[int, ...]
    expired: bool = False

    @property
    def missed(self) -> bool:
        return self.expired


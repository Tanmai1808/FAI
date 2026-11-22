"""Zero-latency, directed message delivery with radius and independent loss."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from math import inf
from typing import Any

from .graph import City


@dataclass(frozen=True)
class Message:
    sender: int
    receiver: int
    kind: str
    sent_at: float
    payload: Any


class CommunicationChannel:
    """A message is sent only on a reachable directed link; each packet is dropped independently."""

    def __init__(
        self,
        city: City,
        regime: str = "full",
        radius_minutes: float = inf,
        loss_probability: float = 0.0,
        seed: int = 0,
    ) -> None:
        if regime not in {"full", "radius-limited", "lossy", "none"}:
            raise ValueError(f"unknown communication regime: {regime}")
        if not 0.0 <= loss_probability <= 1.0:
            raise ValueError("loss_probability must be in [0, 1]")
        if radius_minutes <= 0:
            raise ValueError("radius_minutes must be positive")
        self.city = city
        self.regime = regime
        self.radius_minutes = inf if regime in {"full", "lossy"} else radius_minutes
        self.loss_probability = loss_probability if regime == "lossy" else (1.0 if regime == "none" else 0.0)
        self.rng = random.Random(seed)
        self.sent_by_kind: Counter[str] = Counter()
        self.delivered_by_kind: Counter[str] = Counter()

    @property
    def messages_sent(self) -> int:
        return sum(self.sent_by_kind.values())

    @property
    def messages_delivered(self) -> int:
        return sum(self.delivered_by_kind.values())

    def send(
        self,
        sender: int,
        receiver: int,
        sender_node: int,
        receiver_node: int,
        kind: str,
        payload: Any,
        now: float,
    ) -> Message | None:
        if sender == receiver or self.regime == "none":
            return None
        if self.city.travel(sender_node, receiver_node) > self.radius_minutes:
            return None
        self.sent_by_kind[kind] += 1
        if self.rng.random() < self.loss_probability:
            return None
        self.delivered_by_kind[kind] += 1
        return Message(sender, receiver, kind, now, payload)

    def broadcast(
        self,
        sender: int,
        positions: dict[int, int],
        recipients: tuple[int, ...] | list[int],
        kind: str,
        payload: Any,
        now: float,
    ) -> tuple[Message, ...]:
        delivered = []
        for receiver in sorted(recipients):
            if receiver == sender:
                continue
            message = self.send(
                sender,
                receiver,
                positions[sender],
                positions[receiver],
                kind,
                payload,
                now,
            )
            if message is not None:
                delivered.append(message)
        return tuple(delivered)


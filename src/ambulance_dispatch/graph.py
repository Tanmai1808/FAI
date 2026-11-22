"""Synthetic weighted city graph and shortest-path utilities."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field


@dataclass
class City:
    adjacency: dict[int, list[tuple[int, float]]]
    coordinates: dict[int, tuple[int, int]]
    distances: dict[int, dict[int, float]] = field(init=False, repr=False)
    _coverage_masks: dict[tuple[int, float], int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.adjacency:
            raise ValueError("city graph cannot be empty")
        if set(self.adjacency) != set(self.coordinates):
            raise ValueError("every graph node must have a coordinate")
        self.distances = {node: self._dijkstra(node) for node in self.adjacency}
        self._coverage_masks = {}
        if any(len(row) != len(self.adjacency) for row in self.distances.values()):
            raise ValueError("city graph must be connected")

    @classmethod
    def grid(cls, width: int = 5, height: int = 5, edge_minutes: float = 2.0) -> "City":
        if width < 1 or height < 1 or edge_minutes <= 0:
            raise ValueError("grid dimensions and edge travel time must be positive")
        coordinates = {y * width + x: (x, y) for y in range(height) for x in range(width)}
        adjacency = {node: [] for node in coordinates}
        for node, (x, y) in coordinates.items():
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    other = ny * width + nx
                    adjacency[node].append((other, float(edge_minutes)))
        return cls(adjacency, coordinates)

    @property
    def nodes(self) -> tuple[int, ...]:
        return tuple(sorted(self.adjacency))

    def _dijkstra(self, source: int) -> dict[int, float]:
        distance = {node: float("inf") for node in self.adjacency}
        distance[source] = 0.0
        queue = [(0.0, source)]
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != distance[node]:
                continue
            for neighbor, edge_cost in self.adjacency[node]:
                if edge_cost <= 0:
                    raise ValueError("all edge travel times must be positive")
                candidate = cost + edge_cost
                if candidate < distance[neighbor]:
                    distance[neighbor] = candidate
                    heapq.heappush(queue, (candidate, neighbor))
        return distance

    def travel(self, origin: int, destination: int) -> float:
        try:
            return self.distances[origin][destination]
        except KeyError as exc:
            raise ValueError(f"unknown city node in travel query: {exc.args[0]}") from exc

    def covered(self, positions: list[int] | tuple[int, ...], zone: int, radius_minutes: float) -> bool:
        return any(self.travel(position, zone) <= radius_minutes for position in positions)

    def _coverage_mask(self, node: int, radius_minutes: float) -> int:
        key = (node, float(radius_minutes))
        mask = self._coverage_masks.get(key)
        if mask is None:
            mask = 0
            for zone in self.adjacency:
                if self.travel(node, zone) <= radius_minutes:
                    mask |= 1 << zone
            self._coverage_masks[key] = mask
        return mask

    def coverage_fraction(
        self, positions: list[int] | tuple[int, ...], rates: tuple[float, ...] | list[float], radius_minutes: float
    ) -> float:
        total = sum(rates)
        if len(rates) != len(self.adjacency):
            raise ValueError("demand rate vector must match city zones")
        if total <= 0:
            return 1.0
        mask = 0
        for position in positions:
            mask |= self._coverage_mask(position, radius_minutes)
        covered_demand = 0.0
        while mask:
            bit = mask & -mask
            zone = bit.bit_length() - 1
            covered_demand += rates[zone]
            mask ^= bit
        return covered_demand / total


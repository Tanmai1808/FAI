"""Centralized B3 assignment helper. The caller supplies heuristic pairwise costs."""

from __future__ import annotations

from math import inf
from typing import Sequence


def hungarian_min_cost(costs: Sequence[Sequence[float]]) -> tuple[tuple[int, int], ...]:
    """Return a minimum-cost assignment for every row; requires rows <= columns."""
    n = len(costs)
    if n == 0:
        return ()
    m = len(costs[0])
    if m < n or any(len(row) != m for row in costs):
        raise ValueError("cost matrix must be rectangular with rows <= columns")
    if any(value != value for row in costs for value in row):
        raise ValueError("cost matrix cannot contain NaN")

    # Potentials-based O(n^2 m) Hungarian algorithm, 1-indexed internally.
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = float(costs[i0 - 1][j - 1]) - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            if delta == inf:
                raise ValueError("assignment problem has no finite augmenting path")
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [(p[j] - 1, j - 1) for j in range(1, m + 1) if p[j] != 0]
    return tuple(sorted(assignment))


def assign_b3(
    pairwise_costs: Sequence[Sequence[float]],
    miss_penalty: float,
    idle_penalty: float = 0.0,
) -> tuple[tuple[int, int], ...]:
    """Assign ambulances to calls or dummy jobs; dummy ambulances leave calls unmatched."""
    n_ambulances = len(pairwise_costs)
    n_calls = len(pairwise_costs[0]) if n_ambulances else 0
    if any(len(row) != n_calls for row in pairwise_costs):
        raise ValueError("pairwise cost rows must have equal length")
    if miss_penalty < 0 or idle_penalty < 0:
        raise ValueError("dummy penalties must be nonnegative")
    if n_ambulances == 0 or n_calls == 0:
        return ()
    size = n_ambulances + n_calls
    finite_costs = [float(value) for row in pairwise_costs for value in row if value != inf]
    scale = max([miss_penalty, idle_penalty, *finite_costs], default=1.0)
    big = scale * (size + 2) + 1.0
    matrix = [[0.0] * size for _ in range(size)]
    # Real ambulance rows: incident costs, then one idle dummy column per ambulance.
    for i in range(n_ambulances):
        for j in range(n_calls):
            cost = float(pairwise_costs[i][j])
            matrix[i][j] = cost if cost < big else big
        for j in range(n_calls, size):
            matrix[i][j] = idle_penalty
    # Dummy ambulance rows: a miss penalty for each call, zero for dummy columns.
    for i in range(n_ambulances, size):
        for j in range(n_calls):
            matrix[i][j] = miss_penalty
        for j in range(n_calls, size):
            matrix[i][j] = 0.0
    assignment = hungarian_min_cost(matrix)
    return tuple(
        (ambulance, call)
        for ambulance, call in assignment
        if ambulance < n_ambulances and call < n_calls and matrix[ambulance][call] < big
    )


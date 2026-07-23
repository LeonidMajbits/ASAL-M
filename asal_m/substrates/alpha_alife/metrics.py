from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np


def compute_metrics(state: dict[str, Any]) -> dict[str, float]:
    lineage = state["lineage"]
    energy = state["energy"]
    resources = state["resources"]
    age = state["age"]
    alive = lineage > 0
    live_cells = int(alive.sum())
    total_cells = int(alive.size)

    occupancy = live_cells / max(1, total_cells)
    if live_cells == 0:
        return {
            "occupancy": 0.0,
            "diversity": 0.0,
            "lineages": 0.0,
            "lineage_entropy": 0.0,
            "mean_energy": 0.0,
            "resource_balance": float(resources.mean()),
            "mean_age": 0.0,
            "cluster_coherence": 0.0,
            "activity": float(state["last_change_rate"]),
            "birth_rate": 0.0,
            "death_rate": float(state["last_deaths"] / max(1, total_cells)),
        }

    live_lineages = lineage[alive]
    unique_lineages, counts = np.unique(live_lineages, return_counts=True)
    probabilities = counts / counts.sum()
    entropy = float(-(probabilities * np.log(probabilities + 1e-12)).sum())
    entropy /= float(np.log(max(2, unique_lineages.size)))

    return {
        "occupancy": float(occupancy),
        "diversity": float(min(1.0, unique_lineages.size / max(1, live_cells))),
        "lineages": float(unique_lineages.size),
        "lineage_entropy": float(entropy),
        "mean_energy": float(energy[alive].mean()),
        "resource_balance": float(resources.mean()),
        "mean_age": float(age[alive].mean()),
        "cluster_coherence": float(_largest_cluster_fraction(alive)),
        "activity": float(state["last_change_rate"]),
        "birth_rate": float(state["last_births"] / max(1, total_cells)),
        "death_rate": float(state["last_deaths"] / max(1, total_cells)),
    }


def _largest_cluster_fraction(mask: np.ndarray) -> float:
    live_cells = int(mask.sum())
    if live_cells == 0:
        return 0.0

    visited = np.zeros_like(mask, dtype=bool)
    largest = 0
    for row, col in np.argwhere(mask):
        if visited[row, col]:
            continue
        largest = max(largest, _bfs_cluster(mask, visited, int(row), int(col)))
    return largest / max(1, live_cells)


def _bfs_cluster(
    mask: np.ndarray, visited: np.ndarray, start_row: int, start_col: int
) -> int:
    queue: deque[tuple[int, int]] = deque([(start_row, start_col)])
    visited[start_row, start_col] = True
    size = 0
    max_row, max_col = mask.shape
    while queue:
        row, col = queue.popleft()
        size += 1
        for d_row, d_col in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n_row = (row + d_row) % max_row
            n_col = (col + d_col) % max_col
            if visited[n_row, n_col] or not mask[n_row, n_col]:
                continue
            visited[n_row, n_col] = True
            queue.append((n_row, n_col))
    return size

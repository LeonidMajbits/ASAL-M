from __future__ import annotations

from typing import Any

import numpy as np

from ..core.candidate import ScoredCandidate
from ..scoring.embeddings import embedding_distance


class NoveltyArchive:
    def __init__(self, capacity: int = 48, k_nearest: int = 5) -> None:
        self.capacity = capacity
        self.k_nearest = max(1, int(k_nearest))
        self.entries: list[ScoredCandidate] = []

    def novelty(self, embedding) -> float:
        """Mean distance to k nearest archive neighbors (standard QD-style novelty)."""
        if embedding is None or not self.entries:
            return 1.0
        distances = sorted(
            (
                embedding_distance(embedding, item.embedding)
                for item in self.entries
                if item.embedding is not None
            )
        )
        if not distances:
            return 1.0
        neighborhood = distances[: min(self.k_nearest, len(distances))]
        return float(max(0.0, min(1.0, sum(neighborhood) / len(neighborhood))))

    def add(self, entry: ScoredCandidate) -> bool:
        self.entries.append(entry)
        self.entries.sort(
            key=lambda item: item.score_components.get("novelty", 0.0),
            reverse=True,
        )
        retained = self.entries[: self.capacity]
        kept = entry in retained
        self.entries = retained
        return kept

    def sample_parent(self, rng: Any | None = None) -> ScoredCandidate | None:
        if not self.entries:
            return None
        top_band = self.entries[: max(1, len(self.entries) // 2)]
        if rng is None:
            return top_band[0]
        return top_band[int(np.asarray(rng.integers(0, len(top_band))).item())]

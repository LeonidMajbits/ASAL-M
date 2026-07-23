from __future__ import annotations

from typing import Any

import numpy as np

from ..core.candidate import ScoredCandidate
from ..scoring.embeddings import embedding_distance


class EliteArchive:
    def __init__(self, capacity: int = 24) -> None:
        self.capacity = capacity
        self.entries: list[ScoredCandidate] = []

    def add(self, entry: ScoredCandidate) -> bool:
        self.entries.append(entry)
        self.entries.sort(key=lambda item: item.total_score, reverse=True)
        retained = self.entries[: self.capacity]
        kept = entry in retained
        self.entries = retained
        return kept

    def best(self) -> ScoredCandidate | None:
        return self.entries[0] if self.entries else None

    def coverage_bonus(self, embedding) -> float:
        if embedding is None or not self.entries:
            return 0.5
        distances = [
            embedding_distance(embedding, item.embedding)
            for item in self.entries
            if item.embedding is not None
        ]
        if not distances:
            return 0.5
        return float(max(0.0, min(1.0, sum(distances) / len(distances))))

    def sample_parent(self, rng: Any | None = None) -> ScoredCandidate | None:
        if not self.entries:
            return None
        top_band = self.entries[: max(1, len(self.entries) // 3)]
        if rng is None:
            return top_band[0]
        return top_band[int(np.asarray(rng.integers(0, len(top_band))).item())]

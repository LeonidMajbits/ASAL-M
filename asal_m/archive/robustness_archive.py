from __future__ import annotations

from typing import Any

import numpy as np

from ..core.candidate import ScoredCandidate


class RobustnessArchive:
    def __init__(self, capacity: int = 24) -> None:
        self.capacity = capacity
        self.entries: list[ScoredCandidate] = []

    def add(self, entry: ScoredCandidate) -> bool:
        self.entries.append(entry)
        self.entries.sort(
            key=lambda item: item.score_components.get("robustness", 0.0),
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

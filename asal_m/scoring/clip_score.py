from __future__ import annotations

from typing import Mapping


def compute_target_fit(
    summary_metrics: Mapping[str, float], target_metrics: Mapping[str, float] | None
) -> float:
    if not target_metrics:
        return 0.0

    distances: list[float] = []
    for key, target in target_metrics.items():
        current = float(summary_metrics.get(key, 0.0))
        scale = max(0.1, abs(float(target)))
        distances.append(abs(current - float(target)) / scale)
    if not distances:
        return 0.0
    return max(0.0, 1.0 - sum(distances) / len(distances))

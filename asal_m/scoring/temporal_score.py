from __future__ import annotations

import numpy as np


def compute_temporal_scores(metrics_trace: list[dict[str, float]]) -> dict[str, float]:
    if not metrics_trace:
        return {"persistence": 0.0, "lineage_signal": 0.0, "temporal_coherence": 0.0}

    occupancy = np.asarray(
        [float(item.get("occupancy", 0.0)) for item in metrics_trace], dtype=float
    )
    diversity = np.asarray(
        [float(item.get("diversity", 0.0)) for item in metrics_trace], dtype=float
    )
    lineage_entropy = np.asarray(
        [float(item.get("lineage_entropy", 0.0)) for item in metrics_trace], dtype=float
    )
    activity = np.asarray(
        [float(item.get("activity", 0.0)) for item in metrics_trace], dtype=float
    )

    persistence = float(((occupancy > 0.02).mean() + occupancy.mean()) / 2.0)
    smoothness = 1.0 - float(
        np.clip(
            np.abs(np.diff(occupancy)).mean() if len(occupancy) > 1 else 0.0, 0.0, 1.0
        )
    )
    activity_balance = 1.0 - float(
        np.clip(abs(activity.mean() - 0.12) / 0.25, 0.0, 1.0)
    )
    lineage_signal = float(
        np.clip(0.5 * diversity.mean() + 0.5 * lineage_entropy.mean(), 0.0, 1.0)
    )

    return {
        "persistence": float(np.clip(persistence, 0.0, 1.0)),
        "lineage_signal": float(np.clip(lineage_signal, 0.0, 1.0)),
        "temporal_coherence": float(
            np.clip(0.6 * smoothness + 0.4 * activity_balance, 0.0, 1.0)
        ),
    }

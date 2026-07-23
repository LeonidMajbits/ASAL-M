from __future__ import annotations

import numpy as np

from ..core.candidate import RunArtifacts


def compute_artifact_penalty(run: RunArtifacts) -> float:
    frames = (
        np.asarray(run.frames, dtype=float) / 255.0
        if run.frames
        else np.zeros((0, 1, 1, 3), dtype=float)
    )
    if frames.size == 0:
        return 1.0

    grayscale = frames.mean(axis=-1)
    flicker = (
        float(np.abs(np.diff(grayscale, axis=0)).mean()) if len(grayscale) > 1 else 0.0
    )
    saturation = float(((grayscale < 0.02) | (grayscale > 0.98)).mean())
    occupancy = float(run.summary_metrics.get("occupancy", 0.0))
    diversity = float(run.summary_metrics.get("diversity", 0.0))
    collapse_penalty = 1.0 - max(
        occupancy, run.summary_metrics.get("survival_fraction", 0.0)
    )
    static_penalty = 1.0 if flicker < 0.002 and diversity < 0.1 else 0.0
    return float(
        np.clip(
            0.4 * collapse_penalty
            + 0.25 * flicker
            + 0.2 * saturation
            + 0.15 * static_penalty,
            0.0,
            1.0,
        )
    )

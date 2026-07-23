from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from ..core.candidate import CandidateConfig, RunArtifacts
from ..substrates import create_substrate


def compute_trajectory_quality_score(run: RunArtifacts) -> float:
    """Secondary visual/metric quality score from a single rollout.

    Not a holdout. Kept for cheap proxy signals and analysis only.
    """
    if not run.frames:
        return 0.0

    frames = np.asarray(run.frames, dtype=float) / 255.0
    grayscale = frames.mean(axis=-1)
    edge_density = (
        np.abs(np.diff(grayscale, axis=1)).mean()
        + np.abs(np.diff(grayscale, axis=2)).mean()
    ) / 2.0
    temporal_delta = (
        np.abs(np.diff(grayscale, axis=0)).mean() if len(grayscale) > 1 else 0.0
    )
    occupancy = float(run.summary_metrics.get("occupancy", 0.0))
    diversity = float(run.summary_metrics.get("diversity", 0.0))
    coherence = float(run.summary_metrics.get("cluster_coherence", 0.0))
    return float(
        np.clip(
            0.25 * occupancy
            + 0.25 * diversity
            + 0.2 * coherence
            + 0.15 * min(1.0, edge_density * 5.0)
            + 0.15 * min(1.0, temporal_delta * 5.0),
            0.0,
            1.0,
        )
    )


def compute_holdout_score(
    candidate: CandidateConfig,
    *,
    steps: int,
    holdout_seeds: list[int] | None = None,
    seed_offsets: list[int] | None = None,
) -> tuple[float, list[dict[str, Any]]]:
    """Evaluate the same candidate configuration on held-out seeds.

    Holdout means: fixed params/rules/environment/initial-condition *settings*,
    new random seeds that were not the discovery seed. This is independent of the
    original rollout frames.
    """
    if steps <= 0:
        return 0.0, []

    if holdout_seeds is None:
        offsets = seed_offsets if seed_offsets is not None else [101, 202, 303]
        candidate_seeds = [int(candidate.seed) + int(offset) for offset in offsets]
        # Avoid accidentally reusing the discovery seed if offsets ever include 0.
        candidate_seeds = [
            seed for seed in candidate_seeds if seed != int(candidate.seed)
        ]
        if not candidate_seeds:
            candidate_seeds = [int(candidate.seed) + 101]
    else:
        candidate_seeds = [int(seed) for seed in holdout_seeds]
        if int(candidate.seed) in candidate_seeds:
            raise ValueError("holdout_seeds must exclude the discovery seed")
        if not candidate_seeds:
            raise ValueError("holdout_seeds must contain at least one distinct seed")

    # Repeated seeds do not create independent evidence.
    candidate_seeds = list(dict.fromkeys(candidate_seeds))

    details: list[dict[str, Any]] = []
    scores: list[float] = []
    for seed in candidate_seeds:
        holdout_candidate = replace(candidate, seed=int(seed))
        substrate = create_substrate(holdout_candidate.substrate)
        substrate.reset(holdout_candidate.to_substrate_config(), holdout_candidate.seed)
        survived = 0
        for _ in range(steps):
            if substrate.is_extinct():
                break
            substrate.step()
            survived += 1
        metrics = substrate.extract_metrics()
        survival = survived / max(1, steps)
        score = float(
            np.clip(
                0.45 * survival
                + 0.3 * float(metrics.get("occupancy", 0.0))
                + 0.25 * float(metrics.get("diversity", 0.0)),
                0.0,
                1.0,
            )
        )
        scores.append(score)
        details.append(
            {
                "seed": int(seed),
                "survived_steps": survived,
                "requested_steps": steps,
                "metrics": metrics,
                "score": score,
            }
        )

    if not scores:
        return 0.0, details
    return float(sum(scores) / len(scores)), details

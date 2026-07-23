from __future__ import annotations

import numpy as np

from asal_m.archive import EliteArchive, NoveltyArchive, RobustnessArchive
from asal_m.core.candidate import CandidateConfig, RunArtifacts, ScoredCandidate


def _scored(
    score: float, novelty: float = 0.0, robustness: float = 0.0, seed: int = 0
) -> ScoredCandidate:
    candidate = CandidateConfig(
        substrate="alpha_alife", search_mode="frontier", seed=seed
    )
    run = RunArtifacts(
        candidate=candidate,
        executed_steps=1,
        frames=[],
        metrics_trace=[],
        state_snapshots=[],
        summary_metrics={},
        embedding=np.asarray([float(seed), 0.0, 1.0]),
    )
    return ScoredCandidate(
        run=run,
        total_score=score,
        score_components={"novelty": novelty, "robustness": robustness, "total": score},
    )


def test_elite_archive_respects_capacity() -> None:
    archive = EliteArchive(capacity=3)
    kept_flags = []
    for index in range(5):
        kept_flags.append(archive.add(_scored(score=float(index), seed=index)))
    assert len(archive.entries) == 3
    assert archive.best() is not None
    assert archive.best().total_score == 4.0
    # Lowest scores should have been dropped.
    scores = sorted(item.total_score for item in archive.entries)
    assert scores == [2.0, 3.0, 4.0]


def test_novelty_archive_capacity() -> None:
    archive = NoveltyArchive(capacity=2, k_nearest=1)
    archive.add(_scored(score=0.1, novelty=0.2, seed=1))
    archive.add(_scored(score=0.1, novelty=0.9, seed=2))
    archive.add(_scored(score=0.1, novelty=0.5, seed=3))
    assert len(archive.entries) == 2
    novelties = sorted(item.score_components["novelty"] for item in archive.entries)
    assert novelties == [0.5, 0.9]


def test_robustness_archive_prefers_high_robustness() -> None:
    archive = RobustnessArchive(capacity=2)
    archive.add(_scored(score=1.0, robustness=0.1, seed=1))
    archive.add(_scored(score=0.2, robustness=0.9, seed=2))
    archive.add(_scored(score=0.3, robustness=0.8, seed=3))
    assert len(archive.entries) == 2
    robustness_values = sorted(
        item.score_components["robustness"] for item in archive.entries
    )
    assert robustness_values[-1] >= 0.8

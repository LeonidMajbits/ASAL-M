from __future__ import annotations

import numpy as np

from asal_m.archive.novelty_archive import NoveltyArchive
from asal_m.core.candidate import CandidateConfig, RunArtifacts, ScoredCandidate


def _entry(embedding: np.ndarray, novelty: float = 0.0) -> ScoredCandidate:
    candidate = CandidateConfig(substrate="alpha_alife", search_mode="frontier", seed=0)
    run = RunArtifacts(
        candidate=candidate,
        executed_steps=1,
        frames=[],
        metrics_trace=[],
        state_snapshots=[],
        summary_metrics={},
        embedding=embedding,
    )
    return ScoredCandidate(
        run=run,
        total_score=0.0,
        score_components={"novelty": novelty},
    )


def test_novelty_uses_k_nearest_not_farthest() -> None:
    archive = NoveltyArchive(capacity=10, k_nearest=2)
    archive.entries = [
        _entry(np.asarray([1.0, 0.0, 0.0])),
        _entry(np.asarray([0.0, 1.0, 0.0])),
        _entry(np.asarray([-1.0, 0.0, 0.0])),
    ]
    query = np.asarray([1.0, 0.0, 0.0])
    from asal_m.scoring.embeddings import embedding_distance

    distances = sorted(
        embedding_distance(query, item.embedding) for item in archive.entries
    )
    expected = sum(distances[:2]) / 2.0
    farthest_mean = sum(distances[-2:]) / 2.0
    value = archive.novelty(query)
    assert abs(value - expected) < 1e-9
    # Guard against the old farthest-neighbor bug.
    assert abs(value - farthest_mean) > 1e-6 or farthest_mean == expected


def test_empty_archive_is_maximally_novel() -> None:
    archive = NoveltyArchive()
    assert archive.novelty(np.asarray([1.0, 2.0, 3.0])) == 1.0

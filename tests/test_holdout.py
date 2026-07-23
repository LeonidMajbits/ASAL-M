from __future__ import annotations

import pytest

from asal_m.core.candidate import CandidateConfig
from asal_m.validation.holdout_eval import (
    compute_holdout_score,
    compute_trajectory_quality_score,
)
from asal_m.core import SimulationRunner
from asal_m.substrates import create_substrate


def test_holdout_uses_distinct_seeds() -> None:
    candidate = CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=11,
        environment={"grid_size": 32},
        initial_conditions={"density": 0.12},
    )
    score, details = compute_holdout_score(candidate, steps=16, seed_offsets=[5, 9])
    assert 0.0 <= score <= 1.0
    seeds = {item["seed"] for item in details}
    assert 11 not in seeds
    assert seeds == {16, 20}


def test_explicit_holdout_rejects_discovery_seed() -> None:
    candidate = CandidateConfig(
        substrate="alpha_alife", search_mode="frontier", seed=11
    )
    with pytest.raises(ValueError, match="exclude the discovery seed"):
        compute_holdout_score(candidate, steps=4, holdout_seeds=[11, 17])


def test_explicit_holdout_deduplicates_seeds() -> None:
    candidate = CandidateConfig(
        substrate="alpha_alife", search_mode="frontier", seed=11
    )
    _, details = compute_holdout_score(candidate, steps=4, holdout_seeds=[17, 17, 19])
    assert [item["seed"] for item in details] == [17, 19]


def test_trajectory_quality_is_not_holdout_api() -> None:
    candidate = CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=3,
        environment={"grid_size": 24},
        initial_conditions={"density": 0.1},
    )
    runner = SimulationRunner("runs/test_holdout_quality")
    run = runner.run_candidate(
        create_substrate(candidate.substrate),
        candidate,
        steps=12,
        frame_stride=4,
        capture_state_every=6,
        save_artifacts=False,
    )
    quality = compute_trajectory_quality_score(run)
    assert 0.0 <= quality <= 1.0

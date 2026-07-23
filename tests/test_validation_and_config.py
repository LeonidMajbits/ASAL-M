from __future__ import annotations

from typing import Any, get_type_hints

import pytest

from asal_m.core.candidate import CandidateConfig
from asal_m.core.runner import SimulationRunner
from asal_m.substrates import create_substrate, list_substrates
from asal_m.validation import validate_candidate
from asal_m.validation.replay import deterministic_replay_check


def _alpha_candidate(seed: int = 5) -> CandidateConfig:
    return CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=seed,
        environment={"grid_size": 32},
        initial_conditions={"density": 0.12},
    )


def test_unknown_substrate_fails_clearly() -> None:
    with pytest.raises(ValueError, match="Unknown substrate"):
        create_substrate("not_a_real_substrate")


def test_list_substrates_nonempty() -> None:
    names = list_substrates()
    assert "alpha_alife" in names


def test_multi_seed_deterministic_replay() -> None:
    runner = SimulationRunner("runs/test_replay")
    for seed in (1, 2, 3):
        candidate = _alpha_candidate(seed=seed)
        ok, difference, _ = deterministic_replay_check(
            candidate,
            runner,
            steps=20,
            frame_stride=4,
            capture_state_every=10,
        )
        assert ok is True
        assert difference < 1e-9


def test_validation_composition_has_holdout_details() -> None:
    candidate = _alpha_candidate(seed=9)
    report = validate_candidate(
        candidate,
        steps=16,
        frame_stride=4,
        capture_state_every=8,
        validation_config={
            "artifact_root": "runs/test_validation",
            "long_steps_multiplier": 2,
            "neighbor_samples": 2,
            "holdout_seed_offsets": [11, 17],
            "perturbations": [{"kind": "wipe_patch", "size": 0.2}],
        },
        search_space={},
    )
    payload = report.to_dict()
    assert "promotion_score" in payload
    assert 0.0 <= payload["promotion_score"] <= 1.0
    assert 0.0 <= report.holdout_score <= 1.0
    assert "holdout" in report.details
    seeds = {item["seed"] for item in report.details["holdout"]}
    assert 9 not in seeds
    assert seeds == {20, 26}
    # Same-seed perturbation bookkeeping
    assert all(item["seed"] == 9 for item in report.details["perturbations"])
    assert report.certification["status"] in {"certified", "rejected"}
    assert "checks" in report.certification


def test_candidate_with_updates_accepts_scalar_and_mapping_sections() -> None:
    candidate = _alpha_candidate()
    updated = candidate.with_updates(
        seed=77,
        metadata={"source": "test"},
    )
    hints = get_type_hints(CandidateConfig.with_updates)

    assert updated.seed == 77
    assert updated.metadata == {"source": "test"}
    assert hints["sections"] is Any

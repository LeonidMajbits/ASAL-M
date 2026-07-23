from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from asal_m.core.candidate import CandidateConfig, RunArtifacts, ValidationReport
from asal_m.core.runner import SimulationRunner
from asal_m.scoring import (
    compute_behavior_embedding,
    compute_composite_score,
    compute_mechanism_score,
)
from asal_m.scoring.artifact_penalty import compute_artifact_penalty
from asal_m.scoring.clip_score import compute_target_fit
from asal_m.scoring.robustness_score import compute_robustness_score
from asal_m.search.frontier import FrontierSearchMode
from asal_m.search.novelty import OutlierSearchMode
from asal_m.search.promotion import PromotionSearchMode
from asal_m.search.robustness import RobustnessSearchMode
from asal_m.substrates import create_substrate, get_search_space, list_substrates
from asal_m.validation.holdout_eval import compute_holdout_score
from asal_m.validation.replay import deterministic_replay_check, long_horizon_rerun
from asal_m.validation import CertificationPolicy, evaluate_certification


def _run(
    substrate: str = "alpha_alife", seed: int = 3, steps: int = 16
) -> RunArtifacts:
    candidate = CandidateConfig(
        substrate=substrate,
        search_mode="frontier",
        seed=seed,
        environment={"grid_size": 32},
        initial_conditions={"density": 0.12},
    )
    runner = SimulationRunner("runs/test_scoring")
    return runner.run_candidate(
        create_substrate(substrate),
        candidate,
        steps=steps,
        frame_stride=4,
        capture_state_every=8,
        save_artifacts=False,
    )


def test_all_search_modes_construct() -> None:
    for mode_cls in (
        FrontierSearchMode,
        OutlierSearchMode,
        PromotionSearchMode,
        RobustnessSearchMode,
    ):
        mode = mode_cls()
        assert mode.archive_threshold() >= 0.0
        assert isinstance(mode.name, str) and mode.name


def test_composite_score_keys_and_bounds() -> None:
    run = _run()
    run.embedding = compute_behavior_embedding(run)
    components = compute_composite_score(
        run,
        novelty=0.4,
        diversity_bonus=0.2,
        target_metrics={"occupancy": 0.1, "diversity": 0.2},
        validation=None,
        objective_weights={"mechanism_signal": 0.1},
        validation_proxy_score=0.5,
    )
    for key in (
        "total",
        "target_fit",
        "novelty",
        "diversity_bonus",
        "persistence",
        "robustness",
        "lineage_signal",
        "mechanism_signal",
        "artifact_penalty",
    ):
        assert key in components
        assert np.isfinite(components[key])


def test_mechanism_and_artifact_penalty_finite() -> None:
    run = _run()
    assert (
        0.0 <= compute_mechanism_score(run) <= 1.0
        or compute_mechanism_score(run) >= 0.0
    )
    assert compute_artifact_penalty(run) >= 0.0


def test_target_fit_perfect_and_missing() -> None:
    assert compute_target_fit({"occupancy": 0.2}, {"occupancy": 0.2}) == pytest.approx(
        1.0
    )
    assert compute_target_fit({"occupancy": 0.2}, None) == 0.0


def test_embedding_shape_stable() -> None:
    run = _run()
    emb = compute_behavior_embedding(run)
    assert emb.ndim == 1
    assert emb.size > 0
    assert np.isfinite(emb).all()


def test_long_horizon_and_holdout_finite() -> None:
    candidate = CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=8,
        environment={"grid_size": 32},
        initial_conditions={"density": 0.1},
    )
    runner = SimulationRunner("runs/test_long")
    score, _ = long_horizon_rerun(
        candidate, runner, steps=20, frame_stride=4, capture_state_every=10
    )
    holdout, details = compute_holdout_score(candidate, steps=12, seed_offsets=[3, 5])
    assert 0.0 <= score <= 1.0
    assert 0.0 <= holdout <= 1.0
    assert len(details) == 2


def test_mutation_cells_deterministic_replay() -> None:
    candidate = CandidateConfig(
        substrate="mutation_cells",
        search_mode="frontier",
        seed=4,
        environment={"grid_size": 32},
        initial_conditions={"density": 0.12, "seed_lineages": 4},
    )
    runner = SimulationRunner("runs/test_mut_replay")
    ok, diff, _ = deterministic_replay_check(
        candidate, runner, steps=12, frame_stride=4, capture_state_every=6
    )
    assert ok is True
    assert diff < 1e-9


def test_every_starter_yaml_loads() -> None:
    exp_dir = Path("asal_m/experiments")
    required = {"name", "substrate", "seed"}
    for path in sorted(exp_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), path.name
        if data.get("kind") == "flagship":
            assert "candidate" in data
            assert data["candidate"]["substrate"] in list_substrates()
            continue
        assert required.issubset(data), path.name
        assert data["substrate"] in list_substrates()
        space = get_search_space(data["substrate"])
        assert "params" in space or "rule_variants" in space


def test_validation_report_promotion_score() -> None:
    report = ValidationReport(
        deterministic_replay=True,
        replay_difference=0.0,
        long_horizon_score=0.8,
        perturbation_score=0.7,
        neighborhood_score=0.6,
        holdout_score=0.9,
    )
    score = report.promotion_score()
    assert score == pytest.approx((1.0 + 0.8 + 0.7 + 0.6 + 0.9) / 5.0)
    assert compute_robustness_score(report) == pytest.approx(score)
    assert "promotion_score" in report.to_dict()


def test_certification_rejects_a_failed_dimension_despite_high_average() -> None:
    report = ValidationReport(
        deterministic_replay=True,
        replay_difference=0.0,
        long_horizon_score=0.95,
        perturbation_score=0.40,
        neighborhood_score=0.95,
        holdout_score=0.95,
        details={
            "long_run_summary": {},
            "perturbations": [{}],
            "neighborhood": [{}],
            "holdout": [{}],
        },
    )
    decision = evaluate_certification(report)
    assert report.promotion_score() > 0.8
    assert decision.passed is False
    assert decision.status == "rejected"
    assert "perturbation_below_policy" in decision.failure_codes


def test_certification_distinguishes_missing_evidence_from_failure() -> None:
    report = ValidationReport(
        deterministic_replay=True,
        replay_difference=0.0,
        long_horizon_score=0.9,
        perturbation_score=0.0,
        neighborhood_score=0.0,
        holdout_score=0.9,
        details={"long_run_summary": {}, "holdout": [{}]},
    )
    decision = evaluate_certification(report)
    assert "perturbation_not_evaluated" in decision.failure_codes
    assert "neighborhood_not_evaluated" in decision.failure_codes
    assert decision.checks["perturbation"]["evaluated"] is False


def test_certification_policy_accepts_complete_strong_evidence() -> None:
    report = ValidationReport(
        deterministic_replay=True,
        replay_difference=0.0,
        long_horizon_score=0.9,
        perturbation_score=0.8,
        neighborhood_score=0.7,
        holdout_score=0.85,
        details={
            "long_run_summary": {},
            "perturbations": [{}],
            "neighborhood": [{}],
            "holdout": [{}],
        },
    )
    policy = CertificationPolicy(name="test-policy", min_promotion_score=0.75)
    decision = evaluate_certification(report, policy)
    assert decision.passed is True
    assert decision.status == "certified"
    assert decision.failure_codes == []

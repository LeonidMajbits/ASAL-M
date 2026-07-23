from __future__ import annotations

from typing import Any

from ..core.candidate import CandidateConfig, ValidationReport
from ..core.runner import SimulationRunner
from .certification import (
    CertificationDecision,
    CertificationPolicy,
    evaluate_certification,
)
from .holdout_eval import compute_holdout_score
from .neighborhood_scan import run_neighborhood_scan
from .perturb_suite import run_perturbation_suite
from .replay import deterministic_replay_check, long_horizon_rerun


def validate_candidate(
    candidate: CandidateConfig,
    steps: int,
    frame_stride: int,
    capture_state_every: int,
    validation_config: dict[str, Any] | None = None,
    search_space: dict[str, Any] | None = None,
) -> ValidationReport:
    config = validation_config or {}
    runner = SimulationRunner(config.get("artifact_root", "runs/validation"))

    deterministic, replay_difference, replay_run = deterministic_replay_check(
        candidate,
        runner,
        steps,
        frame_stride,
        capture_state_every,
    )
    long_score, long_run = long_horizon_rerun(
        candidate,
        runner,
        steps * int(config.get("long_steps_multiplier", 2)),
        frame_stride,
        capture_state_every,
    )
    perturbation_score, perturbation_details = run_perturbation_suite(
        candidate,
        steps,
        config.get("perturbations", []),
    )
    neighborhood_score, neighborhood_details = run_neighborhood_scan(
        candidate,
        search_space or {},
        steps,
        num_neighbors=int(config.get("neighbor_samples", 4)),
    )
    holdout_steps = int(config.get("holdout_steps", steps))
    holdout_score, holdout_details = compute_holdout_score(
        candidate,
        steps=holdout_steps,
        holdout_seeds=config.get("holdout_seeds"),
        seed_offsets=config.get("holdout_seed_offsets"),
    )

    notes: list[str] = []
    if not deterministic:
        notes.append("deterministic replay diverged")
    if perturbation_score < 0.25:
        notes.append("perturbation suite exposed fragility")
    if neighborhood_score < 0.25:
        notes.append("neighboring configs collapsed quickly")
    if holdout_score < 0.25:
        notes.append("held-out seeds collapsed quickly")

    report = ValidationReport(
        deterministic_replay=deterministic,
        replay_difference=replay_difference,
        long_horizon_score=long_score,
        perturbation_score=perturbation_score,
        neighborhood_score=neighborhood_score,
        holdout_score=holdout_score,
        notes=notes,
        details={
            "replay_summary": replay_run.summary_metrics,
            "long_run_summary": long_run.summary_metrics,
            "perturbations": perturbation_details,
            "neighborhood": neighborhood_details,
            "holdout": holdout_details,
        },
    )
    report.certification = evaluate_certification(
        report,
        config.get("certification_policy"),
    ).to_dict()
    return report


__all__ = [
    "CertificationDecision",
    "CertificationPolicy",
    "evaluate_certification",
    "validate_candidate",
]

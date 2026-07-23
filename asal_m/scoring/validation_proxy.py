from __future__ import annotations

from typing import Any

import numpy as np

from ..core.candidate import CandidateConfig, RunArtifacts
from ..core.runner import SimulationRunner
from ..validation.holdout_eval import (
    compute_holdout_score,
    compute_trajectory_quality_score,
)
from ..validation.neighborhood_scan import run_neighborhood_scan
from ..validation.perturb_suite import run_perturbation_suite
from ..validation.replay import deterministic_replay_check, long_horizon_rerun


def compute_validation_proxy(run: RunArtifacts) -> float:
    return float(compute_validation_proxy_details(run)["promotion_proxy"])


def compute_validation_proxy_details(run: RunArtifacts) -> dict[str, float]:
    if not run.metrics_trace:
        return {
            "holdout_proxy": 0.0,
            "long_horizon_proxy": 0.0,
            "perturbation_proxy": 0.0,
            "neighborhood_proxy": 0.0,
            "promotion_proxy": 0.0,
        }

    occupancy = _series(run, "occupancy")
    diversity = _series(run, "diversity")
    coherence = _series(run, "cluster_coherence")
    lineage_entropy = _series(run, "lineage_entropy")
    budget_entropy = _series(run, "budget_entropy")
    activity = _series(run, "activity")
    mean_age = _series(run, "mean_age")
    birth_rate = _series(run, "birth_rate")
    death_rate = _series(run, "death_rate")

    late = _late_slice(len(occupancy))
    early = slice(
        0, late.stop - late.start if late.stop - late.start > 0 else len(occupancy)
    )

    occupancy_late = float(occupancy[late].mean())
    diversity_late = float(diversity[late].mean())
    coherence_late = float(coherence[late].mean())
    lineage_entropy_late = float(lineage_entropy[late].mean())
    budget_entropy_late = float(budget_entropy[late].mean())
    mean_age_late = float(mean_age[late].mean())

    occupancy_retention = _clip01(
        occupancy_late / max(0.05, float(occupancy[early].mean()))
    )
    occupancy_smoothness = 1.0 - _clip01(_mean_abs_diff(occupancy) / 0.06)
    activity_smoothness = 1.0 - _clip01(_mean_abs_diff(activity) / 0.08)
    coherence_smoothness = 1.0 - _clip01(_mean_abs_diff(coherence) / 0.03)
    turnover_balance = 1.0 - _clip01(
        abs(float(birth_rate[late].mean()) - float(death_rate[late].mean()))
        / max(0.02, float((birth_rate[late] + death_rate[late]).mean()))
    )
    age_maturity = _clip01(mean_age_late / 0.8)

    # Cheap in-run signal only — not a seed holdout. Full holdout is evaluate_validation_proxy / validate_candidate.
    holdout_proxy = _clip01(
        0.45 * compute_trajectory_quality_score(run)
        + 0.2 * coherence_late
        + 0.15 * diversity_late
        + 0.1 * occupancy_smoothness
        + 0.1 * budget_entropy_late
    )
    long_horizon_proxy = _clip01(
        0.24 * occupancy_late
        + 0.18 * coherence_late
        + 0.16 * occupancy_retention
        + 0.14 * occupancy_smoothness
        + 0.14 * lineage_entropy_late
        + 0.14 * age_maturity
    )
    perturbation_proxy = _clip01(
        0.24 * coherence_late
        + 0.2 * budget_entropy_late
        + 0.18 * turnover_balance
        + 0.14 * diversity_late
        + 0.12 * activity_smoothness
        + 0.12 * occupancy_smoothness
    )
    neighborhood_proxy = _clip01(
        0.26 * coherence_late
        + 0.22 * lineage_entropy_late
        + 0.18 * budget_entropy_late
        + 0.18 * coherence_smoothness
        + 0.16 * occupancy_smoothness
    )
    promotion_proxy = _clip01(
        0.28 * holdout_proxy
        + 0.28 * long_horizon_proxy
        + 0.22 * perturbation_proxy
        + 0.22 * neighborhood_proxy
    )

    return {
        "holdout_proxy": holdout_proxy,
        "long_horizon_proxy": long_horizon_proxy,
        "perturbation_proxy": perturbation_proxy,
        "neighborhood_proxy": neighborhood_proxy,
        "promotion_proxy": promotion_proxy,
    }


def evaluate_validation_proxy(
    candidate: CandidateConfig,
    *,
    steps: int,
    frame_stride: int,
    capture_state_every: int,
    proxy_config: dict[str, Any] | None = None,
    search_space: dict[str, Any] | None = None,
) -> dict[str, float | bool]:
    cfg = _merge_proxy_config(_default_proxy_config(steps), proxy_config or {})
    runner = SimulationRunner(cfg["artifact_root"])

    replay_steps = int(cfg["replay_steps"])
    long_steps = int(cfg["long_steps"])
    proxy_frame_stride = int(cfg["frame_stride"])
    proxy_capture_state_every = int(cfg["capture_state_every"])

    deterministic, replay_difference, _ = deterministic_replay_check(
        candidate,
        runner,
        replay_steps,
        proxy_frame_stride,
        proxy_capture_state_every,
    )
    long_horizon_score, long_run = long_horizon_rerun(
        candidate,
        runner,
        long_steps,
        proxy_frame_stride,
        proxy_capture_state_every,
    )
    perturbation_score, _ = run_perturbation_suite(
        candidate,
        int(cfg["perturbation_steps"]),
        list(cfg.get("perturbations", [])),
    )
    neighborhood_score, _ = run_neighborhood_scan(
        candidate,
        search_space or {},
        int(cfg["neighborhood_steps"]),
        num_neighbors=int(cfg["neighbor_samples"]),
    )
    holdout_score, _ = compute_holdout_score(
        candidate,
        steps=int(cfg.get("holdout_steps", replay_steps)),
        holdout_seeds=cfg.get("holdout_seeds"),
        seed_offsets=cfg.get("holdout_seed_offsets"),
    )
    promotion_proxy = float(
        np.mean(
            [
                1.0 if deterministic else 0.0,
                max(0.0, 1.0 - replay_difference),
                holdout_score,
                long_horizon_score,
                perturbation_score,
                neighborhood_score,
            ]
        )
    )

    return {
        "deterministic_replay": bool(deterministic),
        "replay_difference": float(replay_difference),
        "holdout_proxy": float(holdout_score),
        "long_horizon_proxy": float(long_horizon_score),
        "perturbation_proxy": float(perturbation_score),
        "neighborhood_proxy": float(neighborhood_score),
        "promotion_proxy": promotion_proxy,
    }


def _series(run: RunArtifacts, key: str) -> np.ndarray:
    values = np.asarray(
        [float(item.get(key, 0.0)) for item in run.metrics_trace], dtype=float
    )
    if values.size:
        return values
    return np.asarray([float(run.summary_metrics.get(key, 0.0))], dtype=float)


def _late_slice(length: int) -> slice:
    width = max(3, length // 3)
    start = max(0, length - width)
    return slice(start, length)


def _mean_abs_diff(values: np.ndarray) -> float:
    if values.size <= 1:
        return 0.0
    return float(np.abs(np.diff(values)).mean())


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _default_proxy_config(steps: int) -> dict[str, Any]:
    base_steps = max(48, int(steps))
    proxy_frame_stride = max(1, base_steps // 16)
    proxy_capture_state_every = max(1, base_steps // 8)
    return {
        "artifact_root": "runs/validation_proxy",
        "replay_steps": base_steps,
        "long_steps": base_steps * 2,
        "perturbation_steps": base_steps,
        "neighborhood_steps": base_steps,
        "neighbor_samples": 2,
        "frame_stride": proxy_frame_stride,
        "capture_state_every": proxy_capture_state_every,
        "perturbations": [
            {"kind": "radiation", "magnitude": 0.14},
            {"kind": "charge_drop", "factor": 0.45},
        ],
    }


def _merge_proxy_config(
    defaults: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        merged[key] = value
    return merged

from __future__ import annotations

import numpy as np

from ..core.candidate import CandidateConfig, RunArtifacts
from ..core.runner import SimulationRunner
from ..substrates import create_substrate


def deterministic_replay_check(
    candidate: CandidateConfig,
    runner: SimulationRunner,
    steps: int,
    frame_stride: int,
    capture_state_every: int,
) -> tuple[bool, float, RunArtifacts]:
    run_a = runner.run_candidate(
        create_substrate(candidate.substrate),
        candidate,
        steps=steps,
        frame_stride=frame_stride,
        capture_state_every=capture_state_every,
        save_artifacts=False,
    )
    run_b = runner.run_candidate(
        create_substrate(candidate.substrate),
        candidate,
        steps=steps,
        frame_stride=frame_stride,
        capture_state_every=capture_state_every,
        save_artifacts=False,
    )
    difference = _trace_difference(run_a, run_b)
    return difference <= 1e-9, difference, run_a


def long_horizon_rerun(
    candidate: CandidateConfig,
    runner: SimulationRunner,
    steps: int,
    frame_stride: int,
    capture_state_every: int,
) -> tuple[float, RunArtifacts]:
    run = runner.run_candidate(
        create_substrate(candidate.substrate),
        candidate,
        steps=steps,
        frame_stride=frame_stride,
        capture_state_every=capture_state_every,
        save_artifacts=False,
    )
    score = min(
        1.0,
        0.45 * run.summary_metrics.get("survival_fraction", 0.0)
        + 0.35 * run.summary_metrics.get("occupancy", 0.0)
        + 0.2 * run.summary_metrics.get("diversity", 0.0),
    )
    return float(score), run


def _trace_difference(left: RunArtifacts, right: RunArtifacts) -> float:
    if len(left.frames) != len(right.frames):
        return 1.0
    if not left.frames:
        return 1.0
    frame_delta = (
        np.mean(
            np.abs(
                np.asarray(left.frames, dtype=float)
                - np.asarray(right.frames, dtype=float)
            )
        )
        / 255.0
    )
    keys = sorted(
        {key for item in left.metrics_trace for key in item}
        | {key for item in right.metrics_trace for key in item}
    )
    if not keys or len(left.metrics_trace) != len(right.metrics_trace):
        return float(frame_delta)
    left_metrics = np.asarray(
        [[float(item.get(key, 0.0)) for key in keys] for item in left.metrics_trace],
        dtype=float,
    )
    right_metrics = np.asarray(
        [[float(item.get(key, 0.0)) for key in keys] for item in right.metrics_trace],
        dtype=float,
    )
    metric_delta = (
        np.mean(np.abs(left_metrics - right_metrics)) if left_metrics.size else 0.0
    )
    return float(frame_delta + metric_delta)

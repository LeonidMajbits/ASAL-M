from __future__ import annotations

from ..core.candidate import ValidationReport


def compute_robustness_score(validation: ValidationReport | None) -> float:
    if validation is None:
        return 0.0
    replay_score = (
        max(0.0, 1.0 - validation.replay_difference)
        if validation.deterministic_replay
        else 0.0
    )
    return float(
        max(
            0.0,
            min(
                1.0,
                (
                    replay_score
                    + validation.long_horizon_score
                    + validation.perturbation_score
                    + validation.neighborhood_score
                    + validation.holdout_score
                )
                / 5.0,
            ),
        )
    )

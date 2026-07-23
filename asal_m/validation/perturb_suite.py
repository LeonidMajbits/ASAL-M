from __future__ import annotations

from typing import Any

from ..core.candidate import CandidateConfig
from ..substrates import create_substrate


def run_perturbation_suite(
    candidate: CandidateConfig,
    steps: int,
    perturbations: list[dict[str, Any]],
) -> tuple[float, list[dict[str, Any]]]:
    """Apply mid-horizon shocks to the *same* seed realization for each perturbation.

    Uses the discovery seed for every trial so the measured effect is the
    perturbation, not a different initial sample.
    """
    if not perturbations:
        return 0.0, []

    details: list[dict[str, Any]] = []
    scores: list[float] = []
    split_step = max(1, steps // 2)
    recovery_budget = max(1, steps - split_step)

    for perturbation in perturbations:
        substrate = create_substrate(candidate.substrate)
        substrate.reset(candidate.to_substrate_config(), candidate.seed)

        for _ in range(split_step):
            substrate.step()
            if substrate.is_extinct():
                break

        if substrate.is_extinct():
            scores.append(0.0)
            details.append(
                {
                    "perturbation": perturbation,
                    "seed": int(candidate.seed),
                    "survived_steps": 0,
                    "pre_perturbation_extinct": True,
                    "metrics": substrate.extract_metrics(),
                    "score": 0.0,
                }
            )
            continue

        substrate.apply_perturbation(perturbation)
        survived = 0
        for _ in range(recovery_budget):
            if substrate.is_extinct():
                break
            substrate.step()
            survived += 1

        metrics = substrate.extract_metrics()
        score = min(
            1.0,
            0.4 * (survived / recovery_budget)
            + 0.35 * float(metrics.get("occupancy", 0.0))
            + 0.25 * float(metrics.get("diversity", 0.0)),
        )
        scores.append(float(score))
        details.append(
            {
                "perturbation": perturbation,
                "seed": int(candidate.seed),
                "survived_steps": survived,
                "pre_perturbation_extinct": False,
                "metrics": metrics,
                "score": float(score),
            }
        )

    return float(sum(scores) / len(scores)), details

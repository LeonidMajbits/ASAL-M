from __future__ import annotations

import numpy as np

from ..core.candidate import RunArtifacts


def compute_mechanism_score(run: RunArtifacts) -> float:
    if run.candidate.substrate != "mutation_cells":
        return 0.5
    return _compute_mutation_cells_mechanism_score(run)


def _compute_mutation_cells_mechanism_score(run: RunArtifacts) -> float:
    budget_entropy = _series_mean(run, "budget_entropy")
    budget_utilization = _series_mean(run, "budget_utilization")
    lineage_entropy = _series_mean(run, "lineage_entropy")
    lineage_concentration = _series_mean(run, "lineage_concentration")
    birth_rate = _series_mean(run, "birth_rate")
    death_rate = _series_mean(run, "death_rate")
    activity = _series_mean(run, "activity")

    budget_entropy_score = _clip01(budget_entropy)
    budget_utilization_score = 1.0 - _clip01(abs(budget_utilization - 0.6) / 0.6)
    lineage_dispersion_score = _clip01(
        0.5 * lineage_entropy + 0.5 * (1.0 - lineage_concentration)
    )

    total_turnover = birth_rate + death_rate
    turnover_magnitude = _clip01(total_turnover / 0.18)
    turnover_balance = 1.0 - _clip01(
        abs(birth_rate - death_rate) / max(0.02, total_turnover)
    )
    turnover_score = _clip01(turnover_magnitude * turnover_balance)

    activity_score = 1.0 - _clip01(abs(activity - 0.18) / 0.18)

    return float(
        _clip01(
            0.3 * budget_entropy_score
            + 0.2 * budget_utilization_score
            + 0.25 * lineage_dispersion_score
            + 0.15 * turnover_score
            + 0.1 * activity_score
        )
    )


def _series_mean(run: RunArtifacts, key: str) -> float:
    if run.metrics_trace:
        values = np.asarray(
            [float(item.get(key, 0.0)) for item in run.metrics_trace], dtype=float
        )
        return (
            float(values.mean())
            if values.size
            else float(run.summary_metrics.get(key, 0.0))
        )
    return float(run.summary_metrics.get(key, 0.0))


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))

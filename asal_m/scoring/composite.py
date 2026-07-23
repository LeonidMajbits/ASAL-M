from __future__ import annotations

from typing import Mapping

from ..core.candidate import RunArtifacts, ValidationReport
from .artifact_penalty import compute_artifact_penalty
from .clip_score import compute_target_fit
from .mechanism_score import compute_mechanism_score
from .robustness_score import compute_robustness_score
from .temporal_score import compute_temporal_scores
from .validation_proxy import compute_validation_proxy

DEFAULT_COMPONENT_WEIGHTS = {
    "target_fit": 0.1,
    "novelty": 0.2,
    "diversity_bonus": 0.15,
    "persistence": 0.2,
    "robustness": 0.2,
    "lineage_signal": 0.15,
    "mechanism_signal": 0.0,
    "validation_proxy": 0.0,
    "artifact_penalty": 0.25,
}


def compute_composite_score(
    run: RunArtifacts,
    novelty: float,
    diversity_bonus: float,
    target_metrics: Mapping[str, float] | None = None,
    validation: ValidationReport | None = None,
    objective_weights: Mapping[str, float] | None = None,
    validation_proxy_score: float | None = None,
) -> dict[str, float]:
    temporal = compute_temporal_scores(run.metrics_trace)
    components = {
        "target_fit": compute_target_fit(run.summary_metrics, target_metrics),
        "novelty": float(max(0.0, min(1.0, novelty))),
        "diversity_bonus": float(max(0.0, min(1.0, diversity_bonus))),
        "persistence": temporal["persistence"],
        "robustness": compute_robustness_score(validation),
        "lineage_signal": temporal["lineage_signal"],
        "mechanism_signal": compute_mechanism_score(run),
        "validation_proxy": (
            float(validation_proxy_score)
            if validation_proxy_score is not None
            else compute_validation_proxy(run)
        ),
        "artifact_penalty": compute_artifact_penalty(run),
        "temporal_coherence": temporal["temporal_coherence"],
    }

    weights = dict(DEFAULT_COMPONENT_WEIGHTS)
    if objective_weights:
        weights.update(objective_weights)

    total = (
        weights["target_fit"] * components["target_fit"]
        + weights["novelty"] * components["novelty"]
        + weights["diversity_bonus"] * components["diversity_bonus"]
        + weights["persistence"] * components["persistence"]
        + weights["robustness"] * components["robustness"]
        + weights["lineage_signal"] * components["lineage_signal"]
        + weights["mechanism_signal"] * components["mechanism_signal"]
        + weights["validation_proxy"] * components["validation_proxy"]
        - weights["artifact_penalty"] * components["artifact_penalty"]
    )
    components["total"] = float(total)
    return components

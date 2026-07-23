from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CandidateConfig:
    substrate: str
    search_mode: str
    seed: int
    params: dict[str, Any] = field(default_factory=dict)
    rule_variants: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    initial_conditions: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_substrate_config(self) -> dict[str, Any]:
        return {
            "params": dict(self.params),
            "rule_variants": dict(self.rule_variants),
            "environment": dict(self.environment),
            "initial_conditions": dict(self.initial_conditions),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_updates(self, **sections: Any) -> "CandidateConfig":
        payload = self.to_dict()
        for key, value in sections.items():
            if key in {
                "params",
                "rule_variants",
                "environment",
                "initial_conditions",
                "metadata",
            }:
                current = dict(payload.get(key, {}))
                current.update(value)
                payload[key] = current
            else:
                payload[key] = value
        return CandidateConfig(**payload)


@dataclass
class RunArtifacts:
    candidate: CandidateConfig
    executed_steps: int
    frames: list[np.ndarray]
    metrics_trace: list[dict[str, float]]
    state_snapshots: list[dict[str, Any]]
    summary_metrics: dict[str, float]
    artifact_dir: Path | None = None
    video_path: Path | None = None
    trace_path: Path | None = None
    embedding: np.ndarray | None = None

    def final_metrics(self) -> dict[str, float]:
        return dict(self.summary_metrics)

    def extinct(self) -> bool:
        return self.summary_metrics.get("occupancy", 0.0) <= 0.0


@dataclass
class ValidationReport:
    deterministic_replay: bool = False
    replay_difference: float = 1.0
    long_horizon_score: float = 0.0
    perturbation_score: float = 0.0
    neighborhood_score: float = 0.0
    holdout_score: float = 0.0
    notes: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    certification: dict[str, Any] = field(default_factory=dict)

    def promotion_score(self) -> float:
        replay_score = (
            max(0.0, 1.0 - self.replay_difference) if self.deterministic_replay else 0.0
        )
        return float(
            np.mean(
                [
                    replay_score,
                    self.long_horizon_score,
                    self.perturbation_score,
                    self.neighborhood_score,
                    self.holdout_score,
                ]
            )
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["promotion_score"] = self.promotion_score()
        return payload


@dataclass
class ScoredCandidate:
    run: RunArtifacts
    score_components: dict[str, float]
    total_score: float
    validation: ValidationReport | None = None
    benchmark_details: dict[str, Any] = field(default_factory=dict)
    archived_in: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def candidate(self) -> CandidateConfig:
        return self.run.candidate

    @property
    def embedding(self) -> np.ndarray | None:
        return self.run.embedding

    def winner_record(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "total_score": self.total_score,
            "score_components": dict(self.score_components),
            "summary_metrics": dict(self.run.summary_metrics),
            "artifact_dir": str(self.run.artifact_dir)
            if self.run.artifact_dir
            else None,
            "video_path": str(self.run.video_path) if self.run.video_path else None,
            "trace_path": str(self.run.trace_path) if self.run.trace_path else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "benchmark_details": dict(self.benchmark_details),
            "archived_in": list(self.archived_in),
            "tags": list(self.tags),
        }

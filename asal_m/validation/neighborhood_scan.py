from __future__ import annotations

from typing import Any

import numpy as np

from ..core.candidate import CandidateConfig
from ..core.runner import SimulationRunner
from ..substrates import create_substrate


def run_neighborhood_scan(
    candidate: CandidateConfig,
    search_space: dict[str, Any],
    steps: int,
    num_neighbors: int = 4,
) -> tuple[float, list[dict[str, Any]]]:
    runner = SimulationRunner("runs/validation")
    rng = np.random.default_rng(candidate.seed + 10_000)

    if not search_space:
        return 0.0, []

    details: list[dict[str, Any]] = []
    scores: list[float] = []
    for _ in range(max(1, num_neighbors)):
        neighbor = _mutate_candidate(candidate, search_space, rng)
        run = runner.run_candidate(
            create_substrate(candidate.substrate),
            neighbor,
            steps=steps,
            frame_stride=max(1, steps // 12),
            capture_state_every=max(1, steps // 6),
            save_artifacts=False,
        )
        score = min(
            1.0,
            0.4 * run.summary_metrics.get("survival_fraction", 0.0)
            + 0.35 * run.summary_metrics.get("occupancy", 0.0)
            + 0.25 * run.summary_metrics.get("diversity", 0.0),
        )
        scores.append(float(score))
        details.append(
            {
                "candidate": neighbor.to_dict(),
                "metrics": run.summary_metrics,
                "score": float(score),
            }
        )

    return float(sum(scores) / len(scores)), details


def _mutate_candidate(
    candidate: CandidateConfig,
    search_space: dict[str, Any],
    rng: np.random.Generator,
) -> CandidateConfig:
    sections = {
        "params": dict(candidate.params),
        "rule_variants": dict(candidate.rule_variants),
        "environment": dict(candidate.environment),
        "initial_conditions": dict(candidate.initial_conditions),
    }
    for section, specs in search_space.items():
        if not isinstance(specs, dict):
            continue
        for key, spec in specs.items():
            current = sections[section].get(key)
            if current is None:
                continue
            spec_type = spec.get("type")
            if spec_type == "int":
                int_span = max(1, int(spec["max"]) - int(spec["min"]))
                delta = max(1, int_span // 8)
                int_value = int(
                    np.clip(
                        int(current) + rng.integers(-delta, delta + 1),
                        int(spec["min"]),
                        int(spec["max"]),
                    )
                )
                sections[section][key] = int_value
            elif spec_type == "float":
                float_span = float(spec["max"]) - float(spec["min"])
                float_value = float(
                    np.clip(
                        float(current) + rng.normal(0.0, float_span * 0.08),
                        float(spec["min"]),
                        float(spec["max"]),
                    )
                )
                sections[section][key] = float_value
    return candidate.with_updates(**sections)

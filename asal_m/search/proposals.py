from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np


def sample_sections(
    search_space: dict[str, Any],
    rng: np.random.Generator,
) -> dict[str, dict[str, Any]]:
    """Sample a complete candidate payload from a substrate search space."""

    sections: dict[str, dict[str, Any]] = {}
    for section, specs in search_space.items():
        sections[section] = {}
        for key, spec in specs.items():
            sections[section][key] = sample_value(spec, rng)
    return sections


def mutate_sections(
    sections: dict[str, dict[str, Any]],
    search_space: dict[str, Any],
    rng: np.random.Generator,
) -> None:
    """Mutate a candidate payload in place while respecting declared bounds."""

    for section, specs in search_space.items():
        for key, spec in specs.items():
            if key not in sections[section]:
                sections[section][key] = sample_value(spec, rng)
                continue
            spec_type = spec.get("type")
            current = sections[section][key]
            if spec_type == "int":
                span = max(1, int(spec["max"]) - int(spec["min"]))
                delta = max(1, span // 6)
                sections[section][key] = int(
                    np.clip(
                        int(current) + int(rng.integers(-delta, delta + 1)),
                        int(spec["min"]),
                        int(spec["max"]),
                    )
                )
            elif spec_type == "float":
                span = float(spec["max"]) - float(spec["min"])
                sections[section][key] = float(
                    np.clip(
                        float(current) + rng.normal(0.0, span * 0.08),
                        float(spec["min"]),
                        float(spec["max"]),
                    )
                )
            else:
                sections[section][key] = sample_value(spec, rng)


def sample_value(spec: dict[str, Any], rng: np.random.Generator) -> Any:
    spec_type = spec.get("type", "float")
    if spec_type == "int":
        return int(rng.integers(int(spec["min"]), int(spec["max"]) + 1))
    if spec_type == "choice":
        values = spec.get("values", [])
        if not values:
            raise ValueError("Choice search-space entries require at least one value")
        weights = spec.get("weights")
        if weights:
            probabilities = np.asarray(weights, dtype=float)
            if probabilities.size != len(values) or probabilities.sum() <= 0.0:
                raise ValueError(
                    "Choice weights must match values and have a positive sum"
                )
            probabilities = probabilities / probabilities.sum()
            return deepcopy(values[int(rng.choice(len(values), p=probabilities))])
        return deepcopy(values[int(rng.integers(0, len(values)))])
    return float(rng.uniform(float(spec["min"]), float(spec["max"])))

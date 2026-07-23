from __future__ import annotations

from typing import Any

import numpy as np


def apply_alpha_perturbation(
    state: dict[str, Any],
    config: dict[str, Any],
    perturbation: dict[str, Any],
    rng: np.random.Generator,
) -> None:
    kind = perturbation.get("kind", "wipe_patch")
    species = state["species"]
    lineage = state["lineage"]
    energy = state["energy"]
    resources = state["resources"]
    age = state["age"]
    rows, cols = species.shape

    if kind == "wipe_patch":
        frac = float(perturbation.get("size", 0.2))
        height = max(1, int(rows * frac))
        width = max(1, int(cols * frac))
        start_row = int(rng.integers(0, rows))
        start_col = int(rng.integers(0, cols))
        row_slice = slice(start_row, min(rows, start_row + height))
        col_slice = slice(start_col, min(cols, start_col + width))
        species[row_slice, col_slice] = 0
        lineage[row_slice, col_slice] = 0
        energy[row_slice, col_slice] = 0.0
        age[row_slice, col_slice] = 0
    elif kind == "nutrient_shock":
        delta = float(perturbation.get("delta", 0.2))
        resources[:] = np.clip(resources + delta, 0.0, 1.5)
    elif kind == "mortality_burst":
        rate = float(perturbation.get("rate", 0.2))
        kill_mask = (lineage > 0) & (rng.random(species.shape) < rate)
        species[kill_mask] = 0
        lineage[kill_mask] = 0
        energy[kill_mask] = 0.0
        age[kill_mask] = 0
    elif kind == "resource_drought":
        factor = float(perturbation.get("factor", 0.5))
        resources[:] = np.clip(resources * factor, 0.0, 1.5)
    else:
        raise ValueError(f"Unknown Alpha ALife perturbation: {kind}")

from __future__ import annotations

from typing import Any

import numpy as np


def apply_mutation_cells_perturbation(
    state: dict[str, Any],
    config: dict[str, Any],
    perturbation: dict[str, Any],
    rng: np.random.Generator,
) -> None:
    kind = perturbation.get("kind", "radiation")
    lineage = state["lineage"]
    gene = state["gene"]
    charge = state["charge"]
    mutability = state["mutability"]
    age = state["age"]
    rows, cols = lineage.shape

    if kind == "wipe_patch":
        frac = float(perturbation.get("size", 0.18))
        height = max(1, int(rows * frac))
        width = max(1, int(cols * frac))
        start_row = int(rng.integers(0, rows))
        start_col = int(rng.integers(0, cols))
        row_slice = slice(start_row, min(rows, start_row + height))
        col_slice = slice(start_col, min(cols, start_col + width))
        lineage[row_slice, col_slice] = 0
        gene[row_slice, col_slice] = 0.0
        charge[row_slice, col_slice] = 0.0
        mutability[row_slice, col_slice] = 0.0
        age[row_slice, col_slice] = 0
    elif kind == "radiation":
        alive = lineage > 0
        magnitude = float(perturbation.get("magnitude", 0.18))
        gene[alive] = np.clip(
            gene[alive] + rng.normal(0.0, magnitude, size=int(alive.sum())), 0.0, 1.0
        )
        mutability[alive] = np.clip(mutability[alive] + magnitude * 0.5, 0.01, 0.45)
    elif kind == "charge_drop":
        factor = float(perturbation.get("factor", 0.45))
        charge[:] = np.clip(charge * factor, 0.0, 2.0)
    elif kind == "shuffle_patch":
        frac = float(perturbation.get("size", 0.15))
        height = max(1, int(rows * frac))
        width = max(1, int(cols * frac))
        start_row = int(rng.integers(0, rows))
        start_col = int(rng.integers(0, cols))
        row_slice = slice(start_row, min(rows, start_row + height))
        col_slice = slice(start_col, min(cols, start_col + width))
        patch = gene[row_slice, col_slice].copy().ravel()
        rng.shuffle(patch)
        gene[row_slice, col_slice] = patch.reshape(gene[row_slice, col_slice].shape)
    else:
        raise ValueError(f"Unknown Mutation Cells perturbation: {kind}")

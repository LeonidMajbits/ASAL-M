from __future__ import annotations

from typing import Any

import numpy as np


def render_mutation_cells_frame(state: dict[str, Any]) -> np.ndarray:
    lineage = state["lineage"]
    gene = np.clip(state["gene"], 0.0, 1.0)
    charge = np.clip(state["charge"], 0.0, 1.0)
    mutability = np.clip(state["mutability"], 0.0, 1.0)

    frame = np.zeros((*lineage.shape, 3), dtype=float)
    frame[..., 0] = gene * 255.0
    frame[..., 1] = (1.0 - np.abs(gene - 0.5) * 2.0) * 255.0
    frame[..., 2] = mutability * 255.0
    frame *= charge[..., None] * 0.8 + 0.2
    frame[lineage <= 0] *= 0.12
    return np.clip(frame, 0.0, 255.0).astype(np.uint8)

from __future__ import annotations

from typing import Any

import numpy as np

_PALETTE = np.asarray(
    [
        [0, 0, 0],
        [231, 111, 81],
        [244, 162, 97],
        [233, 196, 106],
        [42, 157, 143],
        [38, 70, 83],
        [142, 202, 230],
        [255, 183, 3],
        [186, 104, 200],
    ],
    dtype=np.uint8,
)


def render_alpha_frame(state: dict[str, Any]) -> np.ndarray:
    species = state["species"]
    resources = state["resources"]
    energy = state["energy"]

    background = np.zeros((*species.shape, 3), dtype=float)
    background[..., 1] = np.clip(resources, 0.0, 1.0) * 70.0
    background[..., 2] = np.clip(resources, 0.0, 1.0) * 120.0 + 25.0

    colors = _PALETTE[np.clip(species, 0, _PALETTE.shape[0] - 1)].astype(float)
    energy_gain = np.clip(energy[..., None], 0.0, 1.0)
    frame = background + colors * energy_gain
    return np.clip(frame, 0.0, 255.0).astype(np.uint8)

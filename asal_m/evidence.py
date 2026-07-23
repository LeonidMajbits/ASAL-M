"""Canonical serialization helpers for checked-in public evidence.

Simulation and certification decisions are computed at full precision. Only
the published JSON representation is normalized so insignificant floating-point
noise does not change release artifacts across supported interpreters and NumPy
builds.
"""

from __future__ import annotations

import json
import math
from numbers import Integral, Real
from typing import Any

PUBLIC_FLOAT_DECIMAL_PLACES = 12


def canonicalize_public_payload(value: Any) -> Any:
    """Return a JSON-compatible payload with a stable public float policy."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("Public evidence cannot contain NaN or infinity")
        rounded = float(f"{numeric:.{PUBLIC_FLOAT_DECIMAL_PLACES}f}")
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Public evidence mappings must use string keys")
        return {key: canonicalize_public_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonicalize_public_payload(item) for item in value]
    raise TypeError(f"Unsupported public evidence value: {type(value).__name__}")


def canonical_public_json(value: Any) -> str:
    """Serialize public evidence with canonical keys, floats, UTF-8, and LF."""

    normalized = canonicalize_public_payload(value)
    return (
        json.dumps(
            normalized,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

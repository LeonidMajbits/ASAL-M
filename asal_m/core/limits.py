"""Shared validation for user-controlled work limits."""

from __future__ import annotations

import argparse
import re
from numbers import Integral
from typing import Any


def require_positive_int(value: Any, name: str) -> int:
    """Return ``value`` as an integer or reject non-positive work limits."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    if isinstance(value, Integral):
        parsed = int(value)
    elif isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip()):
        parsed = int(value)
    else:
        raise ValueError(f"{name} must be a positive integer")
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def positive_int_argument(value: str) -> int:
    """``argparse`` adapter for positive integer options."""
    try:
        return require_positive_int(value, "value")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc

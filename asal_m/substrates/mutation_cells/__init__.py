from __future__ import annotations

from typing import Any

__all__ = [
    "MUTATION_CELLS_DEFAULT_SEARCH_SPACE",
    "MutationCellsSubstrate",
]


def __getattr__(name: str) -> Any:
    if name in {"MUTATION_CELLS_DEFAULT_SEARCH_SPACE", "MutationCellsSubstrate"}:
        from .sim import MUTATION_CELLS_DEFAULT_SEARCH_SPACE, MutationCellsSubstrate

        exports = {
            "MUTATION_CELLS_DEFAULT_SEARCH_SPACE": MUTATION_CELLS_DEFAULT_SEARCH_SPACE,
            "MutationCellsSubstrate": MutationCellsSubstrate,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

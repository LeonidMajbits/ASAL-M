from __future__ import annotations

import importlib
from copy import deepcopy
from typing import Any

SUBSTRATE_REGISTRY = {
    "alpha_alife": {
        "module": "asal_m.substrates.alpha_alife.sim",
        "factory_name": "AlphaALifeSubstrate",
        "search_space_name": "ALPHA_ALIFE_DEFAULT_SEARCH_SPACE",
    },
    "mutation_cells": {
        "module": "asal_m.substrates.mutation_cells.sim",
        "factory_name": "MutationCellsSubstrate",
        "search_space_name": "MUTATION_CELLS_DEFAULT_SEARCH_SPACE",
    },
}


def create_substrate(name: str):
    try:
        entry = SUBSTRATE_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown substrate: {name}") from exc
    module = importlib.import_module(entry["module"])
    factory = getattr(module, entry["factory_name"])
    return factory()


def get_search_space(name: str) -> dict[str, Any]:
    try:
        entry = SUBSTRATE_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown substrate: {name}") from exc
    module = importlib.import_module(entry["module"])
    search_space = getattr(module, entry["search_space_name"])
    return deepcopy(search_space)


def list_substrates() -> list[str]:
    return sorted(SUBSTRATE_REGISTRY)

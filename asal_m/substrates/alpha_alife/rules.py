from __future__ import annotations

from typing import Any

import numpy as np

_NEIGHBOR_SHIFTS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def neighbor_sum(values: np.ndarray) -> np.ndarray:
    total = np.zeros_like(values, dtype=float)
    for dy, dx in _NEIGHBOR_SHIFTS:
        total += np.roll(np.roll(values, dy, axis=0), dx, axis=1)
    return total


def diffuse_resource(resources: np.ndarray, diffusion: float) -> np.ndarray:
    neighborhood_mean = neighbor_sum(resources) / len(_NEIGHBOR_SHIFTS)
    return resources * (1.0 - diffusion) + neighborhood_mean * diffusion


def step_alpha(
    state: dict[str, Any], rng: np.random.Generator, config: dict[str, Any]
) -> dict[str, Any]:
    params = config["params"]
    rules = config["rule_variants"]
    environment = config["environment"]

    species = state["species"]
    lineage = state["lineage"]
    energy = state["energy"]
    resources = state["resources"]
    age = state["age"]

    prev_species = species.copy()
    alive = species > 0
    age[alive] += 1

    resources[:] = diffuse_resource(resources, environment["resource_diffusion"])
    resources[:] = np.clip(
        resources + environment["resource_regen"] * (1.0 - resources),
        0.0,
        1.5,
    )

    neighbor_counts = neighbor_sum(alive.astype(float))
    harvest = np.minimum(resources, params["harvest_rate"]) * alive
    resources[:] = np.clip(resources - harvest, 0.0, 1.5)
    energy[:] = np.clip(
        energy + harvest - params["energy_decay"] * alive,
        0.0,
        2.0,
    )
    energy[:] -= (
        np.clip(neighbor_counts - rules["survival_max"], 0.0, None)
        * params["crowding_cost"]
        * alive
    )

    death_roll = rng.random(species.shape)
    death_mask = alive & (
        (energy <= params["death_energy"])
        | (neighbor_counts < rules["survival_min"])
        | (neighbor_counts > rules["survival_max"])
        | (death_roll < params["background_mortality"])
    )

    death_count = int(death_mask.sum())
    species[death_mask] = 0
    lineage[death_mask] = 0
    energy[death_mask] = 0.0
    age[death_mask] = 0

    alive = species > 0
    neighbor_counts = neighbor_sum(alive.astype(float))
    birth_mask = (~alive) & (
        (neighbor_counts >= rules["birth_min"])
        & (neighbor_counts <= rules["birth_max"])
        & (resources >= environment["birth_resource_min"])
    )

    birth_sites = np.argwhere(birth_mask)
    rng.shuffle(birth_sites)
    birth_count = 0
    for row, col in birth_sites:
        neighbors: list[tuple[int, int]] = []
        weights: list[float] = []
        for d_row, d_col in _NEIGHBOR_SHIFTS:
            n_row = (row + d_row) % species.shape[0]
            n_col = (col + d_col) % species.shape[1]
            if lineage[n_row, n_col] <= 0:
                continue
            parent_energy = energy[n_row, n_col]
            if (
                parent_energy
                < params["reproduction_cost"] + params["offspring_energy"] * 0.5
            ):
                continue
            neighbors.append((n_row, n_col))
            weights.append(parent_energy)

        if not neighbors:
            continue

        parent_index = int(
            rng.choice(len(neighbors), p=np.asarray(weights) / np.sum(weights))
        )
        parent_row, parent_col = neighbors[parent_index]
        parent_lineage = int(lineage[parent_row, parent_col])

        child_lineage = parent_lineage
        if rng.random() < params["mutation_rate"]:
            child_lineage = int(state["lineage_counter"])
            state["lineage_counter"] += 1

        lineage[row, col] = child_lineage
        species[row, col] = ((child_lineage - 1) % environment["palette_size"]) + 1
        energy[row, col] = params["offspring_energy"]
        age[row, col] = 0
        energy[parent_row, parent_col] = max(
            0.0, energy[parent_row, parent_col] - params["reproduction_cost"]
        )
        resources[row, col] = max(
            0.0, resources[row, col] - environment["birth_resource_min"]
        )
        birth_count += 1

    alive = species > 0
    state["step_index"] += 1
    state["last_births"] = birth_count
    state["last_deaths"] = death_count
    state["last_change_rate"] = float((species != prev_species).mean())
    state["last_alive_fraction"] = float(alive.mean())
    return state

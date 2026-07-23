from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from ...core import CandidateConfig, SimulationRunner
from ...core.limits import positive_int_argument
from .metrics import compute_metrics
from .perturb import apply_mutation_cells_perturbation
from .render import render_mutation_cells_frame
from .rules import step_mutation_cells

MUTATION_CELLS_DEFAULT_CONFIG = {
    "params": {
        "charge_gain": 0.22,
        "charge_decay": 0.09,
        "crowding_cost": 0.08,
        "offspring_charge": 0.38,
        "reproduction_cost": 0.16,
        "death_charge": 0.03,
        "background_mutation": 0.015,
        "background_mortality": 0.001,
        "mutability_drift": 0.03,
        "min_mutability": 0.01,
        "max_mutability": 0.35,
        "lineage_split_threshold": 0.08,
        "lineage_budget_strength": 0.72,
    },
    "rule_variants": {
        "survival_min": 1,
        "survival_max": 5,
        "birth_min": 2,
        "birth_max": 4,
        "budget_mode": "dynamic",
    },
    "environment": {
        "grid_size": 64,
    },
    "initial_conditions": {
        "density": 0.1,
        "seed_lineages": 8,
        "initial_charge_min": 0.15,
        "initial_charge_max": 0.8,
        "base_mutability": 0.07,
        "initialization_strategy": "stratified",
    },
}

MUTATION_CELLS_DEFAULT_SEARCH_SPACE = {
    "params": {
        "charge_gain": {"type": "float", "min": 0.05, "max": 0.35},
        "charge_decay": {"type": "float", "min": 0.02, "max": 0.18},
        "crowding_cost": {"type": "float", "min": 0.02, "max": 0.18},
        "offspring_charge": {"type": "float", "min": 0.1, "max": 0.55},
        "reproduction_cost": {"type": "float", "min": 0.05, "max": 0.3},
        "background_mutation": {"type": "float", "min": 0.0, "max": 0.06},
        "background_mortality": {"type": "float", "min": 0.0, "max": 0.02},
        "mutability_drift": {"type": "float", "min": 0.005, "max": 0.08},
        "lineage_split_threshold": {"type": "float", "min": 0.02, "max": 0.18},
        "lineage_budget_strength": {"type": "float", "min": 0.0, "max": 1.0},
    },
    "rule_variants": {
        "survival_min": {"type": "int", "min": 1, "max": 3},
        "survival_max": {"type": "int", "min": 4, "max": 7},
        "birth_min": {"type": "int", "min": 2, "max": 3},
        "birth_max": {"type": "int", "min": 3, "max": 6},
        "budget_mode": {"type": "choice", "values": ["dynamic", "uniform"]},
    },
    "environment": {
        "grid_size": {"type": "int", "min": 48, "max": 96},
    },
    "initial_conditions": {
        "density": {"type": "float", "min": 0.03, "max": 0.22},
        "seed_lineages": {"type": "int", "min": 3, "max": 16},
        "initial_charge_min": {"type": "float", "min": 0.05, "max": 0.3},
        "initial_charge_max": {"type": "float", "min": 0.4, "max": 1.0},
        "base_mutability": {"type": "float", "min": 0.01, "max": 0.2},
        "initialization_strategy": {
            "type": "choice",
            "values": ["stratified", "random_uniform", "opposition"],
        },
    },
}


class MutationCellsSubstrate:
    name = "mutation_cells"

    def __init__(self) -> None:
        self.config = deepcopy(MUTATION_CELLS_DEFAULT_CONFIG)
        self.rng = np.random.default_rng(0)
        self.state: dict[str, Any] = {}

    def reset(self, config: dict[str, Any], seed: int) -> None:
        self.config = _merge_config(MUTATION_CELLS_DEFAULT_CONFIG, config)
        self.rng = np.random.default_rng(seed)

        size = int(self.config["environment"]["grid_size"])
        density = float(self.config["initial_conditions"]["density"])
        seed_lineages = int(self.config["initial_conditions"]["seed_lineages"])
        base_mutability = float(self.config["initial_conditions"]["base_mutability"])
        strategy = str(self.config["initial_conditions"]["initialization_strategy"])

        lineage = np.zeros((size, size), dtype=np.int32)
        gene = np.zeros((size, size), dtype=np.float32)
        charge = np.zeros((size, size), dtype=np.float32)
        mutability = np.zeros((size, size), dtype=np.float32)
        age = np.zeros((size, size), dtype=np.int16)

        occupied = _sample_occupied_sites(
            size=size, density=density, strategy=strategy, rng=self.rng
        )
        live_cells = int(occupied.sum())
        lineage_ids = _sample_lineage_ids(
            seed_lineages=seed_lineages, count=live_cells, rng=self.rng
        )
        lineage[occupied] = lineage_ids
        gene[occupied] = _sample_gene_values(
            count=live_cells, strategy=strategy, rng=self.rng
        )
        charge[occupied] = self.rng.uniform(
            self.config["initial_conditions"]["initial_charge_min"],
            self.config["initial_conditions"]["initial_charge_max"],
            size=live_cells,
        )
        mutability[occupied] = np.clip(
            _sample_mutability_values(
                count=live_cells,
                base_mutability=base_mutability,
                strategy=strategy,
                rng=self.rng,
            ),
            self.config["params"]["min_mutability"],
            self.config["params"]["max_mutability"],
        )

        self.state = {
            "lineage": lineage,
            "gene": gene,
            "charge": charge,
            "mutability": mutability,
            "age": age,
            "lineage_counter": int(seed_lineages + 1),
            "step_index": 0,
            "last_births": 0,
            "last_deaths": 0,
            "last_change_rate": float(occupied.mean()),
            "last_alive_fraction": float(occupied.mean()),
            "last_budget_entropy": 0.0,
            "last_budget_utilization": 1.0,
            "last_budgeted_lineages": float(seed_lineages),
        }

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self.state = step_mutation_cells(self.state, self.rng, self.config)

    def render_frame(self) -> np.ndarray:
        return render_mutation_cells_frame(self.state)

    def get_state(self) -> dict[str, Any]:
        return {
            key: value.copy() if isinstance(value, np.ndarray) else value
            for key, value in self.state.items()
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.state = {
            key: value.copy() if isinstance(value, np.ndarray) else value
            for key, value in state.items()
        }

    def extract_metrics(self) -> dict[str, float]:
        return compute_metrics(self.state)

    def apply_perturbation(self, perturbation: dict[str, Any]) -> None:
        apply_mutation_cells_perturbation(
            self.state, self.config, perturbation, self.rng
        )

    def is_extinct(self) -> bool:
        return not bool((self.state["lineage"] > 0).any())


def _merge_config(
    defaults: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for section, values in overrides.items():
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged[section].update(values)
        else:
            merged[section] = values
    return merged


def _sample_occupied_sites(
    size: int, density: float, strategy: str, rng: np.random.Generator
) -> np.ndarray:
    total_cells = size * size
    count = int(np.clip(round(total_cells * density), 0, total_cells))
    mask = np.zeros(total_cells, dtype=bool)
    if count == 0:
        return mask.reshape(size, size)

    if strategy == "stratified":
        anchors = np.linspace(0, total_cells - 1, num=count, dtype=int)
        jitter = rng.integers(
            -max(1, total_cells // max(8 * count, 1)),
            max(2, total_cells // max(8 * count, 1) + 1),
            size=count,
        )
        chosen = np.clip(anchors + jitter, 0, total_cells - 1)
        mask[np.unique(chosen)] = True
        while int(mask.sum()) < count:
            fill_needed = count - int(mask.sum())
            candidates = rng.choice(total_cells, size=fill_needed, replace=False)
            mask[candidates] = True
        return mask.reshape(size, size)

    if strategy == "opposition":
        half = count // 2
        primary = rng.choice(total_cells, size=half, replace=False)
        opposite = total_cells - 1 - primary
        mask[primary] = True
        mask[opposite] = True
        while int(mask.sum()) < count:
            mask[int(rng.integers(0, total_cells))] = True
        return mask.reshape(size, size)

    chosen = rng.choice(total_cells, size=count, replace=False)
    mask[chosen] = True
    return mask.reshape(size, size)


def _sample_lineage_ids(
    seed_lineages: int, count: int, rng: np.random.Generator
) -> np.ndarray:
    if count <= 0:
        return np.asarray([], dtype=np.int32)
    lineage_cycle = np.tile(
        np.arange(1, seed_lineages + 1, dtype=np.int32),
        int(np.ceil(count / seed_lineages)),
    )
    lineage_ids = lineage_cycle[:count].copy()
    rng.shuffle(lineage_ids)
    return lineage_ids


def _sample_gene_values(
    count: int, strategy: str, rng: np.random.Generator
) -> np.ndarray:
    if count <= 0:
        return np.asarray([], dtype=np.float32)
    if strategy == "stratified":
        values = (np.arange(count, dtype=np.float32) + rng.random(count)) / max(
            1, count
        )
        rng.shuffle(values)
        return np.clip(values, 0.0, 1.0).astype(np.float32)
    if strategy == "opposition":
        half = (count + 1) // 2
        seeds = rng.random(half).astype(np.float32)
        values = np.concatenate([seeds, 1.0 - seeds])[:count]
        rng.shuffle(values)
        return values.astype(np.float32)
    return rng.random(count).astype(np.float32)


def _sample_mutability_values(
    count: int,
    base_mutability: float,
    strategy: str,
    rng: np.random.Generator,
) -> np.ndarray:
    if count <= 0:
        return np.asarray([], dtype=np.float32)
    scale = base_mutability * (0.28 if strategy == "stratified" else 0.4)
    values = base_mutability + rng.normal(0.0, scale, size=count)
    if strategy == "opposition":
        offsets = np.linspace(
            -base_mutability * 0.5, base_mutability * 0.5, num=count, dtype=np.float32
        )
        values = values + offsets
    return values.astype(np.float32)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run Mutation Cells standalone.")
    parser.add_argument("--steps", type=positive_int_argument, default=96)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=str, default="runs/mutation_cells_demo")
    args = parser.parse_args()

    runner = SimulationRunner(Path(args.output))
    candidate = CandidateConfig(
        substrate="mutation_cells", search_mode="standalone", seed=args.seed
    )
    substrate = MutationCellsSubstrate()
    run = runner.run_candidate(
        substrate, candidate, steps=args.steps, frame_stride=4, capture_state_every=16
    )
    print(run.summary_metrics)
    if run.video_path:
        print(run.video_path)


if __name__ == "__main__":
    _main()

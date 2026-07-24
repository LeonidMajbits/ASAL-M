from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from ...core import CandidateConfig, SimulationRunner
from ...core.limits import positive_int_argument
from .metrics import compute_metrics
from .perturb import apply_alpha_perturbation
from .render import render_alpha_frame
from .rules import step_alpha

ALPHA_ALIFE_DEFAULT_CONFIG: dict[str, dict[str, Any]] = {
    "params": {
        "mutation_rate": 0.12,
        "harvest_rate": 0.08,
        "energy_decay": 0.03,
        "crowding_cost": 0.08,
        "reproduction_cost": 0.35,
        "offspring_energy": 0.45,
        "death_energy": 0.05,
        "background_mortality": 0.002,
    },
    "rule_variants": {
        "survival_min": 1,
        "survival_max": 5,
        "birth_min": 2,
        "birth_max": 4,
    },
    "environment": {
        "grid_size": 64,
        "resource_regen": 0.08,
        "resource_diffusion": 0.08,
        "resource_floor": 0.2,
        "resource_ceiling": 1.0,
        "birth_resource_min": 0.1,
        "palette_size": 8,
    },
    "initial_conditions": {
        "density": 0.12,
        "seed_lineages": 6,
        "initial_energy_min": 0.3,
        "initial_energy_max": 1.1,
    },
}

ALPHA_ALIFE_DEFAULT_SEARCH_SPACE = {
    "params": {
        "mutation_rate": {"type": "float", "min": 0.01, "max": 0.35},
        "harvest_rate": {"type": "float", "min": 0.03, "max": 0.18},
        "energy_decay": {"type": "float", "min": 0.01, "max": 0.12},
        "crowding_cost": {"type": "float", "min": 0.02, "max": 0.2},
        "reproduction_cost": {"type": "float", "min": 0.15, "max": 0.8},
        "offspring_energy": {"type": "float", "min": 0.15, "max": 0.75},
        "background_mortality": {"type": "float", "min": 0.0, "max": 0.02},
    },
    "rule_variants": {
        "survival_min": {"type": "int", "min": 1, "max": 3},
        "survival_max": {"type": "int", "min": 4, "max": 7},
        "birth_min": {"type": "int", "min": 2, "max": 3},
        "birth_max": {"type": "int", "min": 3, "max": 6},
    },
    "environment": {
        "resource_regen": {"type": "float", "min": 0.01, "max": 0.15},
        "resource_diffusion": {"type": "float", "min": 0.02, "max": 0.25},
        "resource_floor": {"type": "float", "min": 0.05, "max": 0.4},
        "birth_resource_min": {"type": "float", "min": 0.04, "max": 0.25},
    },
    "initial_conditions": {
        "density": {"type": "float", "min": 0.04, "max": 0.24},
        "seed_lineages": {"type": "int", "min": 2, "max": 12},
        "initial_energy_min": {"type": "float", "min": 0.2, "max": 0.7},
        "initial_energy_max": {"type": "float", "min": 0.7, "max": 1.4},
    },
}


class AlphaALifeSubstrate:
    name = "alpha_alife"

    def __init__(self) -> None:
        self.config: dict[str, Any] = deepcopy(ALPHA_ALIFE_DEFAULT_CONFIG)
        self.rng = np.random.default_rng(0)
        self.state: dict[str, Any] = {}

    def reset(self, config: dict[str, Any], seed: int) -> None:
        self.config = _merge_config(ALPHA_ALIFE_DEFAULT_CONFIG, config)
        self.rng = np.random.default_rng(seed)
        size = int(self.config["environment"]["grid_size"])
        density = float(self.config["initial_conditions"]["density"])
        seed_lineages = int(self.config["initial_conditions"]["seed_lineages"])

        lineage = np.zeros((size, size), dtype=np.int32)
        species = np.zeros((size, size), dtype=np.int16)
        energy = np.zeros((size, size), dtype=np.float32)
        age = np.zeros((size, size), dtype=np.int16)
        resources = self.rng.uniform(
            self.config["environment"]["resource_floor"],
            self.config["environment"]["resource_ceiling"],
            size=(size, size),
        ).astype(np.float32)

        occupied = self.rng.random((size, size)) < density
        lineage_ids = self.rng.integers(
            1, seed_lineages + 1, size=int(occupied.sum()), endpoint=False
        )
        lineage[occupied] = lineage_ids
        species[occupied] = (
            (lineage_ids - 1) % self.config["environment"]["palette_size"]
        ) + 1
        energy[occupied] = self.rng.uniform(
            self.config["initial_conditions"]["initial_energy_min"],
            self.config["initial_conditions"]["initial_energy_max"],
            size=int(occupied.sum()),
        )

        self.state = {
            "species": species,
            "lineage": lineage,
            "energy": energy,
            "resources": resources,
            "age": age,
            "lineage_counter": int(seed_lineages + 1),
            "step_index": 0,
            "last_births": 0,
            "last_deaths": 0,
            "last_change_rate": float(occupied.mean()),
            "last_alive_fraction": float(occupied.mean()),
        }

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self.state = step_alpha(self.state, self.rng, self.config)

    def render_frame(self) -> np.ndarray:
        return render_alpha_frame(self.state)

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
        apply_alpha_perturbation(self.state, self.config, perturbation, self.rng)

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


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run Alpha ALife standalone.")
    parser.add_argument("--steps", type=positive_int_argument, default=96)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=str, default="runs/alpha_alife_demo")
    args = parser.parse_args()

    runner = SimulationRunner(Path(args.output))
    candidate = CandidateConfig(
        substrate="alpha_alife", search_mode="standalone", seed=args.seed
    )
    substrate = AlphaALifeSubstrate()
    run = runner.run_candidate(
        substrate, candidate, steps=args.steps, frame_stride=4, capture_state_every=16
    )
    print(run.summary_metrics)
    if run.video_path:
        print(run.video_path)


if __name__ == "__main__":
    _main()

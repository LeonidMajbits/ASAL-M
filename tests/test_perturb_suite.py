from __future__ import annotations

from asal_m.core.candidate import CandidateConfig
from asal_m.validation.perturb_suite import run_perturbation_suite


def test_perturbation_keeps_discovery_seed() -> None:
    candidate = CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=7,
        params={},
        rule_variants={},
        environment={"grid_size": 32},
        initial_conditions={"density": 0.15},
    )
    score, details = run_perturbation_suite(
        candidate,
        steps=24,
        perturbations=[{"kind": "wipe_patch", "size": 0.2}],
    )
    assert 0.0 <= score <= 1.0
    assert details
    assert all(item["seed"] == 7 for item in details)

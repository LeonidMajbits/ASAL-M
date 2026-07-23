from __future__ import annotations

from pathlib import Path

import yaml

from asal_m.substrates import create_substrate, list_substrates
from asal_m.search import run_search_experiment


def test_substrates_registered() -> None:
    names = list_substrates()
    assert "alpha_alife" in names
    assert "mutation_cells" in names
    for name in names:
        substrate = create_substrate(name)
        assert hasattr(substrate, "reset")
        assert hasattr(substrate, "step")
        assert hasattr(substrate, "extract_metrics")


def test_alpha_short_search_smoke(tmp_path: Path) -> None:
    experiment = yaml.safe_load(
        Path("asal_m/experiments/alpha_mainline.yaml").read_text(encoding="utf-8")
    )
    experiment["budget"] = 3
    experiment["steps"] = 24
    experiment["artifact_root"] = str(tmp_path / "runs")
    experiment["validation"]["interval"] = 100  # avoid full validation in smoke
    experiment["prefilter"] = {
        "min_steps": 1,
        "min_activity": 0.0,
        "min_occupancy": 0.0,
    }
    summary = run_search_experiment(experiment)
    assert summary["counts"]["evaluated"] >= 1

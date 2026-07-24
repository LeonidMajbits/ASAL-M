from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from asal_m.core.candidate import CandidateConfig
from asal_m.core import runner as runner_module
from asal_m.core.runner import SimulationRunner
from asal_m.search import run_search_experiment
from asal_m.substrates import create_substrate


def test_runner_save_artifacts_writes_relative_paths(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # Keep imports working from repo; only artifact writes are under tmp cwd.
    candidate = CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=1,
        environment={"grid_size": 24},
        initial_conditions={"density": 0.1},
    )
    runner = SimulationRunner("runs/artifact_write")
    run = runner.run_candidate(
        create_substrate("alpha_alife"),
        candidate,
        steps=8,
        frame_stride=2,
        capture_state_every=4,
        save_artifacts=True,
    )
    assert run.artifact_dir is not None
    assert (run.artifact_dir / "summary.json").exists()
    assert (run.artifact_dir / "candidate.json").exists()
    text = (run.artifact_dir / "summary.json").read_text(encoding="utf-8")
    assert ":\\\\" not in text.replace("/", "\\") or "runs" in text


def test_search_summary_redacts_absolute_artifact_paths(
    tmp_path: Path, monkeypatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    artifact_root = tmp_path / "private-artifacts"
    monkeypatch.chdir(checkout)
    experiment = {
        "name": "path_probe",
        "seed": 1,
        "substrate": "alpha_alife",
        "search_mode": "frontier",
        "budget": 1,
        "steps": 8,
        "frame_stride": 2,
        "capture_state_every": 4,
        "artifact_root": str(artifact_root),
        "target_metrics": {},
        "prefilter": {"min_steps": 1, "min_activity": 0.0, "min_occupancy": 0.0},
        "validation": {"interval": 0, "score_threshold": 999.0, "perturbations": []},
    }
    run_search_experiment(experiment)
    payload = json.loads(
        (artifact_root / "path_probe" / "experiment_summary.json").read_text(
            encoding="utf-8"
        )
    )
    rendered = json.dumps(payload)
    assert str(tmp_path) not in rendered
    assert payload["experiment"]["artifact_root"] == "private-artifacts"
    for winner in payload["winners"].values():
        if winner is None:
            continue
        for key in ("artifact_dir", "video_path", "trace_path"):
            assert not Path(winner[key]).is_absolute()


def test_mut_cells_short_search(tmp_path: Path) -> None:
    experiment = yaml.safe_load(
        Path("asal_m/experiments/mut_cells_mainline.yaml").read_text(encoding="utf-8")
    )
    experiment["budget"] = 2
    experiment["steps"] = 16
    experiment["artifact_root"] = str(tmp_path / "runs")
    experiment["validation"]["interval"] = 100
    experiment["prefilter"] = {
        "min_steps": 1,
        "min_activity": 0.0,
        "min_occupancy": 0.0,
    }
    summary = run_search_experiment(experiment)
    assert summary["counts"]["evaluated"] >= 1
    assert any(summary["winners"].values())


def test_promotion_mode_yaml_loads_and_runs_tiny(tmp_path: Path) -> None:
    experiment = yaml.safe_load(
        Path("asal_m/experiments/mut_cells_promotion.yaml").read_text(encoding="utf-8")
    )
    experiment["budget"] = 1
    experiment["steps"] = 12
    experiment["artifact_root"] = str(tmp_path / "runs")
    experiment["validation"]["interval"] = 100
    experiment["prefilter"] = {
        "min_steps": 1,
        "min_activity": 0.0,
        "min_occupancy": 0.0,
    }
    summary = run_search_experiment(experiment)
    assert "counts" in summary


def test_artifact_directories_remain_unique_at_the_same_timestamp(
    tmp_path: Path, monkeypatch
) -> None:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 23, 18, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(runner_module, "datetime", FrozenDatetime)
    candidate = CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=1,
    )
    runner = SimulationRunner(tmp_path)

    first = runner._create_artifact_dir(candidate)
    second = runner._create_artifact_dir(candidate)

    assert first != second
    assert first.name.endswith("20260723T180000000000Z")
    assert second.name.endswith("20260723T180000000000Z__001")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("budget", 0),
        ("budget", -1),
        ("budget", 1.0),
        ("budget", 1.9),
        ("budget", "1.0"),
        ("steps", 0),
        ("steps", -1),
        ("steps", 1.0),
        ("steps", 1.9),
        ("steps", "1.0"),
    ],
)
def test_search_rejects_non_positive_work_limits(
    tmp_path: Path, field: str, value: object
) -> None:
    experiment = {
        "name": "invalid_limits",
        "seed": 1,
        "substrate": "alpha_alife",
        "search_mode": "frontier",
        "budget": 1,
        "steps": 1,
        "artifact_root": str(tmp_path),
    }
    experiment[field] = value
    with pytest.raises(ValueError, match=rf"{field} must be a positive integer"):
        run_search_experiment(experiment)


def test_runner_rejects_non_positive_steps(tmp_path: Path) -> None:
    runner = SimulationRunner(tmp_path)
    candidate = CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=1,
    )
    with pytest.raises(ValueError, match="steps must be a positive integer"):
        runner.run_candidate(
            create_substrate("alpha_alife"),
            candidate,
            steps=0,
        )


@pytest.mark.parametrize("value", [1.0, 1.9, "1.0"])
def test_runner_rejects_non_integer_steps(tmp_path: Path, value: object) -> None:
    runner = SimulationRunner(tmp_path)
    candidate = CandidateConfig(
        substrate="alpha_alife",
        search_mode="frontier",
        seed=1,
    )
    with pytest.raises(ValueError, match="steps must be a positive integer"):
        runner.run_candidate(
            create_substrate("alpha_alife"),
            candidate,
            steps=value,
        )

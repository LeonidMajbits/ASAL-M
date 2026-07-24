from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from asal_m.analysis.compare_mutation_winners import main as compare_winners_main
from asal_m.analysis.export_winners import main as export_winners_main
from asal_m.analysis.inspect_artifacts import main as inspect_artifacts_main
from asal_m.analysis.plot_frontiers import main as plot_frontiers_main
from asal_m.analysis.summarize_run import main as summarize_run_main
from asal_m.analysis.validate_flagship import (
    DEFAULT_SPEC_LABEL,
    _load_spec,
    generate_flagship_report,
)


def test_packaged_flagship_spec_loads_without_checkout_path() -> None:
    spec, label = _load_spec(None)

    assert label == DEFAULT_SPEC_LABEL
    assert spec["kind"] == "flagship"
    assert spec["candidate"]["substrate"] == "mutation_cells"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("export_steps", 0),
        ("export_steps", -1),
        ("validation_steps", 0),
        ("validation_steps", -1),
    ],
)
def test_flagship_report_rejects_non_positive_steps(
    tmp_path: Path, field: str, value: int
) -> None:
    kwargs = {
        "output_dir": tmp_path / "output",
        "export_steps": 1,
        "validation_steps": 1,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match="must be a positive integer"):
        generate_flagship_report(None, **kwargs)
    assert not (tmp_path / "output").exists()


def test_flagship_writes_safe_json_markdown_and_yaml(
    tmp_path: Path, monkeypatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    private_root = tmp_path / "private"
    private_root.mkdir()
    monkeypatch.chdir(checkout)

    spec, _ = _load_spec(None)
    spec["source"] = {
        "source_artifact_dir": str(private_root / "source-candidate"),
        "summary_path": "C:" + r"\Users\person\private\experiment_summary.json",
    }
    spec_path = private_root / "flagship.yaml"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    payload, paths = generate_flagship_report(
        spec_path,
        output_dir=private_root / "output",
        export_steps=1,
        validation_steps=1,
    )

    texts = [
        paths["json"].read_text(encoding="utf-8"),
        paths["md"].read_text(encoding="utf-8"),
        paths["spec_copy"].read_text(encoding="utf-8"),
    ]
    combined = "\n".join(texts)
    assert str(tmp_path) not in combined
    assert "C:" not in combined
    assert "Users" not in combined
    assert payload["spec_path"] == "flagship.yaml"
    assert payload["source"]["source_artifact_dir"] == "source-candidate"
    assert payload["source"]["summary_path"] == "experiment_summary.json"
    for key in ("artifact_dir", "video_path", "trace_path"):
        assert "\\" not in payload["export"][key]
    assert payload["export"]["artifact_dir"].startswith("replay_artifacts/")


def test_mutation_comparison_sanitizes_inputs_and_winner_paths(
    tmp_path: Path, monkeypatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    summary_path = private / "experiment_summary.json"
    artifact_path = private / "candidate-artifact"
    summary_path.write_text(
        json.dumps(
            {
                "experiment": {"name": "private-run"},
                "winners": {
                    "mainline": {
                        "artifact_dir": str(artifact_path),
                        "candidate": {
                            "search_mode": "promotion",
                            "rule_variants": {"budget_mode": "dynamic"},
                            "initial_conditions": {
                                "initialization_strategy": "stratified"
                            },
                            "params": {"lineage_budget_strength": 0.9},
                        },
                        "total_score": 0.9,
                        "score_components": {},
                        "summary_metrics": {},
                        "validation": {"promotion_score": 0.8},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    output_dir = checkout / "comparison"
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare-mutation-winners",
            str(summary_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    compare_winners_main()

    json_text = (output_dir / "mutation_winner_comparison.json").read_text(
        encoding="utf-8"
    )
    markdown_text = (output_dir / "mutation_winner_comparison.md").read_text(
        encoding="utf-8"
    )
    combined = json_text + markdown_text
    assert str(tmp_path) not in combined
    assert "experiment_summary.json" in combined
    assert "candidate-artifact" in combined


def test_export_and_summary_commands_handle_winner_and_empty_roles(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    summary_path = tmp_path / "experiment_summary.json"
    output_path = tmp_path / "public" / "winners.json"
    output_path.parent.mkdir()
    summary_path.write_text(
        json.dumps(
            {
                "counts": {"evaluated": 1},
                "winners": {
                    "mainline": {
                        "artifact_dir": "C:" + r"\Users\person\private\candidate-a",
                        "total_score": 0.8,
                        "summary_metrics": {
                            "occupancy": 0.7,
                            "diversity": 0.6,
                        },
                    },
                    "novelty": None,
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export-winners",
            str(summary_path),
            "--output",
            str(output_path),
        ],
    )
    export_winners_main()
    exported = output_path.read_text(encoding="utf-8")
    assert "C:" not in exported
    assert "candidate-a" in exported

    monkeypatch.setattr(sys, "argv", ["summarize-run", str(summary_path)])
    summarize_run_main()
    stdout = capsys.readouterr().out
    assert '"evaluated": 1' in stdout
    assert "mainline: total=0.800" in stdout
    assert "novelty: none" in stdout


def test_export_winners_sanitizes_embedded_linux_path_boundaries(
    tmp_path: Path, monkeypatch
) -> None:
    summary_path = tmp_path / "experiment_summary.json"
    output_path = tmp_path / "winners.json"
    private_directory = "/" + "workspace/Jane Doe/Private Lab"
    summary_path.write_text(
        json.dumps(
            {
                "winners": {
                    "mainline": {
                        "artifact_note": f"loaded from {private_directory}\nnext",
                        "table_note": f"| input={private_directory} |",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export-winners",
            str(summary_path),
            "--output",
            str(output_path),
        ],
    )

    export_winners_main()

    exported = output_path.read_text(encoding="utf-8")
    assert "Jane Doe" not in exported
    assert "/" + "workspace/" not in exported
    assert "loaded from Private Lab\\nnext" in exported
    assert "| input=Private Lab |" in exported


def test_artifact_inspection_command_defaults_to_no_machine_details(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    artifact_root = tmp_path / "artifacts"
    (artifact_root / "candidate-a").mkdir(parents=True)
    output_dir = tmp_path / "report"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect-artifacts",
            "--root",
            str(artifact_root),
            "--output-dir",
            str(output_dir),
        ],
    )

    inspect_artifacts_main()

    payload = json.loads(
        (output_dir / "artifact_report.json").read_text(encoding="utf-8")
    )
    stdout = capsys.readouterr().out
    assert payload["machine_details_included"] is False
    assert "machine_details" not in payload
    assert "machine_details=omitted" in stdout


def test_plot_command_rejects_summary_without_winners_before_optional_import(
    tmp_path: Path, monkeypatch
) -> None:
    summary_path = tmp_path / "empty_summary.json"
    summary_path.write_text('{"winners": {}}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["plot-frontiers", str(summary_path)])

    with pytest.raises(ValueError, match="No winners"):
        plot_frontiers_main()

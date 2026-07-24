from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import yaml

from asal_m.core.artifacts import (
    GPUStatus,
    detect_gpu_status,
    inspect_artifact_root,
    write_artifact_report,
)
from asal_m.public_output import public_path, to_public_data


def test_public_path_redacts_foreign_absolute_roots(tmp_path: Path) -> None:
    base = tmp_path / "checkout"
    base.mkdir()

    assert (
        public_path(
            r"C:\Users\person\private\result.json",  # public-scan: host-pattern
            base_dir=base,
        )
        == "result.json"
    )
    assert (
        public_path(
            r"\\server\secret-share\result.json",  # public-scan: host-pattern
            base_dir=base,
        )
        == "result.json"
    )
    assert public_path(r"\Users\person\result.json", base_dir=base) == "result.json"
    assert (
        public_path(
            "/home/person/private/result.json",  # public-scan: host-pattern
            base_dir=base,
        )
        == "result.json"
    )
    assert (
        public_path(
            "/Users/person/private/result.json",  # public-scan: host-pattern
            base_dir=base,
        )
        == "result.json"
    )
    assert (
        public_path(  # public-scan: host-pattern
            "/tmp/private/result.json",  # public-scan: host-pattern
            base_dir=base,
        )
        == "result.json"
    )


def test_public_path_does_not_duplicate_a_relative_base_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "flagship-smoke"
    output.mkdir()
    monkeypatch.chdir(tmp_path)

    prefixed = Path("flagship-smoke/replay_artifacts/candidate/summary.json")
    within_base = Path("replay_artifacts/candidate/summary.json")

    assert public_path(prefixed, base_dir=output) == (
        "replay_artifacts/candidate/summary.json"
    )
    assert public_path(within_base, base_dir=output) == (
        "replay_artifacts/candidate/summary.json"
    )


def test_public_data_handles_nested_values_and_normalizes_time(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    local = tmp_path / "runs" / "summary.json"
    outside = tmp_path.parent / "private" / "source.yaml"
    timestamp = datetime(
        2026,
        7,
        23,
        10,
        0,
        tzinfo=timezone(timedelta(hours=-4)),
    )

    public = to_public_data(
        {
            "local": local,
            "outside": str(outside),
            "array": np.asarray([1, 2], dtype=np.int64),
            "nested": [{"timestamp": timestamp}],
        }
    )

    assert public == {
        "local": "runs/summary.json",
        "outside": "source.yaml",
        "array": [1, 2],
        "nested": [{"timestamp": "2026-07-23T14:00:00Z"}],
    }


def test_artifact_report_is_safe_by_default(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    artifact_root = tmp_path / "private-artifacts"
    child = artifact_root / "candidate-a"
    child.mkdir(parents=True)
    (child / "summary.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(checkout)

    report = inspect_artifact_root(artifact_root)
    assert report["artifact_root"] == "private-artifacts"
    assert report["children"][0]["path"] == "candidate-a"
    assert report["generated_at"].endswith("Z")
    assert report["machine_details_included"] is False
    assert "machine_details" not in report
    assert "gpu" not in report

    outputs = write_artifact_report(report, checkout / "report")
    written_json = outputs["json"].read_text(encoding="utf-8")
    written_markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert str(tmp_path) not in written_json
    assert str(tmp_path) not in written_markdown
    assert "## Machine details" not in written_markdown


def test_artifact_machine_details_require_explicit_opt_in(
    tmp_path: Path, monkeypatch
) -> None:
    artifact_root = tmp_path / "artifacts"
    (artifact_root / "candidate-a").mkdir(parents=True)
    monkeypatch.setattr(
        "asal_m.core.artifacts.detect_gpu_status",
        lambda: GPUStatus(
            available=True,
            name="Example GPU",
            driver_version="1.2.3",
            cuda_version="13.0",
            memory_total_mib=1024,
            memory_used_mib=64,
            utilization_gpu_pct=3,
            safe_for_heavy_jobs=True,
            recommendation="Available.",
        ),
    )

    report = inspect_artifact_root(
        artifact_root,
        include_machine_details=True,
        path_base=tmp_path,
    )
    assert report["machine_details_included"] is True
    assert report["machine_details"]["gpu"]["name"] == "Example GPU"


def test_gpu_detection_does_not_execute_an_unresolved_path_command(
    monkeypatch,
) -> None:
    monkeypatch.setattr("asal_m.core.artifacts._find_nvidia_smi", lambda: None)

    status = detect_gpu_status()

    assert status.available is False
    assert status.recommendation == "nvidia-smi not found. Staying CPU-only."


def test_public_data_sanitizes_json_markdown_and_yaml_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = {
        "windows": r"C:\Users\person\private\candidate.json",  # public-scan: host-pattern
        "unc": r"\\server\share\winner.json",  # public-scan: host-pattern
        "posix": "/home/person/private/spec.yaml",  # public-scan: host-pattern
    }
    cleaned = to_public_data(payload)

    json_text = json.dumps(cleaned)
    yaml_text = yaml.safe_dump(cleaned)
    markdown = "\n".join(f"- {key}: `{value}`" for key, value in cleaned.items())
    combined = json_text + yaml_text + markdown

    assert "C:" not in combined
    assert "server" not in combined
    assert "/home/" not in combined  # public-scan: host-pattern
    assert cleaned == {
        "windows": "candidate.json",
        "unc": "winner.json",
        "posix": "spec.yaml",
    }


def test_public_data_redacts_absolute_paths_embedded_in_text() -> None:
    cleaned = to_public_data(
        {
            "windows": (
                r"loaded from C:\Users\person\private\candidate.json"  # public-scan: host-pattern
            ),
            "posix": (
                "source=/home/person/private/spec.yaml"  # public-scan: host-pattern
            ),
            "url": "https://example.org/tmp/public/result.json",  # public-scan: host-pattern
        }
    )

    assert cleaned == {
        "windows": "loaded from candidate.json",
        "posix": "source=spec.yaml",
        "url": "https://example.org/tmp/public/result.json",  # public-scan: host-pattern
    }


def test_public_data_redacts_spaced_paths_and_mapping_keys() -> None:
    private_path = "B:" + "\\Main " + "Workspace\\Private " + "Workspace\\secret.txt"
    cleaned = to_public_data(
        {
            private_path: private_path,
            "message": f"loaded from {private_path} and continued",
        }
    )

    assert cleaned == {
        "secret.txt": "secret.txt",
        "message": "loaded from secret.txt and continued",
    }
    rendered = json.dumps(cleaned)
    assert "Main Workspace" not in rendered
    assert "Private Workspace" not in rendered


def test_public_data_redacts_conjunctions_and_quoted_directories_in_paths() -> None:
    file_path = (
        "B:" + "\\Research and Development\\Private Workspace\\candidate result.json"
    )
    directory_path = "B:" + "\\Research and Development\\Private Workspace"

    cleaned = to_public_data(
        {
            "file": f"loaded from {file_path} and continued",
            "quoted_directory": f"root='{directory_path}'",
        }
    )

    assert cleaned == {
        "file": "loaded from candidate result.json and continued",
        "quoted_directory": "root='Private Workspace'",
    }
    rendered = json.dumps(cleaned)
    assert "Research and Development" not in rendered


def test_public_data_rejects_mapping_key_collision_after_sanitization() -> None:
    with pytest.raises(
        ValueError,
        match="duplicate mapping key",
    ):
        to_public_data(
            {
                "C:" + r"\private-a\result.json": 1,
                "D:" + r"\private-b\result.json": 2,
            }
        )

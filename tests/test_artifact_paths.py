from __future__ import annotations

from pathlib import Path

from asal_m.core.runner import _public_path_string, _to_serializable
from examples.public_demo.regenerate import _assert_no_host_paths


def test_public_path_string_prefers_relative(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "runs" / "demo" / "summary.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")
    rendered = _public_path_string(target)
    assert not rendered.startswith("B:")
    assert rendered.replace("\\", "/").endswith("runs/demo/summary.json")


def test_serializable_redacts_drive_rooted_strings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = {
        "artifact_dir": str((tmp_path / "runs" / "x").resolve()),
        "nested": {"path": str((tmp_path / "runs" / "y" / "z.json").resolve())},
    }
    cleaned = _to_serializable(payload)
    text = str(cleaned)
    # Should not retain a Windows drive root in the serialized form when under cwd.
    assert ":\\" not in text.replace("/", "\\") or cleaned["artifact_dir"].startswith(
        "runs"
    )


def test_serializable_redacts_paths_outside_working_tree(
    tmp_path: Path, monkeypatch
) -> None:
    cwd = tmp_path / "checkout"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    outside = tmp_path / "private" / "summary.json"
    cleaned = _to_serializable({"path": outside, "string_path": str(outside)})
    assert cleaned == {"path": "summary.json", "string_path": "summary.json"}


def test_postcard_guard_rejects_cross_platform_host_paths() -> None:
    escaped_separator = "\\" * 2
    for value in (
        '{"path": "D:'
        + escaped_separator
        + "private"
        + escaped_separator
        + 'run.json"}',
        '{"path": "'
        + escaped_separator * 2
        + "server"
        + escaped_separator
        + "share"
        + escaped_separator
        + 'run.json"}',
        r'{"path": "/' + r'home/user/run.json"}',
        r'{"path": "/' + r'Users/person/run.json"}',
        r'{"path": "/' + r'root/user/run.json"}',
        r'{"path": "/' + r'workspace/user/run.json"}',
        r'{"path": "/' + r'opt/project/run.json"}',
    ):
        try:
            _assert_no_host_paths(value)
        except RuntimeError:
            continue
        raise AssertionError(f"host path was accepted: {value}")


def test_postcard_guard_accepts_repo_relative_paths() -> None:
    _assert_no_host_paths(r'{"path": "examples/public_demo/benchmark.json"}')

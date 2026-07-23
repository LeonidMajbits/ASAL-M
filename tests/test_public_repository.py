from __future__ import annotations

import zipfile
from pathlib import Path

from tools.verify_public_repository import (
    _commit_identity_errors,
    _github_pull_request_merge_commit,
    _scan_text,
    scan_archive,
    verify,
)


def test_current_prospective_repository_passes_public_scan() -> None:
    file_count, text_count, archive_count = verify()

    assert file_count >= 100
    assert text_count >= 80
    assert archive_count == 0


def test_public_scan_rejects_host_paths_secrets_email_and_internal_names() -> None:
    text = "\n".join(
        (
            "C:" + r"\Users\person\private\result.json",
            "Grok " + "Operator Lab",
            "person" + "@mail" + ".invalid",
            "api_" + "key='abcdefghijklmnop1234'",
        )
    )

    errors = _scan_text("docs/bad.txt", text)

    assert any("absolute host path" in error for error in errors)
    assert any("internal workspace marker" in error for error in errors)
    assert any("non-public email" in error for error in errors)
    assert any("secret-like" in error for error in errors)


def test_public_scan_allows_noreply_identity_and_relative_paths() -> None:
    errors = _scan_text(
        "docs/good.txt",
        "\n".join(
            (
                "runs/example/summary.json",
                "77941374+LeonidMajbits@users.noreply.github.com",
            )
        ),
    )

    assert errors == []


def test_identity_scan_ignores_only_the_confirmed_github_pr_merge() -> None:
    merge = "a" * 40
    head = "b" * 40
    noreply = "77941374+LeonidMajbits@users.noreply.github.com"
    rows = (
        f"{merge}\t{noreply}\t{'noreply' + '@github.com'}",
        f"{head}\t{noreply}\t{noreply}",
    )

    assert _commit_identity_errors(rows, ignored_commit=merge) == []
    assert any(
        "committer email" in error
        for error in _commit_identity_errors(rows, ignored_commit=None)
    )


def test_github_pr_merge_requires_event_sha_and_exactly_two_parents(
    tmp_path: Path, monkeypatch
) -> None:
    merge = "a" * 40
    base = "b" * 40
    head = "c" * 40

    def fake_run(*_args, **_kwargs):
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": f"{merge} {base} {head}\n",
            },
        )()

    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_SHA", merge)
    monkeypatch.setattr(
        "tools.verify_public_repository.subprocess.run",
        fake_run,
    )

    assert _github_pull_request_merge_commit(tmp_path) == merge

    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    assert _github_pull_request_merge_commit(tmp_path) is None


def test_archive_scan_checks_text_and_path_names(tmp_path: Path) -> None:
    safe_archive = tmp_path / "safe.whl"
    with zipfile.ZipFile(safe_archive, "w") as archive:
        archive.writestr("asal_m/module.py", "VALUE = 'safe'\n")
    errors, text_count = scan_archive(safe_archive)
    assert errors == []
    assert text_count == 1

    unsafe_archive = tmp_path / "unsafe.whl"
    with zipfile.ZipFile(unsafe_archive, "w") as archive:
        archive.writestr("runs/private.txt", "/home/person/private/result.json")
    errors, _ = scan_archive(unsafe_archive)
    assert any("forbidden public path component" in error for error in errors)
    assert any("absolute host path" in error for error in errors)

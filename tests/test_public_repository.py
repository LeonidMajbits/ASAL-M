from __future__ import annotations

import hashlib
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from tools.verify_public_repository import (
    _commit_identity_errors,
    _commit_signature_errors,
    _contains_internal_marker,
    _decode_text,
    _github_pull_request_merge_commit,
    _scan_text,
    scan_archive,
    scan_release_file,
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
            "person" + "@mail" + ".invalid",
            "api_" + "key='abcdefghijklmnop1234'",
        )
    )

    errors = _scan_text("docs/bad.txt", text)

    assert any("absolute host path" in error for error in errors)
    assert any("non-public email" in error for error in errors)
    assert any("secret-like" in error for error in errors)


def test_internal_marker_matching_uses_only_normalized_digests() -> None:
    marker = "fixture confidential workspace"
    digest = hashlib.sha256(marker.encode("utf-8")).hexdigest()

    assert _contains_internal_marker(
        "path/Fixture + Confidential + Workspace/output",
        frozenset({digest}),
    )
    assert not _contains_internal_marker(
        "fixture public workspace",
        frozenset({digest}),
    )


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


def test_host_path_fixture_annotation_is_line_scoped() -> None:
    text = "\n".join(
        (
            "C:" + r"\fixture\path.json  # public-scan: host-pattern",
            "C:" + r"\private\result.json",
        )
    )

    errors = _scan_text("tests/probe.py", text)

    assert len([error for error in errors if "absolute host path" in error]) == 1
    assert errors[0].startswith("tests/probe.py:2:")


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
    other_noreply = "12345+OtherMaintainer@users.noreply.github.com"
    assert any(
        "maintainer noreply" in error
        for error in _commit_identity_errors(
            (f"{head}\t{other_noreply}\t{noreply}",),
            ignored_commit=None,
        )
    )


def test_signature_scan_allows_only_good_or_exact_legacy_commits() -> None:
    legacy = "aea4d2b68979d4fe63f926e04e7ee5326deaa0fe"
    good = "a" * 40
    bad = "b" * 40
    merge = "c" * 40
    noreply = "77941374+LeonidMajbits@users.noreply.github.com"
    rows = (
        f"{legacy}\t{noreply}\t{noreply}\tN\t",
        (
            f"{good}\t{noreply}\t{noreply}\tG\t"
            "SHA256:AcVmWdXtxjOJagwIlL635w7WdQzOvHK3d144G0HC6ng"
        ),
        f"{bad}\t{noreply}\t{noreply}\tN\t",
        f"{merge}\t{noreply}\t{'noreply' + '@github.com'}\tN\t",
    )

    errors = _commit_signature_errors(rows, ignored_commit=merge)

    assert errors == [f"history:{bad}: commit does not have a valid signature"]


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


def test_history_scanning_ci_jobs_fetch_complete_history() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    )

    for job_name in ("test", "package"):
        checkout = next(
            step
            for step in workflow["jobs"][job_name]["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout["with"]["fetch-depth"] == 0
        assert checkout["with"]["persist-credentials"] is False


def test_release_workflow_attests_sbom_and_uses_pinned_actions() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["release"]
    permissions = job["permissions"]

    assert permissions == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
        "artifact-metadata": "write",
    }
    action_steps = [step["uses"] for step in job["steps"] if "uses" in step]
    assert action_steps == [
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
        "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6",
        "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    ]
    assert job["steps"][-2]["with"]["sbom-path"] == "dist/*.spdx.json"
    version_step = next(
        step for step in job["steps"] if step["name"].startswith("Require tag")
    )
    assert "GITHUB_REF_NAME" in version_step["run"]
    assert 'expected = f"v{version}"' in version_step["run"]
    sbom_step = next(
        step for step in job["steps"] if step["name"].startswith("Build deterministic")
    )
    assert "-c requirements-repro.txt" in sbom_step["run"]


def test_archive_scan_checks_text_and_path_names(tmp_path: Path) -> None:
    safe_archive = tmp_path / "safe.whl"
    with zipfile.ZipFile(safe_archive, "w") as archive:
        archive.writestr("asal_m/module.py", "VALUE = 'safe'\n")
    errors, text_count = scan_archive(safe_archive)
    assert errors == []
    assert text_count == 1

    unsafe_archive = tmp_path / "unsafe.whl"
    with zipfile.ZipFile(unsafe_archive, "w") as archive:
        archive.writestr(
            "runs/private.txt",
            "/home/person/private/result.json",  # public-scan: host-pattern
        )
    errors, _ = scan_archive(unsafe_archive)
    assert any("forbidden public path component" in error for error in errors)
    assert any("absolute host path" in error for error in errors)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _audit_repository(tmp_path: Path) -> Path:
    root = tmp_path / "audit-repository"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Audit Fixture")
    _git(
        root,
        "config",
        "user.email",
        "77941374+LeonidMajbits@users.noreply.github.com",
    )
    return root


def _secret(suffix: str = "A") -> str:
    return "sk-" + suffix * 30


def test_prospective_scan_reads_staged_blob_not_clean_worktree(
    tmp_path: Path,
) -> None:
    root = _audit_repository(tmp_path)
    probe = root / "probe.txt"
    probe.write_text(f"token='{_secret()}'\n", encoding="utf-8")
    _git(root, "add", "probe.txt")
    probe.write_text("safe worktree\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="secret-like content"):
        verify(root=root)


def test_history_scan_rejects_secret_in_old_blob(tmp_path: Path) -> None:
    root = _audit_repository(tmp_path)
    probe = root / "probe.txt"
    probe.write_text(f"token='{_secret('B')}'\n", encoding="utf-8")
    _git(root, "add", "probe.txt")
    _git(root, "commit", "-qm", "first safe message")
    probe.write_text("safe current content\n", encoding="utf-8")
    _git(root, "commit", "-qam", "second safe message")

    with pytest.raises(AssertionError, match=r"history:blob:.*secret-like"):
        verify(root=root)


def test_history_scan_rejects_secret_in_commit_message(tmp_path: Path) -> None:
    root = _audit_repository(tmp_path)
    (root / "probe.txt").write_text("safe\n", encoding="utf-8")
    _git(root, "add", "probe.txt")
    _git(root, "commit", "-qm", f"message {_secret('C')}")

    with pytest.raises(AssertionError, match=r"history:commit:.*secret-like"):
        verify(root=root)


def test_history_scan_rejects_secret_in_annotated_tag_message(
    tmp_path: Path,
) -> None:
    root = _audit_repository(tmp_path)
    (root / "probe.txt").write_text("safe\n", encoding="utf-8")
    _git(root, "add", "probe.txt")
    _git(root, "commit", "-qm", "safe")
    _git(root, "tag", "-a", "probe", "-m", f"tag {_secret('D')}")

    with pytest.raises(AssertionError, match=r"history:refs/tags/probe:.*secret-like"):
        verify(root=root)


@pytest.mark.parametrize(
    "token",
    [
        "ghp_" + "E" * 36,
        "github_pat_" + "F" * 60,
        "AKIA" + "G" * 16,
    ],
)
def test_public_scan_rejects_common_provider_token_shapes(token: str) -> None:
    assert any(
        "secret-like content" in error for error in _scan_text("probe.txt", token)
    )


def test_utf16_payload_is_decoded_and_scanned(tmp_path: Path) -> None:
    text = f"token='{_secret('H')}'"
    assert _decode_text(text.encode("utf-16")) == text

    archive_path = tmp_path / "utf16.whl"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("asal_m/probe.txt", text.encode("utf-16"))
    errors, text_count = scan_archive(archive_path)

    assert text_count == 1
    assert any("secret-like content" in error for error in errors)


def test_plain_release_metadata_is_scanned(tmp_path: Path) -> None:
    metadata = tmp_path / "release.spdx.json"
    metadata.write_text(
        '{"token": "' + "ghp_" + "J" * 36 + '"}\n',
        encoding="utf-8",
    )

    errors, text_count = scan_release_file(metadata)

    assert text_count == 1
    assert any("secret-like content" in error for error in errors)

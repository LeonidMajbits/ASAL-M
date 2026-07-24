#!/usr/bin/env python3
"""Verify repository history, prospective public files, and built archives."""

from __future__ import annotations

import argparse
import codecs
import hashlib
import os
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATH_PARTS = {
    ".env",
    ".git",
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "runs",
    "secrets",
    "venv",
    "vendor",
}
FORBIDDEN_PATH_PREFIXES = {
    "docs/assets",
    "examples/public_demo/findings",
}
# SHA-256 digests of normalized three-word workspace labels. Keeping only
# digests prevents the verifier from republishing the private labels it blocks.
INTERNAL_MARKER_DIGESTS = frozenset(
    {
        "c0fd2ab5945220b4f44b1b40363393d073cca5032ac9a65b4ecf833619457486",
        "bae64a43cabe26c9d4246aa0cfdfec0a6e79a8b2da508ed12923be42fe2f0b02",
        "826c81eef6de410d011a83d6c0515c91d36d260b8d595d281a06da069356b051",
    }
)
# These published v0.1.1-era blobs contain only the already disclosed
# non-sensitive workspace-label fixtures. Their exact object IDs are retained
# as a narrow historical baseline; every other finding in them still fails.
ACKNOWLEDGED_HISTORY_INTERNAL_MARKER_BLOBS = frozenset(
    {
        "8148e41a95431c333846fc9bd7638661e056e2eb",
        "1f67b362da21d43be3a5b54f812c331ca64c762c",
        "1e0f46b5a5e714f54d38d1eb1b99edce72de898e",
        "70c7a547f6d23f42e4fa487d600fe8294a20bc4a",
        "6333609f2595cae01563668a02a165f23a0fc1a9",
    }
)
# Exact published blobs containing only synthetic host-path fixtures or the
# verifier regexes that detect them. Only the host-path finding is suppressed.
ACKNOWLEDGED_HISTORY_HOST_FIXTURE_BLOBS = frozenset(
    {
        "16e430b571bf77508fe2627bc4bc30d750208db4",
        "1e0f46b5a5e714f54d38d1eb1b99edce72de898e",
        "1f67b362da21d43be3a5b54f812c331ca64c762c",
        "246c5c25771780f16ceee89a65d12600a02009a3",
        "4256f73ffab4ea62f45e725bb00ad6bfe335553f",
        "6333609f2595cae01563668a02a165f23a0fc1a9",
        "70c7a547f6d23f42e4fa487d600fe8294a20bc4a",
        "7290917163e7698d2fe52591564d4c9d8d34e70a",
        "8148e41a95431c333846fc9bd7638661e056e2eb",
        "83b5906e35b60b30bd6d8d5cf2185dfca618a28e",
        "89b0bf6fd9d168f71aafa3a23807f581d5d00fbf",
        "a88a608ce36c489fefaa042a64f8b2632a504645",
        "e3fc9acf755b55a8c86de829022540b2e8eab8a8",
        "e84e1e108666c1fe1ca5cbad743ab2f7315f293d",
        "fe7fc9be60f7c316f3ee524fad647fd7f97accc0",
    }
)
ACKNOWLEDGED_UNSIGNED_COMMITS = frozenset(
    {
        "aea4d2b68979d4fe63f926e04e7ee5326deaa0fe",
        "e1279df342606e47ee32e4395984b1af6836d3be",
        "b167f2a933ed24432d6cf8c8eff29710fadb5828",
        "3bb6b707ae9d881a057cba74d63594250792ac58",
    }
)
ACKNOWLEDGED_UNSIGNED_TAG_OBJECTS = frozenset(
    {
        "e2f089d8bfbcd36b0d9f21ee3286683ac3929e3c",
        "02be4aa24fb6ddeb7b11a0eac86bf30f10c78b35",
    }
)
RELEASE_SIGNING_FINGERPRINT = "SHA256:AcVmWdXtxjOJagwIlL635w7WdQzOvHK3d144G0HC6ng"
MAINTAINER_NOREPLY_EMAIL = "77941374+LeonidMajbits@users.noreply.github.com"
HOST_PATTERNS = (
    re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]"),
    re.compile(r"\\\\[^\\\s]+[\\/]"),  # public-scan: host-pattern
    re.compile(r"/(?:Users|home|tmp)/", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"\b(?:AKIA|ASIA|A3T[A-Z0-9]|AGPA|AIDA|ANPA|ANVA|AROA|AIPA)"
        r"[A-Z0-9]{16}\b"
    ),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}['\"]?"
    ),
)
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
ALLOWED_EMAIL_SUFFIXES = (
    "@users.noreply.github.com",
    "@example.com",
    "@example.org",
    "@localhost",
)


def prospective_public_files(root: Path = ROOT) -> list[Path]:
    """Return tracked plus untracked, non-ignored files for the next commit."""
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=True,
        capture_output=True,
    )
    return sorted(
        Path(item.decode("utf-8")) for item in completed.stdout.split(b"\0") if item
    )


def _index_entries(root: Path) -> tuple[dict[Path, tuple[str, str]], list[str]]:
    """Return stage-zero index entries and fail-closed conflict diagnostics."""
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "-z"],
        check=True,
        capture_output=True,
    )
    entries: dict[Path, tuple[str, str]] = {}
    errors: list[str] = []
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        relative = Path(raw_path.decode("utf-8"))
        if stage != "0":
            errors.append(
                f"{relative.as_posix()}: unresolved Git index conflict at stage {stage}"
            )
            continue
        if object_id == "0" * 40:
            errors.append(
                f"{relative.as_posix()}: intent-to-add entry has no staged blob"
            )
            continue
        entries[relative] = (mode, object_id)
    return entries, errors


def _git_object(root: Path, object_type: str, object_id: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), "cat-file", object_type, object_id],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def verify_commit_identity(root: Path = ROOT) -> list[str]:
    """Require noreply identities and signatures outside the legacy baseline."""
    ignored_commit = _github_pull_request_merge_commit(root)
    allowed_signers = root / "docs" / "keys" / "allowed_signers"
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            f"gpg.ssh.allowedSignersFile={allowed_signers}",
            "log",
            "--all",
            "HEAD",
            "--format=%H%x09%ae%x09%ce%x09%G?%x09%GF",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 128:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "--all",
                "--format=%H%x09%ae%x09%ce%x09%G?%x09%GF",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        completed.check_returncode()
    errors = _commit_identity_errors(
        completed.stdout.splitlines(),
        ignored_commit=ignored_commit,
    )
    errors.extend(
        _commit_signature_errors(
            completed.stdout.splitlines(),
            ignored_commit=ignored_commit,
        )
    )
    tags = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "for-each-ref",
            "--format=%(refname)%09%(objecttype)%09%(objectname)%09%(taggeremail)",
            "refs/tags",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for row in tags.stdout.splitlines():
        reference, object_type, object_id, tagger_email = row.split("\t")
        if object_type != "tag":
            errors.append(f"history:{reference}: release tag is not annotated")
            continue
        email = tagger_email.strip().strip("<>")
        if email.casefold() != MAINTAINER_NOREPLY_EMAIL.casefold():
            errors.append(
                f"history:{reference}: tagger email is not the maintainer noreply address"
            )
        if object_id in ACKNOWLEDGED_UNSIGNED_TAG_OBJECTS:
            continue
        raw_tag = _git_object(root, "tag", object_id)
        if b"-----BEGIN SSH SIGNATURE-----" not in raw_tag:
            errors.append(f"history:{reference}: annotated tag is not SSH-signed")
            continue
        verified = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                f"gpg.ssh.allowedSignersFile={allowed_signers}",
                "verify-tag",
                "--raw",
                reference,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if verified.returncode != 0:
            errors.append(
                f"history:{reference}: annotated tag does not have a valid signature"
            )
    return errors


def scan_history(root: Path = ROOT) -> tuple[list[str], int]:
    """Scan reachable commit/tag messages, historical paths, and blob bytes."""
    errors: list[str] = []
    text_count = 0
    revisions = _reachable_revisions(root)

    for commit in revisions:
        raw_commit = _git_object(root, "commit", commit)
        message = raw_commit.partition(b"\n\n")[2]
        text = _decode_text(message)
        if text is not None:
            text_count += 1
            errors.extend(
                f"history:commit:{commit}:{error}"
                for error in _scan_text("commit-message.txt", text)
            )
        tree_paths = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-tree",
                "-r",
                "-z",
                "--name-only",
                commit,
            ],
            check=True,
            capture_output=True,
        )
        for raw_path in tree_paths.stdout.split(b"\0"):
            if not raw_path:
                continue
            historical_path = raw_path.decode("utf-8")
            errors.extend(
                f"history:commit:{commit}:{error}"
                for error in _scan_path(historical_path)
            )

    object_rows = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--objects", "--all", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if object_rows.returncode not in (0, 128):
        object_rows.check_returncode()

    seen_objects: set[str] = set()
    for row in object_rows.stdout.splitlines():
        object_id, _, historical_path = row.partition(" ")
        if object_id in seen_objects:
            continue
        seen_objects.add(object_id)
        object_type = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-t", object_id],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if object_type != "blob":
            continue
        relative = historical_path or f"blob-{object_id}"
        text = _decode_text(_git_object(root, "blob", object_id))
        if text is None:
            continue
        text_count += 1
        findings = _scan_text(relative, text)
        if object_id in ACKNOWLEDGED_HISTORY_INTERNAL_MARKER_BLOBS:
            findings = [
                finding
                for finding in findings
                if "contains internal workspace marker" not in finding
            ]
        if object_id in ACKNOWLEDGED_HISTORY_HOST_FIXTURE_BLOBS:
            findings = [
                finding
                for finding in findings
                if "contains an absolute host path" not in finding
            ]
        errors.extend(f"history:blob:{object_id}:{finding}" for finding in findings)

    tags = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "for-each-ref",
            "--format=%(refname)%09%(objecttype)%09%(objectname)",
            "refs/tags",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for row in tags.stdout.splitlines():
        reference, object_type, object_id = row.split("\t")
        if object_type != "tag":
            continue
        raw_tag = _git_object(root, "tag", object_id)
        message = raw_tag.partition(b"\n\n")[2]
        text = _decode_text(message)
        if text is None:
            continue
        text_count += 1
        errors.extend(
            f"history:{reference}:{error}"
            for error in _scan_text("tag-message.txt", text)
        )
    return errors, text_count


def _reachable_revisions(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--all", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 128:
        fallback = subprocess.run(
            ["git", "-C", str(root), "rev-list", "--all"],
            check=True,
            capture_output=True,
            text=True,
        )
        return fallback.stdout.splitlines()
    completed.check_returncode()
    return completed.stdout.splitlines()


def _github_pull_request_merge_commit(root: Path) -> str | None:
    """Identify GitHub's ephemeral two-parent PR test merge, if present."""
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return None
    sha = os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        return None

    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "rev-list",
            "--parents",
            "-n",
            "1",
            sha,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    parts = completed.stdout.split()
    if (
        completed.returncode == 0
        and len(parts) == 3
        and parts[0].lower() == sha.lower()
    ):
        return sha.lower()
    return None


def _commit_identity_errors(
    rows: Iterable[str],
    *,
    ignored_commit: str | None = None,
) -> list[str]:
    errors: list[str] = []
    for row in rows:
        commit, author, committer, *_ = row.split("\t")
        if ignored_commit and commit.lower() == ignored_commit.lower():
            continue
        for role, email in (("author", author), ("committer", committer)):
            if email.casefold() != MAINTAINER_NOREPLY_EMAIL.casefold():
                errors.append(
                    f"history:{commit}: {role} email is not the maintainer noreply address"
                )
    return errors


def _commit_signature_errors(
    rows: Iterable[str],
    *,
    ignored_commit: str | None = None,
) -> list[str]:
    errors: list[str] = []
    for row in rows:
        parts = row.split("\t")
        if len(parts) < 4:
            continue
        commit, _, _, signature_status, *fingerprints = parts
        if ignored_commit and commit.lower() == ignored_commit.lower():
            continue
        if commit in ACKNOWLEDGED_UNSIGNED_COMMITS:
            continue
        fingerprint = fingerprints[0] if fingerprints else ""
        if signature_status != "G" or fingerprint != RELEASE_SIGNING_FINGERPRINT:
            errors.append(f"history:{commit}: commit does not have a valid signature")
    return errors


def scan_public_files(
    root: Path = ROOT, files: Iterable[Path] | None = None
) -> tuple[list[str], int]:
    selected = list(files) if files is not None else prospective_public_files(root)
    index, errors = _index_entries(root)
    text_count = 0
    for relative in selected:
        normalized = relative.as_posix()
        errors.extend(_scan_path(normalized))
        path = root / relative
        entry = index.get(relative)
        if entry is not None:
            mode, object_id = entry
            if mode == "160000":
                errors.append(f"{normalized}: Git submodules are not public-scannable")
                continue
            staged_data = _git_object(root, "blob", object_id)
        else:
            if not path.is_file():
                errors.append(f"{normalized}: prospective public file is missing")
                continue
            staged_data = path.read_bytes()

        text = _decode_text(staged_data)
        if text is None:
            pass
        else:
            text_count += 1
            errors.extend(_scan_text(normalized, text))

        # Also scan a divergent tracked worktree copy. The index remains the
        # commit-authoritative payload, but fail-closed local review should not
        # hide an unstaged leak waiting to be added.
        if entry is not None and path.is_file():
            worktree_data = path.read_bytes()
            if worktree_data != staged_data:
                worktree_text = _decode_text(worktree_data)
                if worktree_text is not None:
                    text_count += 1
                    errors.extend(_scan_text(normalized, worktree_text))
    return errors, text_count


def scan_archive(path: Path) -> tuple[list[str], int]:
    errors: list[str] = []
    text_count = 0
    if path.suffix == ".whl" or path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = (
                (info.filename, archive.read(info))
                for info in archive.infolist()
                if not info.is_dir()
            )
            for name, data in members:
                relative = _archive_relative_path(name)
                errors.extend(_scan_path(relative))
                text = _decode_text(data)
                if text is not None:
                    text_count += 1
                    errors.extend(_scan_text(relative, text))
    elif path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                relative = _archive_relative_path(member.name)
                errors.extend(_scan_path(relative))
                text = _decode_text(extracted.read())
                if text is not None:
                    text_count += 1
                    errors.extend(_scan_text(relative, text))
    else:
        errors.append(f"{path}: unsupported archive format")
    return errors, text_count


def scan_release_file(path: Path) -> tuple[list[str], int]:
    errors = _scan_path(path.name)
    text = _decode_text(path.read_bytes())
    if text is None:
        return errors, 0
    errors.extend(_scan_text(path.name, text))
    return errors, 1


def _archive_relative_path(name: str) -> str:
    parts = list(PurePosixPath(name).parts)
    if parts and (
        parts[0].lower().startswith("asal_m-") or parts[0].lower().startswith("asal-m-")
    ):
        parts = parts[1:]
    return PurePosixPath(*parts).as_posix()


def _scan_path(relative: str) -> list[str]:
    normalized = PurePosixPath(relative).as_posix().lstrip("./")
    parts = {part.lower() for part in PurePosixPath(normalized).parts}
    errors: list[str] = []
    if parts & FORBIDDEN_PATH_PARTS:
        errors.append(f"{normalized}: forbidden public path component")
    if any(
        normalized.lower().startswith(prefix.lower())
        for prefix in FORBIDDEN_PATH_PREFIXES
    ):
        errors.append(f"{normalized}: forbidden public path prefix")
    return errors


def _scan_text(relative: str, text: str) -> list[str]:
    errors: list[str] = []
    if _contains_internal_marker(text):
        errors.append(f"{relative}: contains internal workspace marker")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(f"{relative}: contains secret-like content")
    for email in EMAIL_PATTERN.findall(text):
        if not email.lower().endswith(ALLOWED_EMAIL_SUFFIXES):
            errors.append(f"{relative}: contains a non-public email address")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if "public-scan: host-pattern" in line:
            continue
        for pattern in HOST_PATTERNS:
            if pattern.search(line):
                errors.append(
                    f"{relative}:{line_number}: contains an absolute host path"
                )
    return errors


def _contains_internal_marker(
    text: str, marker_digests: frozenset[str] = INTERNAL_MARKER_DIGESTS
) -> bool:
    words = re.findall(r"[A-Za-z0-9_]+", text.casefold())
    for index in range(len(words) - 2):
        normalized = " ".join(words[index : index + 3])
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if digest in marker_digests:
            return True
    return False


def _decode_text(data: bytes) -> str | None:
    for bom, encoding in (
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
        (codecs.BOM_UTF8, "utf-8-sig"),
    ):
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    if len(data) >= 4:
        pairs = len(data) // 2
        even_nulls = data[0::2].count(0) / pairs
        odd_nulls = data[1::2].count(0) / pairs
        encoding = None
        if odd_nulls >= 0.3 and even_nulls <= 0.05:
            encoding = "utf-16-le"
        elif even_nulls >= 0.3 and odd_nulls <= 0.05:
            encoding = "utf-16-be"
        if encoding is not None:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                pass
    return None


def verify(
    root: Path = ROOT,
    archives: Iterable[Path] = (),
    release_files: Iterable[Path] = (),
) -> tuple[int, int, int]:
    files = prospective_public_files(root)
    errors = verify_commit_identity(root)
    history_errors, history_text_count = scan_history(root)
    errors.extend(history_errors)
    file_errors, text_count = scan_public_files(root, files)
    errors.extend(file_errors)
    text_count += history_text_count

    archive_count = 0
    for archive in archives:
        archive_errors, archive_text_count = scan_archive(archive)
        errors.extend(f"{archive.name}:{error}" for error in archive_errors)
        text_count += archive_text_count
        archive_count += 1

    for release_file in release_files:
        release_errors, release_text_count = scan_release_file(release_file)
        errors.extend(f"{release_file.name}:{error}" for error in release_errors)
        text_count += release_text_count

    if errors:
        raise AssertionError("\n".join(sorted(set(errors))))
    return len(files), text_count, archive_count


def _archive_arguments(values: Iterable[str]) -> list[Path]:
    archives: list[Path] = []
    for value in values:
        path = Path(value)
        if path.is_dir():
            archives.extend(sorted(path.glob("*.whl")))
            archives.extend(sorted(path.glob("*.tar.gz")))
        else:
            archives.append(path)
    return archives


def _release_file_arguments(values: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for value in values:
        path = Path(value)
        if path.is_dir():
            files.extend(sorted(path.glob("*.spdx.json")))
            for name in (
                "SHA256SUMS",
                "asal-m-release-signing.pub",
                "allowed_signers",
            ):
                candidate = path / name
                if candidate.is_file():
                    files.append(candidate)
        else:
            files.append(path)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan prospective public files, history, and optional archives."
    )
    parser.add_argument(
        "--archives",
        nargs="*",
        default=[],
        metavar="PATH",
        help="Wheel/sdist files or directories containing them.",
    )
    parser.add_argument(
        "--release-files",
        nargs="*",
        default=[],
        metavar="PATH",
        help="Plain release metadata files or directories containing them.",
    )
    args = parser.parse_args()
    archives = _archive_arguments(args.archives)
    release_files = _release_file_arguments(args.release_files)
    file_count, text_count, archive_count = verify(
        archives=archives,
        release_files=release_files,
    )
    print(
        "public repository: verified "
        f"({file_count} files, {text_count} text payloads, "
        f"{archive_count} archives)"
    )


if __name__ == "__main__":
    main()

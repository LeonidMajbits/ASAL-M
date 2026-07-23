#!/usr/bin/env python3
"""Verify repository history, prospective public files, and built archives."""

from __future__ import annotations

import argparse
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
HOST_FIXTURE_PATHS = {
    "examples/certification_benchmark/regenerate.py",
    "examples/public_demo/regenerate.py",
    "tests/test_analysis_commands.py",
    "tests/test_artifact_paths.py",
    "tests/test_public_output.py",
    "tests/test_public_repository.py",
    "tools/verify_public_docs.py",
    "tools/verify_public_evidence.py",
    "tools/verify_public_repository.py",
}
INTERNAL_MARKERS = (
    "Grok " + "Operator Lab",
    "Codex " + "Operator Lab",
    "PLUS " + "ONE LAB",
)
HOST_PATTERNS = (
    re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]"),
    re.compile(r"\\\\[^\\\s]+[\\/]"),
    re.compile(r"/(?:Users|home|tmp)/", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|sk)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)\b"
        r"\s*[:=]\s*['\"][A-Za-z0-9_./+=-]{16,}['\"]"
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


def verify_commit_identity(root: Path = ROOT) -> list[str]:
    """Require GitHub noreply commit and annotated-tag identity."""
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            "--all",
            "--format=%H%x09%ae%x09%ce",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    errors: list[str] = []
    for row in completed.stdout.splitlines():
        commit, author, committer = row.split("\t")
        for role, email in (("author", author), ("committer", committer)):
            if not email.lower().endswith("@users.noreply.github.com"):
                errors.append(
                    f"history:{commit}: {role} email is not a GitHub noreply address"
                )
    tags = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "for-each-ref",
            "--format=%(refname)%09%(taggeremail)",
            "refs/tags",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for row in tags.stdout.splitlines():
        reference, tagger_email = row.split("\t")
        email = tagger_email.strip().strip("<>")
        if email and not email.lower().endswith("@users.noreply.github.com"):
            errors.append(
                f"history:{reference}: tagger email is not a GitHub noreply address"
            )
    return errors


def scan_public_files(
    root: Path = ROOT, files: Iterable[Path] | None = None
) -> tuple[list[str], int]:
    selected = list(files) if files is not None else prospective_public_files(root)
    errors: list[str] = []
    text_count = 0
    for relative in selected:
        normalized = relative.as_posix()
        errors.extend(_scan_path(normalized))
        path = root / relative
        if not path.is_file():
            errors.append(f"{normalized}: prospective public file is missing")
            continue
        text = _decode_text(path.read_bytes())
        if text is None:
            continue
        text_count += 1
        errors.extend(_scan_text(normalized, text))
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
    for marker in INTERNAL_MARKERS:
        if marker.lower() in text.lower():
            errors.append(f"{relative}: contains internal workspace marker")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(f"{relative}: contains secret-like content")
    for email in EMAIL_PATTERN.findall(text):
        if not email.lower().endswith(ALLOWED_EMAIL_SUFFIXES):
            errors.append(f"{relative}: contains a non-public email address")
    if relative not in HOST_FIXTURE_PATHS:
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "public-scan: host-pattern" in line:
                continue
            for pattern in HOST_PATTERNS:
                if pattern.search(line):
                    errors.append(
                        f"{relative}:{line_number}: contains an absolute host path"
                    )
    return errors


def _decode_text(data: bytes) -> str | None:
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def verify(root: Path = ROOT, archives: Iterable[Path] = ()) -> tuple[int, int, int]:
    files = prospective_public_files(root)
    errors = verify_commit_identity(root)
    file_errors, text_count = scan_public_files(root, files)
    errors.extend(file_errors)

    archive_count = 0
    for archive in archives:
        archive_errors, archive_text_count = scan_archive(archive)
        errors.extend(f"{archive.name}:{error}" for error in archive_errors)
        text_count += archive_text_count
        archive_count += 1

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
    args = parser.parse_args()
    archives = _archive_arguments(args.archives)
    file_count, text_count, archive_count = verify(archives=archives)
    print(
        "public repository: verified "
        f"({file_count} files, {text_count} text payloads, "
        f"{archive_count} archives)"
    )


if __name__ == "__main__":
    main()

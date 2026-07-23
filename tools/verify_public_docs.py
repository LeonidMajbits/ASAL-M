#!/usr/bin/env python3
"""Verify the checked-in public documentation surface without network access."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = {
    Path("README.md"),
    Path("AUTHORS.md"),
    Path("CHANGELOG.md"),
    Path("CITATION.cff"),
    Path("CLAIM_BOUNDARY.md"),
    Path("CONTRIBUTING.md"),
    Path("SECURITY.md"),
    Path("docs/USER_GUIDE.md"),
    Path("docs/EXPERIMENTS.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/ADDING_A_SUBSTRATE.md"),
    Path("docs/REPRODUCIBILITY.md"),
    Path("docs/RELEASE_CHECKLIST.md"),
    Path("docs/PROTOCOL_REGISTRATION.md"),
    Path("examples/certification_benchmark/README.md"),
    Path("examples/public_demo/README.md"),
}

EXCLUDED_PREFIXES = (
    ".git/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    "build/",
    "dist/",
    "docs/assets/",
    "examples/public_demo/findings/",
    "runs/",
    "vendor/",
    "venv/",
)

LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
HOST_PATTERNS = (
    re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]"),
    re.compile(r"\\\\[^\\\s]+[\\/]"),
    re.compile(r"/(?:Users|home|tmp)/", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)


def _public_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        normalized = relative.as_posix()
        if any(normalized.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        files.append(relative)
    return sorted(files)


def _link_target(raw_target: str) -> tuple[str, str]:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    target = target.split("?", maxsplit=1)[0]
    path, separator, fragment = target.partition("#")
    return unquote(path), unquote(fragment if separator else "")


def _heading_slug(value: str) -> str:
    value = re.sub(r"[`*_~]", "", value).strip().lower()
    value = re.sub(r"[^\w\- ]", "", value)
    value = re.sub(r"\s+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def _headings(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {_heading_slug(match) for match in HEADING_PATTERN.findall(text)}


def _validate_links(relative: Path, text: str) -> list[str]:
    errors: list[str] = []
    source = ROOT / relative
    for raw_target in LINK_PATTERN.findall(text):
        if raw_target.startswith(("http://", "https://", "mailto:")):
            continue
        local_path, fragment = _link_target(raw_target)
        if not local_path and not fragment:
            continue
        target = source if not local_path else source.parent / local_path
        try:
            resolved = target.resolve()
            resolved.relative_to(ROOT)
        except (OSError, ValueError):
            errors.append(f"{relative}: link escapes repository: {raw_target}")
            continue
        if not resolved.exists():
            errors.append(f"{relative}: missing link target: {raw_target}")
            continue
        if fragment and resolved.suffix.lower() == ".md":
            if _heading_slug(fragment) not in _headings(resolved):
                errors.append(f"{relative}: missing heading: {raw_target}")
    return errors


def verify() -> tuple[int, int]:
    missing = sorted(path for path in REQUIRED_DOCS if not (ROOT / path).is_file())
    errors = [f"missing required public document: {path}" for path in missing]
    docs = _public_markdown_files()
    link_count = 0

    for relative in docs:
        text = (ROOT / relative).read_text(encoding="utf-8")
        link_count += len(LINK_PATTERN.findall(text))
        errors.extend(_validate_links(relative, text))
        for pattern in HOST_PATTERNS:
            if pattern.search(text):
                errors.append(f"{relative}: contains a host-path marker")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"{relative}: contains a secret-like marker")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for required_link in (
        "docs/USER_GUIDE.md",
        "docs/EXPERIMENTS.md",
        "docs/PROTOCOL_REGISTRATION.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
    ):
        if required_link not in readme:
            errors.append(f"README.md: missing public navigation link: {required_link}")

    if errors:
        raise AssertionError("\n".join(errors))
    return len(docs), link_count


def main() -> None:
    doc_count, link_count = verify()
    print(f"public docs: verified ({doc_count} files, {link_count} links)")


if __name__ == "__main__":
    main()

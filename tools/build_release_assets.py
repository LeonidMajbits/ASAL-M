#!/usr/bin/env python3
"""Create or verify SHA-256 checksums for wheel and source archives."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def release_archives(dist: Path) -> list[Path]:
    return sorted([*dist.glob("*.whl"), *dist.glob("*.tar.gz")])


def render_checksums(paths: list[Path]) -> str:
    if not paths:
        raise FileNotFoundError("No wheel or source archive found")
    return "".join(f"{sha256(path)}  {path.name}\n" for path in paths)


def verify_checksums(checksum_path: Path, dist: Path) -> list[str]:
    expected: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, separator, filename = line.partition("  ")
        if not separator or len(digest) != 64:
            return [f"Malformed checksum line: {line}"]
        expected[filename] = digest

    archives = release_archives(dist)
    actual_names = {path.name for path in archives}
    errors: list[str] = []
    if set(expected) != actual_names:
        errors.append("Checksum file names do not match release archives")
    for path in archives:
        if expected.get(path.name) != sha256(path):
            errors.append(f"Checksum mismatch: {path.name}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or verify ASAL-M release checksums."
    )
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify the existing SHA256SUMS instead of writing it.",
    )
    args = parser.parse_args()
    checksum_path = args.dist / "SHA256SUMS"

    if args.verify:
        errors = verify_checksums(checksum_path, args.dist)
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"release checksums: verified ({len(release_archives(args.dist))} files)")
        return

    checksum_path.write_text(
        render_checksums(release_archives(args.dist)),
        encoding="utf-8",
        newline="\n",
    )
    print(f"release_checksums={checksum_path}")


if __name__ == "__main__":
    main()

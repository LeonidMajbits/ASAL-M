#!/usr/bin/env python3
"""Create and verify path-safe SHA-256 commitments for audit inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
SCHEMA = "asal-m.protocol-commitment.v1"


def digest_file(path: Path) -> dict[str, str | int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            byte_count += len(block)
    return {
        "file_name": path.name,
        "sha256": digest.hexdigest(),
        "bytes": byte_count,
    }


def parse_inputs(values: Iterable[str]) -> dict[str, Path]:
    inputs: dict[str, Path] = {}
    for value in values:
        role, separator, raw_path = value.partition("=")
        if not separator or not ROLE_PATTERN.fullmatch(role):
            raise ValueError("Each input must use a lowercase role and path: role=path")
        if role in inputs:
            raise ValueError(f"Duplicate commitment role: {role}")
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(f"Commitment input not found: {path}")
        inputs[role] = path
    if not inputs:
        raise ValueError("At least one role=path input is required")
    return inputs


def create_commitment(inputs: dict[str, Path]) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "created_at": (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        ),
        "inputs": [
            {"role": role, **digest_file(path)} for role, path in sorted(inputs.items())
        ],
    }


def verify_commitment(
    commitment: dict[str, object], inputs: dict[str, Path]
) -> list[str]:
    errors: list[str] = []
    if commitment.get("schema") != SCHEMA:
        errors.append("unsupported commitment schema")
    records = commitment.get("inputs")
    if not isinstance(records, list):
        return errors + ["commitment inputs must be a list"]

    expected_by_role = {
        str(record.get("role")): record
        for record in records
        if isinstance(record, dict)
    }
    if set(expected_by_role) != set(inputs):
        errors.append("provided roles do not match committed roles")
        return errors

    for role, path in inputs.items():
        actual = digest_file(path)
        expected = expected_by_role[role]
        for field in ("file_name", "sha256", "bytes"):
            if actual[field] != expected.get(field):
                errors.append(f"{role}: {field} does not match commitment")
    return errors


def _write_new_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite an existing commitment: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or verify an ASAL-M protocol commitment."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create", help="Create a new, non-overwriting commitment."
    )
    create_parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="ROLE=PATH",
        help="Exact input bytes to commit, such as audit_protocol=protocol.yaml.",
    )
    create_parser.add_argument("--output", required=True, type=Path)

    verify_parser = subparsers.add_parser(
        "verify", help="Verify revealed inputs against a commitment."
    )
    verify_parser.add_argument("commitment", type=Path)
    verify_parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="ROLE=PATH",
    )

    args = parser.parse_args()
    inputs = parse_inputs(args.input)
    if args.command == "create":
        payload = create_commitment(inputs)
        _write_new_json(args.output, payload)
        print(f"protocol_commitment={args.output}")
        return

    payload = json.loads(args.commitment.read_text(encoding="utf-8"))
    errors = verify_commitment(payload, inputs)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"protocol commitment: verified ({len(inputs)} inputs)")


if __name__ == "__main__":
    main()

from __future__ import annotations

import re
from pathlib import Path

import yaml

from tools.build_release_assets import (
    render_checksums,
    verify_checksums,
)
from tools.protocol_commitment import (
    SCHEMA,
    create_commitment,
    parse_inputs,
    verify_commitment,
)


def test_protocol_commitment_round_trip_and_tamper_detection(
    tmp_path: Path,
) -> None:
    protocol = tmp_path / "audit_protocol.yaml"
    policy = tmp_path / "policy.yaml"
    protocol.write_text("audit_seeds: [101, 202]\n", encoding="utf-8")
    policy.write_text("name: example-v1\n", encoding="utf-8")
    inputs = parse_inputs(
        [
            f"audit_protocol={protocol}",
            f"policy={policy}",
        ]
    )

    commitment = create_commitment(inputs)

    assert commitment["schema"] == SCHEMA
    assert verify_commitment(commitment, inputs) == []
    assert str(tmp_path) not in str(commitment)

    protocol.write_text("audit_seeds: [303]\n", encoding="utf-8")
    errors = verify_commitment(commitment, inputs)
    assert any("sha256" in error for error in errors)


def test_release_checksum_round_trip_and_tamper_detection(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "asal_m-0.1.1-py3-none-any.whl"
    source = tmp_path / "asal_m-0.1.1.tar.gz"
    wheel.write_bytes(b"wheel")
    source.write_bytes(b"source")
    checksum_path = tmp_path / "SHA256SUMS"
    checksum_path.write_text(
        render_checksums([wheel, source]),
        encoding="utf-8",
    )

    assert verify_checksums(checksum_path, tmp_path) == []

    wheel.write_bytes(b"tampered")
    errors = verify_checksums(checksum_path, tmp_path)
    assert errors == ["Checksum mismatch: asal_m-0.1.1-py3-none-any.whl"]


def test_release_metadata_versions_align() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
    readme = Path("README.md").read_text(encoding="utf-8")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    assert match is not None
    version = match.group(1)
    assert version == "0.1.1"
    assert citation["version"] == version
    assert f"version `{version}`" in readme
    assert f"## {version}" in changelog

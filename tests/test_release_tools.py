from __future__ import annotations

import re
import json
from pathlib import Path

import yaml

from tools.build_release_assets import (
    render_checksums,
    verify_checksums,
)
from tools.build_sbom import render_spdx, verify_spdx
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


def test_release_checksums_include_spdx_sbom(tmp_path: Path) -> None:
    wheel = tmp_path / "asal_m-0.1.2-py3-none-any.whl"
    source = tmp_path / "asal_m-0.1.2.tar.gz"
    sbom = tmp_path / "asal_m-0.1.2.spdx.json"
    public_key = tmp_path / "asal-m-release-signing.pub"
    allowed_signers = tmp_path / "allowed_signers"
    wheel.write_bytes(b"wheel")
    source.write_bytes(b"source")
    sbom.write_text("{}\n", encoding="utf-8")
    public_key.write_text("ssh-ed25519 fixture\n", encoding="utf-8")
    allowed_signers.write_text(
        "asal-m-release ssh-ed25519 fixture\n",
        encoding="utf-8",
    )
    checksum_path = tmp_path / "SHA256SUMS"
    checksum_path.write_text(
        render_checksums([wheel, source, sbom, public_key, allowed_signers]),
        encoding="utf-8",
    )

    assert verify_checksums(checksum_path, tmp_path) == []


def test_spdx_sbom_is_deterministic_and_binds_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "asal_m-0.1.2-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    first = render_spdx(
        package_name="asal-m",
        package_version="0.1.2",
        dependency_versions={"PyYAML": "6.0.3", "numpy": "2.4.1"},
        subject=wheel,
        source_date_epoch=1_753_300_000,
    )
    second = render_spdx(
        package_name="asal-m",
        package_version="0.1.2",
        dependency_versions={"numpy": "2.4.1", "PyYAML": "6.0.3"},
        subject=wheel,
        source_date_epoch=1_753_300_000,
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    dependencies = {"PyYAML": "6.0.3", "numpy": "2.4.1"}
    assert (
        verify_spdx(
            first,
            wheel,
            package_name="asal-m",
            package_version="0.1.2",
            dependency_versions=dependencies,
        )
        == []
    )
    assert first["spdxVersion"] == "SPDX-2.3"
    assert len(first["packages"]) == 3

    wheel.write_bytes(b"tampered")
    assert verify_spdx(
        first,
        wheel,
        package_name="asal-m",
        package_version="0.1.2",
        dependency_versions=dependencies,
    ) == ["SBOM subject checksum does not match the wheel"]


def test_spdx_verifier_rejects_removed_dependencies_and_relationships(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "asal_m-0.1.2-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    payload = render_spdx(
        package_name="asal-m",
        package_version="0.1.2",
        dependency_versions={
            "numpy": "2.5.1",
            "Pillow": "12.3.0",
            "PyYAML": "6.0.3",
        },
        subject=wheel,
        source_date_epoch=1_753_300_000,
    )
    payload["packages"] = payload["packages"][:1]
    payload["relationships"] = []

    errors = verify_spdx(
        payload,
        wheel,
        package_name="asal-m",
        package_version="0.1.2",
        dependency_versions={
            "numpy": "2.5.1",
            "Pillow": "12.3.0",
            "PyYAML": "6.0.3",
        },
    )

    assert any("missing dependency package" in error for error in errors)
    assert any("missing DESCRIBES relationship" in error for error in errors)
    assert any("missing DEPENDS_ON relationship" in error for error in errors)


def test_spdx_verifier_rejects_dependency_and_graph_tampering(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "asal_m-0.1.2-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    dependencies = {"numpy": "2.5.1", "Pillow": "12.3.0", "PyYAML": "6.0.3"}
    payload = render_spdx(
        package_name="asal-m",
        package_version="0.1.2",
        dependency_versions=dependencies,
        subject=wheel,
        source_date_epoch=1_753_300_000,
    )
    numpy_package = next(
        package for package in payload["packages"] if package["name"] == "numpy"
    )
    numpy_package["versionInfo"] = "0.0.0"
    numpy_package["externalRefs"][0]["referenceLocator"] = "pkg:pypi/numpy@0.0.0"
    payload["relationships"].append(dict(payload["relationships"][0]))
    payload["relationships"].append(
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-UNKNOWN",
        }
    )

    errors = verify_spdx(
        payload,
        wheel,
        package_name="asal-m",
        package_version="0.1.2",
        dependency_versions=dependencies,
    )

    assert any("dependency version does not match" in error for error in errors)
    assert any("dependency purl does not match" in error for error in errors)
    assert any("duplicate relationship" in error for error in errors)
    assert any("unknown target" in error for error in errors)


def test_release_public_key_and_allowed_signers_match() -> None:
    public_key = Path("docs/keys/asal-m-release-signing.pub").read_text(
        encoding="utf-8"
    )
    allowed = Path("docs/keys/allowed_signers").read_text(encoding="utf-8")
    key_fields = public_key.split()

    assert key_fields[0] == "ssh-ed25519"
    assert len(key_fields[1]) >= 60
    assert "PRIVATE" not in public_key
    assert allowed.count(f"{key_fields[0]} {key_fields[1]}") == 2
    assert 'namespaces="git"' in allowed
    assert 'namespaces="file"' in allowed


def test_release_metadata_versions_align() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
    readme = Path("README.md").read_text(encoding="utf-8")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    assert match is not None
    version = match.group(1)
    assert version == "0.1.4"
    assert citation["version"] == version
    assert f"version `{version}`" in readme
    assert f"## {version}" in changelog

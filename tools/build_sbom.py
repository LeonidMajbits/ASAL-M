#!/usr/bin/env python3
"""Build a deterministic SPDX 2.3 SBOM for an installed ASAL-M wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

SPDX_VERSION = "SPDX-2.3"
DATA_LICENSE = "CC0-1.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def requirement_name(requirement: str) -> str | None:
    """Extract a distribution name without evaluating optional-extra markers."""
    if "extra ==" in requirement:
        return None
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    return match.group(1) if match else None


def normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def spdx_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9.-]+", "-", value).strip("-")
    return f"SPDXRef-Package-{safe}"


def render_spdx(
    *,
    package_name: str,
    package_version: str,
    dependency_versions: dict[str, str],
    subject: Path,
    source_date_epoch: int,
) -> dict[str, Any]:
    """Return deterministic SPDX JSON describing the wheel and runtime deps."""
    subject_digest = sha256(subject)
    main_id = spdx_id(f"{package_name}-{package_version}")
    packages: list[dict[str, Any]] = [
        {
            "SPDXID": main_id,
            "name": package_name,
            "versionInfo": package_version,
            "packageFileName": subject.name,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "Apache-2.0",
            "checksums": [
                {
                    "algorithm": "SHA256",
                    "checksumValue": subject_digest,
                }
            ],
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": (
                        f"pkg:pypi/{normalized_name(package_name)}@{package_version}"
                    ),
                }
            ],
        }
    ]
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": main_id,
        }
    ]

    for name, version in sorted(
        dependency_versions.items(), key=lambda item: normalized_name(item[0])
    ):
        dependency_id = spdx_id(f"{name}-{version}")
        packages.append(
            {
                "SPDXID": dependency_id,
                "name": name,
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": (
                            f"pkg:pypi/{normalized_name(name)}@{version}"
                        ),
                    }
                ],
            }
        )
        relationships.append(
            {
                "spdxElementId": main_id,
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": dependency_id,
            }
        )

    created = datetime.fromtimestamp(source_date_epoch, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    namespace_seed = json.dumps(
        {
            "package": package_name,
            "version": package_version,
            "subject": subject_digest,
            "dependencies": dependency_versions,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    namespace_digest = hashlib.sha256(namespace_seed).hexdigest()
    return {
        "spdxVersion": SPDX_VERSION,
        "dataLicense": DATA_LICENSE,
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{package_name}-{package_version}-release",
        "documentNamespace": (
            "https://github.com/LeonidMajbits/ASAL-M/sbom/"
            f"{package_version}/{namespace_digest}"
        ),
        "creationInfo": {
            "created": created,
            "creators": [f"Tool: {package_name}-build-sbom-{package_version}"],
        },
        "packages": packages,
        "relationships": relationships,
    }


def installed_release(
    package_name: str,
) -> tuple[str, str, dict[str, str]]:
    distribution = metadata.distribution(package_name)
    resolved: dict[str, str] = {}
    for requirement in distribution.requires or []:
        name = requirement_name(requirement)
        if name is None:
            continue
        resolved[name] = metadata.version(name)
    return distribution.metadata["Name"], distribution.version, resolved


def write_spdx(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_spdx(
    payload: dict[str, Any],
    subject: Path,
    *,
    package_name: str,
    package_version: str,
    dependency_versions: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    if payload.get("spdxVersion") != SPDX_VERSION:
        errors.append("SBOM does not declare SPDX 2.3")
    if payload.get("dataLicense") != DATA_LICENSE:
        errors.append("SBOM does not declare CC0-1.0 data license")
    if payload.get("SPDXID") != "SPDXRef-DOCUMENT":
        errors.append("SBOM document SPDXID is invalid")

    packages = payload.get("packages")
    if not isinstance(packages, list) or not packages:
        errors.append("SBOM has no packages")
        return errors

    package_by_id: dict[str, dict[str, Any]] = {}
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            errors.append(f"SBOM package at index {index} is not an object")
            continue
        package_id = package.get("SPDXID")
        if not isinstance(package_id, str) or not package_id:
            errors.append(f"SBOM package at index {index} has no SPDXID")
            continue
        if package_id in package_by_id:
            errors.append(f"SBOM has duplicate package SPDXID {package_id}")
            continue
        package_by_id[package_id] = package

    main_id = spdx_id(f"{package_name}-{package_version}")
    expected_dependencies = {
        spdx_id(f"{name}-{version}"): (name, version)
        for name, version in dependency_versions.items()
    }
    expected_package_ids = {main_id, *expected_dependencies}

    for dependency_id, (name, version) in sorted(expected_dependencies.items()):
        if dependency_id not in package_by_id:
            errors.append(f"SBOM is missing dependency package {name}=={version}")

    for extra_id in sorted(set(package_by_id) - expected_package_ids):
        errors.append(f"SBOM has unexpected package {extra_id}")

    described = package_by_id.get(main_id)
    if described is None:
        errors.append(
            f"SBOM is missing subject package {package_name}=={package_version}"
        )
    else:
        if normalized_name(str(described.get("name", ""))) != normalized_name(
            package_name
        ):
            errors.append("SBOM subject package name does not match")
        if described.get("versionInfo") != package_version:
            errors.append("SBOM subject package version does not match")
        checksums = described.get("checksums", [])
        expected_digest = sha256(subject)
        if not isinstance(checksums, list) or not any(
            item.get("algorithm") == "SHA256"
            and item.get("checksumValue") == expected_digest
            for item in checksums
            if isinstance(item, dict)
        ):
            errors.append("SBOM subject checksum does not match the wheel")
        if described.get("packageFileName") != subject.name:
            errors.append("SBOM subject filename does not match the wheel")

    for dependency_id, (name, version) in sorted(expected_dependencies.items()):
        package = package_by_id.get(dependency_id)
        if package is None:
            continue
        if normalized_name(str(package.get("name", ""))) != normalized_name(name):
            errors.append(f"SBOM dependency name does not match for {name}=={version}")
        if package.get("versionInfo") != version:
            errors.append(
                f"SBOM dependency version does not match for {name}=={version}"
            )
        expected_purl = f"pkg:pypi/{normalized_name(name)}@{version}"
        references = package.get("externalRefs", [])
        if not isinstance(references, list) or not any(
            reference.get("referenceCategory") == "PACKAGE-MANAGER"
            and reference.get("referenceType") == "purl"
            and reference.get("referenceLocator") == expected_purl
            for reference in references
            if isinstance(reference, dict)
        ):
            errors.append(f"SBOM dependency purl does not match for {name}=={version}")

    relationships = payload.get("relationships")
    relationship_set: set[tuple[str, str, str]] = set()
    if not isinstance(relationships, list):
        errors.append("SBOM relationships are missing or invalid")
        relationships = []
    valid_ids = {"SPDXRef-DOCUMENT", *package_by_id}
    for index, relationship in enumerate(relationships):
        if not isinstance(relationship, dict):
            errors.append(f"SBOM relationship at index {index} is not an object")
            continue
        item = (
            str(relationship.get("spdxElementId", "")),
            str(relationship.get("relationshipType", "")),
            str(relationship.get("relatedSpdxElement", "")),
        )
        if item in relationship_set:
            errors.append(f"SBOM has duplicate relationship {' '.join(item)}")
            continue
        relationship_set.add(item)
        if item[0] not in valid_ids or item[2] not in valid_ids:
            errors.append(f"SBOM relationship at index {index} has an unknown target")

    describes = ("SPDXRef-DOCUMENT", "DESCRIBES", main_id)
    if describes not in relationship_set:
        errors.append("SBOM is missing DESCRIBES relationship to the subject")
    expected_relationships = {describes}
    for dependency_id, (name, version) in sorted(expected_dependencies.items()):
        relationship = (main_id, "DEPENDS_ON", dependency_id)
        expected_relationships.add(relationship)
        if relationship not in relationship_set:
            errors.append(
                f"SBOM is missing DEPENDS_ON relationship for {name}=={version}"
            )
    for unexpected in sorted(relationship_set - expected_relationships):
        errors.append(f"SBOM has unexpected relationship {' '.join(unexpected)}")
    return errors


def _single_path(values: Iterable[str], label: str) -> Path:
    paths = [Path(value) for value in values]
    if len(paths) != 1:
        raise ValueError(f"{label} requires exactly one path")
    return paths[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or verify an SPDX 2.3 release SBOM."
    )
    parser.add_argument("--package", default="asal-m")
    parser.add_argument("--subject", nargs=1, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    subject = _single_path(args.subject, "--subject")

    if args.verify:
        payload = json.loads(args.output.read_text(encoding="utf-8"))
        name, version, dependencies = installed_release(args.package)
        errors = verify_spdx(
            payload,
            subject,
            package_name=name,
            package_version=version,
            dependency_versions=dependencies,
        )
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"release SBOM: verified ({len(payload['packages'])} packages)")
        return

    name, version, dependencies = installed_release(args.package)
    payload = render_spdx(
        package_name=name,
        package_version=version,
        dependency_versions=dependencies,
        subject=subject,
        source_date_epoch=args.source_date_epoch,
    )
    write_spdx(payload, args.output)
    print(f"release_sbom={args.output}")


if __name__ == "__main__":
    main()

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


def verify_spdx(payload: dict[str, Any], subject: Path) -> list[str]:
    errors: list[str] = []
    if payload.get("spdxVersion") != SPDX_VERSION:
        errors.append("SBOM does not declare SPDX 2.3")
    if payload.get("dataLicense") != DATA_LICENSE:
        errors.append("SBOM does not declare CC0-1.0 data license")
    packages = payload.get("packages")
    if not isinstance(packages, list) or not packages:
        errors.append("SBOM has no packages")
        return errors
    described = packages[0]
    checksums = described.get("checksums", [])
    expected = sha256(subject)
    if not any(
        item.get("algorithm") == "SHA256" and item.get("checksumValue") == expected
        for item in checksums
        if isinstance(item, dict)
    ):
        errors.append("SBOM subject checksum does not match the wheel")
    if described.get("packageFileName") != subject.name:
        errors.append("SBOM subject filename does not match the wheel")
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
        errors = verify_spdx(payload, subject)
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

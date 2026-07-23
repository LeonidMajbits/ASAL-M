#!/usr/bin/env python3
"""Integrity and semantic checks for checked-in public benchmark evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from asal_m.evidence import (  # noqa: E402
    PUBLIC_FLOAT_DECIMAL_PLACES,
    canonical_public_json,
)

BENCHMARK = ROOT / "examples" / "certification_benchmark" / "benchmark.json"
IMAGE = ROOT / "examples" / "certification_benchmark" / "certification-comparison.png"
PUBLIC_DEMO_BENCHMARK = ROOT / "examples" / "public_demo" / "benchmark.json"
PUBLIC_DEMO_IMAGE = ROOT / "examples" / "public_demo" / "mutation_cells_seed42.gif"
FONT_REGULAR = (
    ROOT / "examples" / "certification_benchmark" / "fonts" / "DejaVuSans.ttf"
)
FONT_BOLD = (
    ROOT / "examples" / "certification_benchmark" / "fonts" / "DejaVuSans-Bold.ttf"
)

FONT_SHA256 = {
    "DejaVuSans.ttf": "7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954",
    "DejaVuSans-Bold.ttf": "e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724",
}
ARTIFACT_SHA256 = {
    "certification-benchmark.json": (
        "c9f4c6a19e254140ffd7ec3edc8cc93a351b03ecbf801d6b59aaecd56a126e26"
    ),
    "certification-comparison.png": (
        "d9ace3de92e11a5381dbb06aae489048f525f67445c1ac80052b0affe1490434"
    ),
    "public-demo-benchmark.json": (
        "02fc23842d28cf28875f0fcde93fd447e7b1afe4a3cd2abcb4ceddd2dc6cd53c"
    ),
    "mutation_cells_seed42.gif": (
        "439588b196430cf2b8622def124010fbdb2449efa840db0bb61d97a2fd876e3b"
    ),
}


class EvidenceVerificationError(RuntimeError):
    """Raised when checked-in public evidence violates its release contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceVerificationError(message)


def _mean(values: list[float]) -> float:
    _require(bool(values), "Evidence lists must not be empty")
    return sum(values) / len(values)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_canonical_json(path: Path) -> tuple[str, dict[str, Any]]:
    _require(path.is_file(), f"Missing evidence file: {path.name}")
    data = path.read_bytes()
    _require(data.endswith(b"\n"), f"{path.name} must end with a newline")
    _require(b"\r" not in data, f"{path.name} must use canonical LF line endings")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceVerificationError(f"{path.name} must be valid UTF-8") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvidenceVerificationError(f"{path.name} must be valid JSON") from exc
    _require(
        canonical_public_json(payload) == text,
        f"{path.name} does not use canonical public JSON serialization",
    )
    return text, payload


def _verify_image(
    path: Path,
    *,
    expected_format: str,
    expected_size: tuple[int, int],
    expected_frames: int = 1,
) -> None:
    _require(path.is_file(), f"Missing evidence image: {path.name}")
    _require(
        path.stat().st_size > 10_000,
        f"Evidence image is unexpectedly small: {path.name}",
    )
    try:
        with Image.open(path) as image:
            actual_format = image.format
            actual_size = image.size
            actual_frames = getattr(image, "n_frames", 1)
            image.verify()
    except Exception as exc:
        raise EvidenceVerificationError(
            f"Unreadable evidence image: {path.name}"
        ) from exc
    _require(actual_format == expected_format, f"{path.name} must be {expected_format}")
    _require(actual_size == expected_size, f"{path.name} has unexpected dimensions")
    _require(
        actual_frames == expected_frames, f"{path.name} has unexpected frame count"
    )


def verify(payload: dict[str, Any]) -> None:
    """Verify the certification benchmark's semantic invariants."""

    protocol = payload["protocol"]
    audit_seeds = set(protocol["audit_seeds"])
    shortlist = payload["selection_shortlist"]
    selection_seeds = {
        int(row["candidate_seed"]) + int(offset)
        for row in shortlist
        for offset in protocol["selection_holdout_offsets"]
    }
    _require(
        audit_seeds.isdisjoint(selection_seeds), "Selection and audit seeds overlap"
    )
    _require(
        len(payload["discovery_pool"]) == int(protocol["pool_size"]),
        "Discovery pool size does not match the protocol",
    )
    _require(
        len(shortlist) == int(protocol["shortlist_size"]),
        "Selection shortlist size does not match the protocol",
    )

    reproduction = payload["reproduction"]
    _require(
        int(reproduction["float_decimal_places"]) == PUBLIC_FLOAT_DECIMAL_PLACES,
        "Certification float policy does not match the serializer",
    )
    _require(
        reproduction["constraints"] == "requirements-repro.txt",
        "Certification evidence must name the release constraints",
    )
    rendering = reproduction["rendering"]
    _require(
        rendering["font_regular_sha256"] == FONT_SHA256["DejaVuSans.ttf"],
        "Certification regular-font digest is incorrect",
    )
    _require(
        rendering["font_bold_sha256"] == FONT_SHA256["DejaVuSans-Bold.ttf"],
        "Certification bold-font digest is incorrect",
    )

    raw = payload["selected"]["single_rollout"]
    certified = payload["selected"]["certification"]
    _require(
        raw["candidate_index"] != certified["candidate_index"],
        "Raw and certification selections must be different candidates",
    )
    _require(
        raw["certification"]["status"] == "rejected",
        "The fixed raw selection must be rejected",
    )
    _require(
        certified["certification"]["status"] == "certified",
        "The fixed certification selection must be certified",
    )
    _require(
        float(raw["discovery_score"]) > float(certified["discovery_score"]),
        "The fixed raw selection must have the higher discovery score",
    )

    for label, selected in (("raw", raw), ("certification", certified)):
        audit = selected["final_audit"]
        trials = audit["trials"]
        _require(
            {trial["seed"] for trial in trials} == audit_seeds,
            f"{label} audit seeds do not match the frozen audit set",
        )
        computed = _mean([float(trial["audit_score"]) for trial in trials])
        _require(
            math.isclose(computed, float(audit["mean_score"]), abs_tol=1e-12),
            f"{label} audit mean is inconsistent with its trials",
        )
        passed = sum(bool(trial["passed"]) for trial in trials)
        _require(
            passed == int(audit["passed_trials"]),
            f"{label} passed-trial count is inconsistent",
        )
        _require(
            len(trials) == int(audit["total_trials"]),
            f"{label} total-trial count is inconsistent",
        )
        _require(
            math.isclose(
                passed / len(trials),
                float(audit["pass_rate"]),
                abs_tol=1e-12,
            ),
            f"{label} audit pass rate is inconsistent",
        )

    comparison = payload["comparison"]
    raw_mean = float(raw["final_audit"]["mean_score"])
    certified_mean = float(certified["final_audit"]["mean_score"])
    gain = certified_mean - raw_mean
    _require(
        math.isclose(gain, float(comparison["absolute_audit_gain"]), abs_tol=1e-12),
        "Claimed absolute audit gain is inconsistent",
    )
    _require(gain > 0.0, "Certification selection must improve the fixed final audit")
    _require(
        math.isclose(
            gain / raw_mean,
            float(comparison["relative_audit_gain"]),
            abs_tol=1e-12,
        ),
        "Claimed relative audit gain is inconsistent",
    )


def verify_public_demo(payload: dict[str, Any]) -> None:
    """Verify the fixed postcard's public reproduction contract."""

    _require(payload["schema_version"] == 2, "Unexpected postcard schema version")
    reproduction = payload["reproduction"]
    _require(
        int(reproduction["float_decimal_places"]) == PUBLIC_FLOAT_DECIMAL_PLACES,
        "Postcard float policy does not match the serializer",
    )
    _require(
        reproduction["constraints"] == "requirements-repro.txt",
        "Postcard evidence must name the release constraints",
    )
    hero = payload["hero"]
    _require(
        hero["gif"] == "examples/public_demo/mutation_cells_seed42.gif",
        "Postcard GIF path is not repository-relative and canonical",
    )
    _require(hero["seed"] == 42, "Unexpected postcard seed")
    _require(hero["grid_size"] == 96, "Unexpected postcard grid size")
    _require(hero["display_scale"] == 4, "Checked-in postcard must use scale 4")
    _require(
        hero["native_resolution"] == [96, 96], "Unexpected postcard native resolution"
    )
    _require(
        hero["display_resolution"] == [384, 384],
        "Unexpected postcard display resolution",
    )
    _require(
        hero["validation"]["deterministic_replay"] is True,
        "Postcard replay must be deterministic",
    )


def verify_paths(
    *,
    benchmark: Path = BENCHMARK,
    image: Path = IMAGE,
    public_demo_benchmark: Path = PUBLIC_DEMO_BENCHMARK,
    public_demo_image: Path = PUBLIC_DEMO_IMAGE,
    font_regular: Path = FONT_REGULAR,
    font_bold: Path = FONT_BOLD,
) -> None:
    texts_and_payloads = [
        _read_canonical_json(benchmark),
        _read_canonical_json(public_demo_benchmark),
    ]
    forbidden = (
        r"[A-Za-z]:[\\/]",
        r"\\\\[^\\\s]+[\\/]",
        r"/(?:Users|home|tmp)/",
    )
    _require(
        not any(
            re.search(pattern, text, flags=re.IGNORECASE)
            for text, _payload in texts_and_payloads
            for pattern in forbidden
        ),
        "Public evidence contains an absolute host path",
    )

    _require(font_regular.is_file(), "Missing bundled regular release font")
    _require(font_bold.is_file(), "Missing bundled bold release font")
    _require(
        _sha256(font_regular) == FONT_SHA256["DejaVuSans.ttf"],
        "Bundled regular release font checksum mismatch",
    )
    _require(
        _sha256(font_bold) == FONT_SHA256["DejaVuSans-Bold.ttf"],
        "Bundled bold release font checksum mismatch",
    )
    for path, label in (
        (benchmark, "certification-benchmark.json"),
        (image, "certification-comparison.png"),
        (public_demo_benchmark, "public-demo-benchmark.json"),
        (public_demo_image, "mutation_cells_seed42.gif"),
    ):
        _require(
            _sha256(path) == ARTIFACT_SHA256[label],
            f"Release artifact checksum mismatch: {label}",
        )

    _verify_image(
        image,
        expected_format="PNG",
        expected_size=(1280, 760),
    )
    _verify_image(
        public_demo_image,
        expected_format="GIF",
        expected_size=(384, 384),
        expected_frames=49,
    )
    verify(texts_and_payloads[0][1])
    verify_public_demo(texts_and_payloads[1][1])


def main() -> None:
    try:
        verify_paths()
    except EvidenceVerificationError as exc:
        raise SystemExit(f"public evidence: FAILED: {exc}") from exc
    print("public evidence: verified")


if __name__ == "__main__":
    main()

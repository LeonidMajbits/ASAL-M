#!/usr/bin/env python3
"""Regenerate the partition-disjoint ASAL-M certification benchmark.

The benchmark deliberately separates three evidence partitions:

1. one-seed discovery scores for a deterministic candidate pool;
2. certification evidence for the six highest discovery scores; and
3. a final audit on seeds and stronger perturbations never used for selection.

It writes only ``benchmark.json`` and ``certification-comparison.png`` beside
this script. Temporary validation artifacts are removed before exit.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import sys
import tempfile
import zlib
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from asal_m.core import CandidateConfig, SimulationRunner  # noqa: E402
from asal_m.evidence import (  # noqa: E402
    PUBLIC_FLOAT_DECIMAL_PLACES,
    canonical_public_json,
    canonicalize_public_payload,
)
from asal_m.search.proposals import sample_sections  # noqa: E402
from asal_m.substrates import create_substrate, get_search_space  # noqa: E402
from asal_m.validation import validate_candidate  # noqa: E402
from asal_m.validation.holdout_eval import compute_holdout_score  # noqa: E402
from asal_m.validation.perturb_suite import run_perturbation_suite  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent
BENCHMARK_JSON = OUTPUT_DIR / "benchmark.json"
COMPARISON_PNG = OUTPUT_DIR / "certification-comparison.png"
FONT_DIR = OUTPUT_DIR / "fonts"
FONT_FILES = {
    False: (
        FONT_DIR / "DejaVuSans.ttf",
        "7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954",
    ),
    True: (
        FONT_DIR / "DejaVuSans-Bold.ttf",
        "e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724",
    ),
}

POOL_SEED = 20_260_722
POOL_SIZE = 30
SHORTLIST_SIZE = 6
GRID_SIZE = 48
DISCOVERY_STEPS = 40
AUDIT_STEPS = 80
SELECTION_HOLDOUT_OFFSETS = [1001, 2003, 3001]
AUDIT_SEEDS = [
    900001,
    900101,
    900211,
    900307,
    900401,
    900503,
    900601,
    900701,
    900809,
    900907,
    901003,
    901103,
]
SELECTION_PERTURBATIONS = [
    {"kind": "radiation", "magnitude": 0.16},
    {"kind": "charge_drop", "factor": 0.40},
    {"kind": "wipe_patch", "size": 0.18},
]
AUDIT_PERTURBATIONS = [
    {"kind": "radiation", "magnitude": 0.20},
    {"kind": "charge_drop", "factor": 0.30},
    {"kind": "wipe_patch", "size": 0.22},
]
AUDIT_PASS_THRESHOLD = 0.75


def discovery_score(metrics: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Single-rollout interestingness proxy used only for the discovery partition."""

    components = {
        "activity": min(1.0, float(metrics.get("activity", 0.0)) / 0.25),
        "diversity": float(metrics.get("diversity", 0.0)),
        "lineage_entropy": float(metrics.get("lineage_entropy", 0.0)),
        "cluster_coherence": float(metrics.get("cluster_coherence", 0.0)),
        "occupancy": min(1.0, float(metrics.get("occupancy", 0.0)) / 0.50),
    }
    score = (
        0.25 * components["activity"]
        + 0.20 * components["diversity"]
        + 0.20 * components["lineage_entropy"]
        + 0.15 * components["cluster_coherence"]
        + 0.20 * components["occupancy"]
    )
    return float(np.clip(score, 0.0, 1.0)), components


def _candidate_pool() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = np.random.default_rng(POOL_SEED)
    search_space = deepcopy(get_search_space("mutation_cells"))
    search_space["environment"]["grid_size"] = {
        "type": "int",
        "min": GRID_SIZE,
        "max": GRID_SIZE,
    }
    runner = SimulationRunner("unused-benchmark-artifacts")
    rows: list[dict[str, Any]] = []
    for index in range(POOL_SIZE):
        sections = sample_sections(search_space, rng)
        candidate = CandidateConfig(
            substrate="mutation_cells",
            search_mode="certification_benchmark",
            seed=int(rng.integers(1, 2**31 - 1)),
            **sections,
        )
        run = runner.run_candidate(
            create_substrate(candidate.substrate),
            candidate,
            steps=DISCOVERY_STEPS,
            frame_stride=5,
            capture_state_every=10,
            save_artifacts=False,
        )
        score, components = discovery_score(run.summary_metrics)
        rows.append(
            {
                "candidate_index": index,
                "candidate": candidate,
                "discovery_score": score,
                "discovery_components": components,
                "summary_metrics": dict(run.summary_metrics),
                "final_frame": run.frames[-1],
            }
        )
    return rows, search_space


def _certify_shortlist(
    rows: list[dict[str, Any]],
    search_space: dict[str, Any],
    work: Path,
) -> list[dict[str, Any]]:
    shortlist = sorted(rows, key=lambda row: row["discovery_score"], reverse=True)[
        :SHORTLIST_SIZE
    ]
    for row in shortlist:
        report = validate_candidate(
            row["candidate"],
            steps=DISCOVERY_STEPS,
            frame_stride=5,
            capture_state_every=10,
            validation_config={
                "artifact_root": str(work / "selection"),
                "long_steps_multiplier": 2,
                "neighbor_samples": 4,
                "holdout_seed_offsets": SELECTION_HOLDOUT_OFFSETS,
                "perturbations": SELECTION_PERTURBATIONS,
            },
            search_space=search_space,
        )
        row["validation"] = report
    return shortlist


def _audit_candidate(candidate: CandidateConfig) -> dict[str, Any]:
    long_score, long_details = compute_holdout_score(
        candidate,
        steps=AUDIT_STEPS,
        holdout_seeds=AUDIT_SEEDS,
    )
    trials: list[dict[str, Any]] = []
    for long_detail in long_details:
        seed = int(long_detail["seed"])
        stress_score, stress_details = run_perturbation_suite(
            replace(candidate, seed=seed),
            steps=AUDIT_STEPS,
            perturbations=AUDIT_PERTURBATIONS,
        )
        audit_score = 0.55 * float(long_detail["score"]) + 0.45 * float(stress_score)
        trials.append(
            {
                "seed": seed,
                "long_horizon_score": float(long_detail["score"]),
                "strong_perturbation_score": float(stress_score),
                "audit_score": float(audit_score),
                "passed": bool(audit_score >= AUDIT_PASS_THRESHOLD),
                "perturbations": stress_details,
            }
        )

    values = np.asarray([trial["audit_score"] for trial in trials], dtype=float)
    stress_values = np.asarray(
        [trial["strong_perturbation_score"] for trial in trials],
        dtype=float,
    )
    return {
        "mean_score": float(values.mean()),
        "min_score": float(values.min()),
        "max_score": float(values.max()),
        "long_horizon_mean": float(long_score),
        "strong_perturbation_mean": float(stress_values.mean()),
        "pass_threshold": AUDIT_PASS_THRESHOLD,
        "passed_trials": int((values >= AUDIT_PASS_THRESHOLD).sum()),
        "total_trials": int(values.size),
        "pass_rate": float((values >= AUDIT_PASS_THRESHOLD).mean()),
        "trials": trials,
    }


def _public_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_index": int(row["candidate_index"]),
        "candidate_seed": int(row["candidate"].seed),
        "discovery_score": float(row["discovery_score"]),
        "discovery_components": dict(row["discovery_components"]),
        "summary_metrics": {
            key: float(value) for key, value in row["summary_metrics"].items()
        },
    }


def _public_selection_row(row: dict[str, Any]) -> dict[str, Any]:
    report = row["validation"]
    return {
        **_public_candidate_row(row),
        "certification_score": float(report.promotion_score()),
        "certification": report.certification,
        "validation_scores": {
            "long_horizon": float(report.long_horizon_score),
            "perturbation": float(report.perturbation_score),
            "neighborhood": float(report.neighborhood_score),
            "holdout": float(report.holdout_score),
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _font(size: int, *, bold: bool = False):
    path, expected_sha256 = FONT_FILES[bold]
    if not path.is_file():
        raise RuntimeError(f"Required release font is missing: {path.name}")
    actual_sha256 = _sha256(path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"Release font checksum mismatch for {path.name}: {actual_sha256}"
        )
    return ImageFont.truetype(
        str(path),
        size=size,
        layout_engine=ImageFont.Layout.BASIC,
    )


def _draw_bar(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    width: int,
    value: float,
    color: tuple[int, int, int],
) -> None:
    draw.rounded_rectangle((x, y, x + width, y + 22), radius=8, fill=(40, 49, 60))
    draw.rounded_rectangle(
        (x, y, x + max(2, int(width * np.clip(value, 0.0, 1.0))), y + 22),
        radius=8,
        fill=color,
    )


def _render_comparison(
    raw_row: dict[str, Any],
    certified_row: dict[str, Any],
    raw_audit: dict[str, Any],
    certified_audit: dict[str, Any],
) -> None:
    canvas = Image.new("RGB", (1280, 760), (15, 19, 24))
    draw = ImageDraw.Draw(canvas)
    title_font = _font(34, bold=True)
    subtitle_font = _font(20)
    heading_font = _font(23, bold=True)
    body_font = _font(18)
    small_font = _font(15)
    green = (70, 205, 145)
    red = (232, 101, 105)
    blue = (92, 168, 255)
    text = (232, 237, 242)
    muted = (160, 171, 182)

    draw.text(
        (44, 28),
        "Discovery score vs held-out certification",
        font=title_font,
        fill=text,
    )
    draw.text(
        (44, 76),
        "Same seeded pool. Selection holdouts and final audit seeds are disjoint.",
        font=subtitle_font,
        fill=muted,
    )

    panels = [
        (44, raw_row, raw_audit, "Single-rollout winner", red),
        (664, certified_row, certified_audit, "Certification-selected", green),
    ]
    for x, row, audit, label, accent in panels:
        draw.rounded_rectangle((x, 120, x + 572, 430), radius=18, fill=(25, 31, 38))
        draw.text((x + 22, 142), label, font=heading_font, fill=accent)
        frame = Image.fromarray(row["final_frame"]).resize(
            (220, 220), Image.Resampling.NEAREST
        )
        canvas.paste(frame, (x + 22, 190))
        report = row["validation"]
        decision = report.certification
        draw.text(
            (x + 268, 194),
            decision["status"].upper(),
            font=heading_font,
            fill=accent,
        )
        metrics = [
            ("Discovery", row["discovery_score"]),
            ("Certification", report.promotion_score()),
            ("Unseen audit", audit["mean_score"]),
            ("Strong stress", audit["strong_perturbation_mean"]),
        ]
        for offset, (name, value) in enumerate(metrics):
            yy = 238 + offset * 39
            draw.text((x + 268, yy), f"{name}: {value:.3f}", font=body_font, fill=text)
        failures = decision["failure_codes"]
        outcome = (
            f"audit passes: {audit['passed_trials']}/{audit['total_trials']}"
            if not failures
            else f"gate: {failures[0].replace('_', ' ')}"
        )
        draw.text((x + 268, 398), outcome, font=small_font, fill=muted)

    labels = ["Discovery", "Certification", "Unseen audit", "Strong stress"]
    raw_values = [
        raw_row["discovery_score"],
        raw_row["validation"].promotion_score(),
        raw_audit["mean_score"],
        raw_audit["strong_perturbation_mean"],
    ]
    certified_values = [
        certified_row["discovery_score"],
        certified_row["validation"].promotion_score(),
        certified_audit["mean_score"],
        certified_audit["strong_perturbation_mean"],
    ]
    draw.text(
        (44, 466), "Score inversion under unseen evidence", font=heading_font, fill=text
    )
    for index, label in enumerate(labels):
        yy = 520 + index * 50
        draw.text((44, yy), label, font=body_font, fill=text)
        _draw_bar(draw, x=205, y=yy, width=390, value=raw_values[index], color=red)
        draw.text((605, yy), f"{raw_values[index]:.3f}", font=small_font, fill=red)
        _draw_bar(
            draw, x=705, y=yy, width=390, value=certified_values[index], color=green
        )
        draw.text(
            (1105, yy), f"{certified_values[index]:.3f}", font=small_font, fill=green
        )

    draw.text((205, 718), "raw selection", font=small_font, fill=red)
    draw.text((705, 718), "certification selection", font=small_font, fill=green)
    draw.line((44, 704, 1236, 704), fill=(52, 61, 72), width=1)
    draw.text((1120, 718), "ASAL-M", font=small_font, fill=blue)
    _write_deterministic_png(canvas, COMPARISON_PNG)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _write_deterministic_png(image: Image.Image, path: Path) -> None:
    """Write an RGB PNG without platform-sensitive Pillow encoder choices."""

    rgb = image.convert("RGB")
    scanlines = b"".join(
        b"\x00" + rgb.crop((0, y, rgb.width, y + 1)).tobytes()
        for y in range(rgb.height)
    )
    header = struct.pack(
        ">IIBBBBB",
        rgb.width,
        rgb.height,
        8,
        2,
        0,
        0,
        0,
    )
    compressor = zlib.compressobj(
        level=9,
        method=zlib.DEFLATED,
        wbits=zlib.MAX_WBITS,
        memLevel=8,
        strategy=zlib.Z_HUFFMAN_ONLY,
    )
    compressed = compressor.compress(scanlines) + compressor.flush(zlib.Z_FINISH)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def _assert_no_host_paths(text: str) -> None:
    normalized = text.replace("\\\\", "\\")
    patterns = (
        r"[A-Za-z]:[\\/]",
        r"\\\\[^\\\s]+[\\/]",  # public-scan: host-pattern
        r"/(?:Users|home|tmp)/",
    )
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
        raise RuntimeError("Host absolute path leaked into benchmark output")


def regenerate() -> dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="asal_m_certification_benchmark_"))
    try:
        rows, search_space = _candidate_pool()
        shortlist = _certify_shortlist(rows, search_space, work)
        raw_row = shortlist[0]
        certified = [
            row for row in shortlist if row["validation"].certification["passed"]
        ]
        if not certified:
            raise RuntimeError("Seeded benchmark produced no certified candidate")
        certified_row = max(
            certified, key=lambda row: row["validation"].promotion_score()
        )

        selection_seed_sets = {
            row["candidate"].seed + offset
            for row in shortlist
            for offset in SELECTION_HOLDOUT_OFFSETS
        }
        if selection_seed_sets.intersection(AUDIT_SEEDS):
            raise RuntimeError("Selection and final-audit seeds must be disjoint")

        raw_audit = _audit_candidate(raw_row["candidate"])
        certified_audit = _audit_candidate(certified_row["candidate"])
        absolute_gain = certified_audit["mean_score"] - raw_audit["mean_score"]

        payload = {
            "title": "ASAL-M partition-disjoint certification benchmark",
            "schema_version": 1,
            "claim": (
                "On this fixed candidate pool, hard-gated certification selected a regime "
                "that transferred better than the highest single-rollout discovery score."
            ),
            "reproduction": {
                "command": "python examples/certification_benchmark/regenerate.py",
                "selection_and_audit_are_disjoint": True,
                "constraints": "requirements-repro.txt",
                "float_decimal_places": PUBLIC_FLOAT_DECIMAL_PLACES,
                "rendering": {
                    "font_regular": "examples/certification_benchmark/fonts/DejaVuSans.ttf",
                    "font_regular_sha256": FONT_FILES[False][1],
                    "font_bold": "examples/certification_benchmark/fonts/DejaVuSans-Bold.ttf",
                    "font_bold_sha256": FONT_FILES[True][1],
                    "font_version": "DejaVu Sans 2.37",
                    "layout_engine": "Pillow BASIC",
                    "png_scanline_filter": 0,
                    "png_compression_strategy": "zlib Z_HUFFMAN_ONLY",
                },
            },
            "protocol": {
                "substrate": "mutation_cells",
                "pool_seed": POOL_SEED,
                "pool_size": POOL_SIZE,
                "shortlist_size": SHORTLIST_SIZE,
                "grid_size": GRID_SIZE,
                "discovery_steps": DISCOVERY_STEPS,
                "selection_holdout_offsets": SELECTION_HOLDOUT_OFFSETS,
                "selection_perturbations": SELECTION_PERTURBATIONS,
                "audit_steps": AUDIT_STEPS,
                "audit_seeds": AUDIT_SEEDS,
                "audit_perturbations": AUDIT_PERTURBATIONS,
                "audit_score": "0.55 * unseen_long_horizon + 0.45 * strong_perturbation",
                "audit_pass_threshold": AUDIT_PASS_THRESHOLD,
            },
            "discovery_pool": [_public_candidate_row(row) for row in rows],
            "selection_shortlist": [_public_selection_row(row) for row in shortlist],
            "selected": {
                "single_rollout": {
                    **_public_selection_row(raw_row),
                    "candidate": raw_row["candidate"].to_dict(),
                    "final_audit": raw_audit,
                },
                "certification": {
                    **_public_selection_row(certified_row),
                    "candidate": certified_row["candidate"].to_dict(),
                    "final_audit": certified_audit,
                },
            },
            "comparison": {
                "absolute_audit_gain": float(absolute_gain),
                "relative_audit_gain": float(absolute_gain / raw_audit["mean_score"]),
                "single_rollout_audit_pass_rate": float(raw_audit["pass_rate"]),
                "certification_audit_pass_rate": float(certified_audit["pass_rate"]),
            },
        }

        text = canonical_public_json(payload)
        _assert_no_host_paths(text)
        BENCHMARK_JSON.write_text(text, encoding="utf-8", newline="\n")
        _render_comparison(raw_row, certified_row, raw_audit, certified_audit)
        return canonicalize_public_payload(payload)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    os.chdir(REPO_ROOT)
    payload = regenerate()
    comparison = payload["comparison"]
    print(f"wrote {BENCHMARK_JSON.relative_to(REPO_ROOT).as_posix()}")
    print(f"wrote {COMPARISON_PNG.relative_to(REPO_ROOT).as_posix()}")
    print(
        "unseen_audit "
        f"raw={payload['selected']['single_rollout']['final_audit']['mean_score']:.3f} "
        f"certified={payload['selected']['certification']['final_audit']['mean_score']:.3f} "
        f"absolute_gain={comparison['absolute_audit_gain']:.3f}"
    )


if __name__ == "__main__":
    main()

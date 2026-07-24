#!/usr/bin/env python3
"""Regenerate the public postcard assets (hero GIF + benchmark.json).

Usage (from repo root):

    python examples/public_demo/regenerate.py

Only two public artifacts are written into this directory:
  - mutation_cells_seed42.gif
  - benchmark.json

Intermediate rollouts and search runs are written under a temporary directory
and deleted. Absolute host paths are never embedded in the postcard JSON.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from asal_m.core import CandidateConfig, SimulationRunner  # noqa: E402
from asal_m.evidence import (  # noqa: E402
    PUBLIC_FLOAT_DECIMAL_PLACES,
    canonical_public_json,
    canonicalize_public_payload,
)
from asal_m.search import run_search_experiment  # noqa: E402
from asal_m.substrates import create_substrate, get_search_space  # noqa: E402
from asal_m.validation import validate_candidate  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent
HERO_GIF = DEMO_DIR / "mutation_cells_seed42.gif"
BENCHMARK_JSON = DEMO_DIR / "benchmark.json"

# Presentation scale for the public postcard (native sim is 96x96 cells → 384x384 display).
DISPLAY_SCALE = 4
GRID_SIZE = 96
SEED = 42
STEPS = 96


def _demo_candidate() -> CandidateConfig:
    return CandidateConfig(
        substrate="mutation_cells",
        search_mode="frontier",
        seed=SEED,
        params={
            "background_mortality": 0.012,
            "background_mutation": 0.01,
            "charge_decay": 0.07,
            "charge_gain": 0.27,
            "crowding_cost": 0.13,
            "lineage_budget_strength": 0.9,
            "lineage_split_threshold": 0.18,
            "mutability_drift": 0.08,
            "offspring_charge": 0.2,
            "reproduction_cost": 0.1,
        },
        rule_variants={
            "birth_max": 6,
            "birth_min": 2,
            "budget_mode": "dynamic",
            "survival_max": 6,
            "survival_min": 1,
        },
        environment={"grid_size": GRID_SIZE},
        initial_conditions={
            "base_mutability": 0.12,
            "density": 0.16,
            "initial_charge_max": 0.45,
            "initial_charge_min": 0.15,
            "initialization_strategy": "stratified",
            "seed_lineages": 8,
        },
    )


def _upscaled_gif(frames: list[np.ndarray], path: Path, scale: int) -> None:
    if not frames:
        raise RuntimeError("No frames produced for hero GIF")
    pil_frames = []
    for frame in frames:
        image = Image.fromarray(frame)
        if scale > 1:
            image = image.resize(
                (image.width * scale, image.height * scale), Image.Resampling.NEAREST
            )
        pil_frames.append(image)
    # GIF comment is invisible in GitHub previews; readable with tools that show metadata.
    comment = b"ASAL-M postcard | interesting is cheap; promotion is expensive"
    pil_frames[0].save(
        path,
        save_all=True,
        append_images=pil_frames[1:],
        optimize=False,
        duration=90,
        loop=0,
        comment=comment,
    )


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def _assert_no_host_paths(text: str) -> None:
    normalized = text.replace("\\\\", "\\")
    patterns = (
        r"[A-Za-z]:[\\/]",
        r"(?<![\\])\\\\[A-Za-z0-9._-]+[\\/]",
        r"(?<![A-Za-z0-9:/])/(?:Users|home|tmp|root|workspace|opt)/",
    )
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
        raise RuntimeError(
            "Host absolute paths leaked into benchmark.json; aborting write"
        )


def regenerate(*, display_scale: int = DISPLAY_SCALE) -> dict:
    candidate = _demo_candidate()
    work = Path(tempfile.mkdtemp(prefix="asal_m_public_demo_"))
    try:
        runner = SimulationRunner(work / "rollout")
        run = runner.run_candidate(
            create_substrate(candidate.substrate),
            candidate,
            steps=STEPS,
            frame_stride=2,
            capture_state_every=8,
            save_artifacts=False,
        )
        _upscaled_gif(run.frames, HERO_GIF, scale=display_scale)

        validation = validate_candidate(
            candidate,
            steps=64,
            frame_stride=4,
            capture_state_every=8,
            validation_config={
                "artifact_root": str(work / "validation"),
                "long_steps_multiplier": 2,
                "neighbor_samples": 3,
                "perturbations": [
                    {"kind": "radiation", "magnitude": 0.12},
                    {"kind": "wipe_patch", "size": 0.15},
                ],
                "holdout_seed_offsets": [101, 202, 303],
            },
            search_space=get_search_space(candidate.substrate),
        )

        experiment = {
            "name": "alpha_mainline_public_postcard",
            "seed": 7,
            "substrate": "alpha_alife",
            "search_mode": "frontier",
            "budget": 6,
            "steps": 32,
            "frame_stride": 4,
            "capture_state_every": 8,
            "artifact_root": str(work / "search"),
            "target_metrics": {
                "occupancy": 0.18,
                "diversity": 0.2,
                "cluster_coherence": 0.45,
            },
            "prefilter": {"min_steps": 8, "min_activity": 0.0, "min_occupancy": 0.0},
            "validation": {
                "interval": 100,
                "long_steps_multiplier": 2,
                "neighbor_samples": 2,
                "perturbations": [{"kind": "wipe_patch", "size": 0.15}],
            },
        }
        summary = run_search_experiment(experiment)

        winners = {}
        for name, winner in summary["winners"].items():
            if winner is None:
                winners[name] = None
                continue
            winners[name] = {
                "total_score": float(winner["total_score"]),
                "candidate_seed": int(winner["candidate"]["seed"]),
                "summary_metrics": {
                    key: float(value)
                    for key, value in winner["summary_metrics"].items()
                },
            }

        payload = {
            "title": "ASAL-M public simulation postcard (fixed seeds)",
            "schema_version": 2,
            "reproduction": {
                "command": "python examples/public_demo/regenerate.py",
                "from_repo_root": True,
                "constraints": "requirements-repro.txt",
                "float_decimal_places": PUBLIC_FLOAT_DECIMAL_PLACES,
                "notes": (
                    "Regenerates only mutation_cells_seed42.gif and benchmark.json. "
                    "Scientific calculations use full precision; published JSON floats "
                    "are normalized only at serialization."
                ),
            },
            "hero": {
                "gif": _rel(HERO_GIF),
                "substrate": "mutation_cells",
                "seed": SEED,
                "grid_size": GRID_SIZE,
                "steps": STEPS,
                "display_scale": display_scale,
                "native_resolution": [GRID_SIZE, GRID_SIZE],
                "display_resolution": [
                    GRID_SIZE * display_scale,
                    GRID_SIZE * display_scale,
                ],
                "summary_metrics": {
                    key: float(value) for key, value in run.summary_metrics.items()
                },
                "validation": {
                    "deterministic_replay": bool(validation.deterministic_replay),
                    "replay_difference": float(validation.replay_difference),
                    "long_horizon_score": float(validation.long_horizon_score),
                    "perturbation_score": float(validation.perturbation_score),
                    "neighborhood_score": float(validation.neighborhood_score),
                    "holdout_score": float(validation.holdout_score),
                    "promotion_score": float(validation.promotion_score()),
                    "certification": validation.certification,
                    "notes": list(validation.notes),
                },
            },
            "alpha_search_smoke": {
                "name": experiment["name"],
                "seed": experiment["seed"],
                "budget": experiment["budget"],
                "steps": experiment["steps"],
                "counts": summary["counts"],
                "winners": winners,
            },
        }

        text = canonical_public_json(payload)
        _assert_no_host_paths(text)
        BENCHMARK_JSON.write_text(text, encoding="utf-8", newline="\n")
        return canonicalize_public_payload(payload)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate ASAL-M public postcard assets."
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=DISPLAY_SCALE,
        help="Nearest-neighbor upscale factor for the hero GIF.",
    )
    args = parser.parse_args()
    if args.scale < 1:
        raise SystemExit("--scale must be >= 1")

    # Always run relative to repo root so any residual paths are repo-relative.
    import os

    os.chdir(REPO_ROOT)
    payload = regenerate(display_scale=args.scale)
    print(f"wrote {_rel(HERO_GIF)}")
    print(f"wrote {_rel(BENCHMARK_JSON)}")
    print(
        "hero_validation "
        f"holdout={payload['hero']['validation']['holdout_score']:.3f} "
        f"promotion={payload['hero']['validation']['promotion_score']:.3f} "
        f"display={payload['hero']['display_resolution']}"
    )


if __name__ == "__main__":
    main()

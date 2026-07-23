from __future__ import annotations

import argparse
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from .search import run_search_experiment
from .substrates import list_substrates


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ASAL-M experiments.")
    parser.add_argument(
        "--experiment",
        type=str,
        default=None,
        help="Experiment YAML path or packaged starter name (for example: alpha_mainline).",
    )
    parser.add_argument(
        "--budget", type=int, default=None, help="Optional override for search budget."
    )
    parser.add_argument(
        "--steps", type=int, default=None, help="Optional override for rollout steps."
    )
    args = parser.parse_args()

    if not args.experiment:
        parser.error("the following arguments are required: --experiment")

    experiment = _load_experiment(args.experiment)

    if args.budget is not None:
        experiment["budget"] = args.budget
    if args.steps is not None:
        experiment["steps"] = args.steps

    if experiment["substrate"] not in list_substrates():
        raise ValueError(
            f"Unknown substrate {experiment['substrate']}. Available: {', '.join(list_substrates())}"
        )

    summary = run_search_experiment(experiment)
    print(summary["counts"])
    for name, winner in summary["winners"].items():
        if winner is None:
            print(f"{name}: none")
            continue
        certification = (winner.get("validation") or {}).get("certification") or {}
        status = certification.get("status", "not-evaluated")
        print(
            f"{name}: total={winner['total_score']:.3f} "
            f"certification={status} "
            f"artifact_dir={winner['artifact_dir']}"
        )


def _load_experiment(spec: str) -> dict[str, Any]:
    path = Path(spec)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        source = str(path)
    elif path.name == spec:
        filename = spec if spec.endswith(".yaml") else f"{spec}.yaml"
        resource = files("asal_m.experiments").joinpath(filename)
        if not resource.is_file():
            raise FileNotFoundError(
                f"Experiment not found as a path or packaged starter: {spec}"
            )
        text = resource.read_text(encoding="utf-8")
        source = f"packaged:{filename}"
    else:
        raise FileNotFoundError(f"Experiment path not found: {spec}")

    experiment = yaml.safe_load(text)
    if not isinstance(experiment, dict):
        raise ValueError(f"Experiment must be a YAML mapping: {source}")
    return experiment


if __name__ == "__main__":
    main()

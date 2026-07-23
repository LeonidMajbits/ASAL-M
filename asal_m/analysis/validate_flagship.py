from __future__ import annotations

import argparse
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from ..core import CandidateConfig, SimulationRunner
from ..core.limits import positive_int_argument, require_positive_int
from ..public_output import to_public_data, utc_timestamp
from ..scoring import compute_mechanism_score
from ..substrates import create_substrate, get_search_space
from ..validation import validate_candidate
from ..validation.holdout_eval import compute_trajectory_quality_score

DEFAULT_SPEC_NAME = "flagship_template_example.yaml"
DEFAULT_SPEC_LABEL = f"packaged:{DEFAULT_SPEC_NAME}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a long-form validation and export pass for a frozen ASAL-M flagship."
    )
    parser.add_argument(
        "spec",
        nargs="?",
        default=None,
        help=f"Path to a flagship YAML spec. Defaults to {DEFAULT_SPEC_LABEL}.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional override for the report and artifact directory.",
    )
    parser.add_argument(
        "--export-steps",
        type=positive_int_argument,
        default=None,
        help="Optional override for the saved replay rollout length.",
    )
    parser.add_argument(
        "--validation-steps",
        type=positive_int_argument,
        default=None,
        help="Optional override for the validation base rollout length.",
    )
    args = parser.parse_args()

    payload, paths = generate_flagship_report(
        Path(args.spec) if args.spec else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        export_steps=args.export_steps,
        validation_steps=args.validation_steps,
    )

    print(f"flagship_json={paths['json']}")
    print(f"flagship_md={paths['md']}")
    print(f"export_artifact={payload['export']['artifact_dir']}")
    print(
        "promotion_score="
        f"{payload['validation']['promotion_score']:.3f} "
        f"holdout={payload['validation']['holdout_score']:.3f}"
    )


def generate_flagship_report(
    spec_path: Path | None = None,
    output_dir: Path | None = None,
    export_steps: int | None = None,
    validation_steps: int | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    spec, spec_label = _load_spec(spec_path)
    candidate = CandidateConfig(**spec["candidate"])

    export_cfg = dict(spec.get("export", {}))
    validation_cfg = dict(spec.get("validation", {}))
    resolved_output_dir = Path(
        output_dir or export_cfg.get("output_dir") or f"runs/flagships/{spec['name']}"
    )

    resolved_export_steps = require_positive_int(
        export_steps if export_steps is not None else export_cfg.get("steps", 192),
        "export_steps",
    )
    export_frame_stride = int(export_cfg.get("frame_stride", 4))
    export_capture_state_every = int(export_cfg.get("capture_state_every", 16))
    resolved_validation_steps = require_positive_int(
        validation_steps
        if validation_steps is not None
        else validation_cfg.pop("steps", 128),
        "validation_steps",
    )
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    validation_frame_stride = int(
        validation_cfg.pop("frame_stride", export_frame_stride)
    )
    validation_capture_state_every = int(
        validation_cfg.pop("capture_state_every", export_capture_state_every)
    )
    validation_cfg["artifact_root"] = str(resolved_output_dir / "validation_artifacts")

    replay_runner = SimulationRunner(resolved_output_dir / "replay_artifacts")
    replay_run = replay_runner.run_candidate(
        create_substrate(candidate.substrate),
        candidate,
        steps=resolved_export_steps,
        frame_stride=export_frame_stride,
        capture_state_every=export_capture_state_every,
        save_artifacts=True,
    )

    search_space = _resolve_search_space(spec, candidate.substrate)
    validation = validate_candidate(
        candidate,
        steps=resolved_validation_steps,
        frame_stride=validation_frame_stride,
        capture_state_every=validation_capture_state_every,
        validation_config=validation_cfg,
        search_space=search_space,
    )

    generated_at = utc_timestamp()
    export_trajectory_quality = compute_trajectory_quality_score(replay_run)
    export_holdout = float(validation.holdout_score)
    export_mechanism_signal = compute_mechanism_score(replay_run)
    source_payload = spec.get("source", {})

    payload = {
        "generated_at": generated_at,
        "spec_path": spec_label,
        "flagship": {
            "name": spec["name"],
            "description": spec.get("description", ""),
            "candidate": candidate.to_dict(),
        },
        "source": source_payload,
        "export": {
            "artifact_dir": replay_run.artifact_dir,
            "video_path": replay_run.video_path,
            "trace_path": replay_run.trace_path,
            "executed_steps": replay_run.executed_steps,
            "summary_metrics": replay_run.summary_metrics,
            "trajectory_quality_score": export_trajectory_quality,
            "holdout_score": export_holdout,
            "mechanism_signal": export_mechanism_signal,
            "summary_delta_from_source": _metric_delta(
                source_payload.get("summary_metrics", {}),
                replay_run.summary_metrics,
            ),
        },
        "validation": validation.to_dict(),
        "validation_delta_from_source": _metric_delta(
            source_payload.get("validation", {}),
            validation.to_dict(),
        ),
        "neighborhood_search_space": search_space,
        "assessment": _build_assessment(
            source_payload, replay_run.summary_metrics, validation
        ),
    }

    spec_copy_path = resolved_output_dir / "flagship_spec_resolved.yaml"
    json_path = resolved_output_dir / "flagship_validation_report.json"
    md_path = resolved_output_dir / "flagship_validation_report.md"

    public_spec = to_public_data(spec)
    public_payload = to_public_data(payload, base_dir=resolved_output_dir)
    spec_copy_path.write_text(
        yaml.safe_dump(public_spec, sort_keys=False), encoding="utf-8"
    )
    json_path.write_text(
        json.dumps(public_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(public_payload), encoding="utf-8")

    return public_payload, {
        "output_dir": resolved_output_dir,
        "spec_copy": spec_copy_path,
        "json": json_path,
        "md": md_path,
    }


def _load_spec(path: Path | None) -> tuple[dict[str, Any], str]:
    if path is None:
        resource = files("asal_m.experiments").joinpath(DEFAULT_SPEC_NAME)
        if not resource.is_file():
            raise FileNotFoundError(
                f"Packaged flagship spec is missing: {DEFAULT_SPEC_NAME}"
            )
        text = resource.read_text(encoding="utf-8")
        label = DEFAULT_SPEC_LABEL
    else:
        text = path.read_text(encoding="utf-8")
        label = str(path)
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Flagship spec did not parse as a mapping: {label}")
    return payload, label


def _resolve_search_space(spec: dict[str, Any], substrate: str) -> dict[str, Any]:
    if "neighborhood_search_space" in spec:
        return spec["neighborhood_search_space"]
    return get_search_space(substrate)


def _metric_delta(
    reference: dict[str, Any], current: dict[str, Any]
) -> dict[str, float]:
    keys = sorted(set(reference) | set(current))
    delta: dict[str, float] = {}
    for key in keys:
        try:
            current_value = float(current.get(key, 0.0))
            reference_value = float(reference.get(key, 0.0))
        except (TypeError, ValueError):
            continue
        delta[key] = current_value - reference_value
    return delta


def _build_assessment(
    source_payload: dict[str, Any],
    replay_summary: dict[str, Any],
    validation,
) -> dict[str, Any]:
    source_validation = source_payload.get("validation", {})
    source_summary = source_payload.get("summary_metrics", {})

    current_promotion = float(validation.promotion_score())
    certification = dict(validation.certification)
    source_promotion = float(source_validation.get("promotion_score", 0.0) or 0.0)
    current_occupancy = float(replay_summary.get("occupancy", 0.0) or 0.0)
    source_occupancy = float(source_summary.get("occupancy", 0.0) or 0.0)
    current_budget_entropy = float(replay_summary.get("budget_entropy", 0.0) or 0.0)
    source_budget_entropy = float(source_summary.get("budget_entropy", 0.0) or 0.0)

    notes: list[str] = []
    if validation.deterministic_replay:
        notes.append(
            "Deterministic replay held under the dedicated flagship validation run."
        )
    else:
        notes.append(
            "Deterministic replay failed and this basin should not be treated as a frozen reference."
        )

    promotion_delta = current_promotion - source_promotion
    notes.append(f"Promotion score delta versus source winner: {promotion_delta:+.3f}.")
    notes.append(
        f"Replay occupancy delta versus source winner: {current_occupancy - source_occupancy:+.3f}."
    )
    notes.append(
        f"Replay budget entropy delta versus source winner: {current_budget_entropy - source_budget_entropy:+.3f}."
    )
    if certification.get("passed") is True:
        notes.append(
            f"All hard gates passed under policy {certification['policy']['name']}."
        )
    else:
        failures = ", ".join(certification.get("failure_codes", [])) or "unspecified"
        notes.append(f"Hard-gate certification rejected the basin: {failures}.")

    if certification.get("passed") is True and current_promotion >= max(
        0.85, source_promotion - 0.03
    ):
        status = "stable_flagship"
    elif validation.deterministic_replay:
        status = "mixed_flagship"
    else:
        status = "failed_flagship"

    return {
        "status": status,
        "promotion_delta": promotion_delta,
        "occupancy_delta": current_occupancy - source_occupancy,
        "budget_entropy_delta": current_budget_entropy - source_budget_entropy,
        "certification": certification,
        "notes": notes,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("source", {})
    export = payload["export"]
    validation = payload["validation"]
    assessment = payload["assessment"]
    lines = [
        f"# {payload['flagship']['name']} Validation Report",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Spec: `{payload['spec_path']}`",
        f"- Source artifact: `{source.get('source_artifact_dir', 'unknown')}`",
        f"- Export artifact: `{export.get('artifact_dir', 'unknown')}`",
        f"- Status: `{assessment['status']}`",
        "",
        "## Candidate",
        "",
        f"- Substrate: `{payload['flagship']['candidate']['substrate']}`",
        f"- Search mode: `{payload['flagship']['candidate']['search_mode']}`",
        f"- Seed: `{payload['flagship']['candidate']['seed']}`",
        f"- Budget mode: `{payload['flagship']['candidate']['rule_variants'].get('budget_mode')}`",
        f"- Initialization: `{payload['flagship']['candidate']['initial_conditions'].get('initialization_strategy')}`",
        f"- Grid size: `{payload['flagship']['candidate']['environment'].get('grid_size')}`",
        "",
        "## Export Replay",
        "",
        f"- Executed steps: `{export['executed_steps']}`",
        f"- Holdout score: `{export['holdout_score']:.3f}`",
        f"- Mechanism signal: `{export['mechanism_signal']:.3f}`",
        f"- Occupancy: `{float(export['summary_metrics'].get('occupancy', 0.0)):.3f}`",
        f"- Budget entropy: `{float(export['summary_metrics'].get('budget_entropy', 0.0)):.3f}`",
        f"- Budget utilization: `{float(export['summary_metrics'].get('budget_utilization', 0.0)):.3f}`",
        "",
        "## Validation",
        "",
        f"- Deterministic replay: `{validation['deterministic_replay']}`",
        f"- Replay difference: `{float(validation['replay_difference']):.6f}`",
        f"- Long-horizon score: `{float(validation['long_horizon_score']):.3f}`",
        f"- Perturbation score: `{float(validation['perturbation_score']):.3f}`",
        f"- Neighborhood score: `{float(validation['neighborhood_score']):.3f}`",
        f"- Holdout score: `{float(validation['holdout_score']):.3f}`",
        f"- Promotion score: `{float(validation['promotion_score']):.3f}`",
        "",
        "## Assessment",
        "",
    ]
    for note in assessment.get("notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines).strip() + "\n"


if __name__ == "__main__":
    main()

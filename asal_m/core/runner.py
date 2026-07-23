from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

try:
    from PIL import Image
except ModuleNotFoundError:  # pragma: no cover - depends on local env
    Image = None

from .candidate import CandidateConfig, RunArtifacts
from .interfaces import SubstrateProtocol


class SimulationRunner:
    def __init__(self, artifact_root: str | Path = "runs") -> None:
        self.artifact_root = Path(artifact_root)

    def run_candidate(
        self,
        substrate: SubstrateProtocol,
        candidate: CandidateConfig,
        steps: int,
        frame_stride: int = 4,
        capture_state_every: int = 16,
        save_artifacts: bool = True,
    ) -> RunArtifacts:
        substrate.reset(candidate.to_substrate_config(), candidate.seed)

        frames: list[np.ndarray] = []
        metrics_trace: list[dict[str, float]] = []
        state_snapshots: list[dict[str, Any]] = []

        def capture(step_index: int) -> None:
            frame = np.asarray(substrate.render_frame(), dtype=np.uint8)
            metrics = {"step": float(step_index)}
            metrics.update(_coerce_metrics(substrate.extract_metrics()))
            frames.append(frame)
            metrics_trace.append(metrics)
            if capture_state_every > 0 and step_index % capture_state_every == 0:
                state_snapshots.append(substrate.get_state())

        capture(0)
        executed_steps = 0
        for step_index in range(1, steps + 1):
            substrate.step()
            executed_steps = step_index
            should_capture = (
                step_index % max(1, frame_stride) == 0
                or step_index == steps
                or substrate.is_extinct()
            )
            if should_capture:
                capture(step_index)
            if substrate.is_extinct():
                break

        summary_metrics = dict(metrics_trace[-1] if metrics_trace else {})
        summary_metrics["executed_steps"] = float(executed_steps)
        summary_metrics["survival_fraction"] = float(executed_steps / max(1, steps))

        artifact_dir: Path | None = None
        video_path: Path | None = None
        trace_path: Path | None = None
        if save_artifacts:
            artifact_dir = self._create_artifact_dir(candidate)
            np.savez_compressed(
                artifact_dir / "frames.npz", frames=np.asarray(frames, dtype=np.uint8)
            )
            self._write_json(artifact_dir / "candidate.json", candidate.to_dict())
            self._write_json(artifact_dir / "metrics_trace.json", metrics_trace)
            self._write_json(artifact_dir / "summary.json", summary_metrics)
            self._write_state(artifact_dir / "final_state.npz", substrate.get_state())
            video_path = self._write_gif(artifact_dir / "rollout.gif", frames)
            trace_path = artifact_dir / "metrics_trace.json"

        return RunArtifacts(
            candidate=candidate,
            executed_steps=executed_steps,
            frames=frames,
            metrics_trace=metrics_trace,
            state_snapshots=state_snapshots,
            summary_metrics=summary_metrics,
            artifact_dir=artifact_dir,
            video_path=video_path,
            trace_path=trace_path,
        )

    def _create_artifact_dir(self, candidate: CandidateConfig) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dirname = f"{candidate.substrate}__{candidate.search_mode}__seed{candidate.seed}__{timestamp}"
        artifact_dir = self.artifact_root / dirname
        artifact_dir.mkdir(parents=True, exist_ok=False)
        return artifact_dir

    def _write_gif(self, path: Path, frames: list[np.ndarray]) -> Path | None:
        if not frames or Image is None:
            return None
        pil_frames = [Image.fromarray(frame) for frame in frames]
        pil_frames[0].save(
            path,
            save_all=True,
            append_images=pil_frames[1:],
            optimize=False,
            duration=90,
            loop=0,
        )
        return path

    def _write_state(self, path: Path, state: dict[str, Any]) -> None:
        arrays: dict[str, Any] = {}
        for key, value in state.items():
            arrays[key] = np.asarray(value)
        np.savez_compressed(path, **arrays)

    def _write_json(self, path: Path, payload: Any) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(_to_serializable(payload), handle, indent=2, sort_keys=True)


def _coerce_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    coerced: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, (bool, np.bool_)):
            coerced[key] = float(value)
        elif np.isscalar(value):
            coerced[key] = float(value)
    return coerced


def _to_serializable(payload: Any) -> Any:
    if isinstance(payload, Path):
        return _public_path_string(payload)
    if isinstance(payload, dict):
        return {str(key): _to_serializable(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_to_serializable(value) for value in payload]
    if isinstance(payload, np.ndarray):
        return payload.tolist()
    if isinstance(payload, (np.floating, np.integer)):
        return payload.item()
    if isinstance(payload, (date, datetime)):
        return payload.isoformat()
    if isinstance(payload, str):
        return _maybe_relativize_path_string(payload)
    return payload


def _public_path_string(path: Path) -> str:
    """Prefer repo-relative POSIX paths in written JSON (no host absolute roots)."""
    resolved = path
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    cwd = Path.cwd()
    try:
        return resolved.relative_to(cwd).as_posix()
    except ValueError:
        pass
    # Outside the working tree, retain only the leaf name. Persisted public JSON
    # must never disclose drive roots, UNC shares, or Unix home/temp prefixes.
    normalized = str(path).replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] or "external_path"


def _maybe_relativize_path_string(value: str) -> str:
    if not value:
        return value
    # Windows drive, UNC, rooted Windows, or POSIX absolute paths embedded as strings.
    looks_absolute = value.startswith(("/", "\\")) or (
        len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}
    )
    if not looks_absolute:
        return value.replace("\\", "/")
    try:
        return _public_path_string(Path(value))
    except OSError:
        return Path(value).name

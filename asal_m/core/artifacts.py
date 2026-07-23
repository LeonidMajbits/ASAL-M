from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GPUStatus:
    available: bool
    name: str | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    memory_total_mib: int | None = None
    memory_used_mib: int | None = None
    utilization_gpu_pct: int | None = None
    safe_for_heavy_jobs: bool = False
    recommendation: str = "GPU not detected."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_artifact_root(start: str | Path | None = None) -> Path:
    """Locate an optional local ARTIFACTS directory (not required for public runs)."""
    base = Path.cwd() if start is None else Path(start)
    candidates = [
        base / "ARTIFACTS",
        base.parent / "ARTIFACTS",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not locate an ARTIFACTS directory from the current checkout."
    )


def inspect_artifact_root(root: str | Path) -> dict[str, Any]:
    """Generic read-only inventory of a local artifact directory tree.

    Does not encode private lab bundle names. Safe default is inventory only;
    never auto-executes binaries.
    """
    artifact_root = Path(root).resolve()
    if not artifact_root.exists():
        raise FileNotFoundError(f"Artifact root does not exist: {artifact_root}")

    children: list[dict[str, Any]] = []
    for child in sorted(artifact_root.iterdir(), key=lambda path: path.name.lower()):
        if not child.is_dir():
            continue
        stats = _scan_tree(child)
        exe_count = sum(
            1
            for path in child.rglob("*")
            if path.is_file() and path.suffix.lower() == ".exe"
        )
        children.append(
            {
                "name": child.name,
                "path": str(child),
                "file_count": stats["file_count"],
                "dir_count": stats["dir_count"],
                "total_bytes": stats["total_bytes"],
                "top_extensions": stats["top_extensions"],
                "executable_count": exe_count,
                "auto_run_policy": "never-auto-execute"
                if exe_count
                else "readonly-import",
            }
        )

    summary = {
        "child_dir_count": len(children),
        "total_files": sum(item["file_count"] for item in children),
        "total_dirs": sum(item["dir_count"] for item in children),
        "total_bytes": sum(item["total_bytes"] for item in children),
        "blocked_auto_exec_children": [
            item["name"]
            for item in children
            if item["auto_run_policy"] == "never-auto-execute"
        ],
    }

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "artifact_root": str(artifact_root),
        "gpu": detect_gpu_status().to_dict(),
        "summary": summary,
        "children": children,
        "notes": [
            "This is a generic inventory only.",
            "ASAL-M never auto-executes binaries found under ARTIFACTS.",
        ],
    }


def write_artifact_report(
    report: dict[str, Any], output_dir: str | Path
) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    json_path = destination / "artifact_report.json"
    md_path = destination / "artifact_report.md"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_artifact_report(report), encoding="utf-8")

    return {"json": json_path, "markdown": md_path}


def render_artifact_report(report: dict[str, Any]) -> str:
    gpu = report.get("gpu", {})
    summary = report.get("summary", {})
    lines = [
        "# Artifact inventory",
        "",
        f"Generated: `{report.get('generated_at')}`",
        f"Root: `{report.get('artifact_root')}`",
        "",
        "## GPU",
        f"- Available: `{gpu.get('available')}`",
        f"- Name: `{gpu.get('name')}`",
        f"- Recommendation: {gpu.get('recommendation')}",
        "",
        "## Summary",
        f"- Child directories: `{summary.get('child_dir_count')}`",
        f"- Files: `{summary.get('total_files')}`",
        f"- Bytes: `{summary.get('total_bytes')}`",
        f"- Never-auto-exec children: `{summary.get('blocked_auto_exec_children')}`",
        "",
        "## Children",
    ]
    for child in report.get("children", []):
        lines.extend(
            [
                f"### {child['name']}",
                f"- path: `{child['path']}`",
                f"- files: `{child['file_count']}`",
                f"- bytes: `{child['total_bytes']}`",
                f"- policy: `{child['auto_run_policy']}`",
                "",
            ]
        )
    for note in report.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def detect_gpu_status() -> GPUStatus:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return GPUStatus(
            available=False, recommendation="nvidia-smi not found. Staying CPU-only."
        )
    except subprocess.TimeoutExpired:
        return GPUStatus(
            available=False, recommendation="nvidia-smi timed out. Staying CPU-only."
        )

    if completed.returncode != 0 or not completed.stdout.strip():
        return GPUStatus(
            available=False, recommendation="nvidia-smi returned no usable GPU data."
        )

    first = completed.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in first.split(",")]
    if len(parts) < 5:
        return GPUStatus(
            available=False, recommendation="Could not parse GPU state from nvidia-smi."
        )

    name = parts[0]
    driver_version = parts[1]
    try:
        memory_total = int(float(parts[2]))
        memory_used = int(float(parts[3]))
        utilization = int(float(parts[4]))
    except ValueError:
        memory_total = None
        memory_used = None
        utilization = None

    used_ratio = (
        (memory_used / memory_total)
        if memory_total and memory_used is not None and memory_total > 0
        else 1.0
    )
    safe_for_heavy_jobs = bool(
        utilization is not None
        and memory_used is not None
        and memory_total is not None
        and utilization <= 20
        and used_ratio <= 0.25
    )
    if safe_for_heavy_jobs:
        recommendation = (
            "GPU is available and lightly loaded. Heavy jobs can be opt-in."
        )
    else:
        recommendation = (
            "GPU is present but currently busy. Keep default ASAL-M work CPU-only until "
            "you intentionally reserve the GPU."
        )

    return GPUStatus(
        available=True,
        name=name,
        driver_version=driver_version,
        cuda_version=_detect_cuda_version(),
        memory_total_mib=memory_total,
        memory_used_mib=memory_used,
        utilization_gpu_pct=utilization,
        safe_for_heavy_jobs=safe_for_heavy_jobs,
        recommendation=recommendation,
    )


def _detect_cuda_version() -> str | None:
    try:
        completed = subprocess.run(
            ["nvidia-smi"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    for line in completed.stdout.splitlines():
        if "CUDA Version:" in line:
            return line.split("CUDA Version:")[-1].strip().split()[0]
    return None


def _scan_tree(root: Path) -> dict[str, Any]:
    file_count = 0
    dir_count = 0
    total_bytes = 0
    extensions: Counter[str] = Counter()

    for path in root.rglob("*"):
        if path.is_dir():
            dir_count += 1
            continue
        if not path.is_file():
            continue
        file_count += 1
        try:
            total_bytes += path.stat().st_size
        except OSError:
            pass
        extensions[path.suffix.lower() or "<none>"] += 1

    return {
        "file_count": file_count,
        "dir_count": dir_count,
        "total_bytes": total_bytes,
        "top_extensions": dict(extensions.most_common(8)),
    }

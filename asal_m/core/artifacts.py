from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..public_output import public_path, to_public_data, utc_timestamp


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


def inspect_artifact_root(
    root: str | Path,
    *,
    include_machine_details: bool = False,
    path_base: str | Path | None = None,
) -> dict[str, Any]:
    """Generic read-only inventory of a local artifact directory tree.

    Does not encode private lab bundle names. Safe default is inventory only;
    never auto-executes binaries and omits machine/GPU details.
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
                "path": public_path(child, base_dir=path_base),
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

    report = {
        "generated_at": utc_timestamp(),
        "artifact_root": public_path(artifact_root, base_dir=path_base),
        "machine_details_included": include_machine_details,
        "summary": summary,
        "children": children,
        "notes": [
            "This is a generic inventory only.",
            "ASAL-M never auto-executes binaries found under ARTIFACTS.",
        ],
    }
    if include_machine_details:
        report["machine_details"] = {"gpu": detect_gpu_status().to_dict()}
    return report


def write_artifact_report(
    report: dict[str, Any], output_dir: str | Path
) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    json_path = destination / "artifact_report.json"
    md_path = destination / "artifact_report.md"

    public_report = to_public_data(report)
    json_path.write_text(
        json.dumps(public_report, indent=2, sort_keys=True), encoding="utf-8"
    )
    md_path.write_text(render_artifact_report(public_report), encoding="utf-8")

    return {"json": json_path, "markdown": md_path}


def render_artifact_report(report: dict[str, Any]) -> str:
    machine_details = report.get("machine_details", {})
    gpu = machine_details.get("gpu", {})
    summary = report.get("summary", {})
    lines = [
        "# Artifact inventory",
        "",
        f"Generated: `{report.get('generated_at')}`",
        f"Root: `{report.get('artifact_root')}`",
        "",
        "## Summary",
        f"- Child directories: `{summary.get('child_dir_count')}`",
        f"- Files: `{summary.get('total_files')}`",
        f"- Bytes: `{summary.get('total_bytes')}`",
        f"- Never-auto-exec children: `{summary.get('blocked_auto_exec_children')}`",
        "",
        "## Children",
    ]
    if machine_details:
        lines[5:5] = [
            "## Machine details (explicitly requested)",
            "",
            f"- GPU available: `{gpu.get('available')}`",
            f"- GPU name: `{gpu.get('name')}`",
            f"- Driver: `{gpu.get('driver_version')}`",
            f"- CUDA: `{gpu.get('cuda_version')}`",
            f"- Recommendation: {gpu.get('recommendation')}",
            "",
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
    executable = _find_nvidia_smi()
    if executable is None:
        return GPUStatus(
            available=False, recommendation="nvidia-smi not found. Staying CPU-only."
        )
    try:
        completed = subprocess.run(
            [
                executable,
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
        cuda_version=_detect_cuda_version(executable),
        memory_total_mib=memory_total,
        memory_used_mib=memory_used,
        utilization_gpu_pct=utilization,
        safe_for_heavy_jobs=safe_for_heavy_jobs,
        recommendation=recommendation,
    )


def _detect_cuda_version(executable: str | None = None) -> str | None:
    resolved = executable or _find_nvidia_smi()
    if resolved is None:
        return None
    try:
        completed = subprocess.run(
            [resolved],
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


def _find_nvidia_smi() -> str | None:
    """Locate NVIDIA tooling only at known absolute installation paths."""
    candidates = [
        Path("/usr/bin/nvidia-smi"),
        Path("/usr/local/nvidia/bin/nvidia-smi"),
    ]
    system_root = os.environ.get("SystemRoot")
    if system_root:
        candidates.append(Path(system_root) / "System32" / "nvidia-smi.exe")
    program_files = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(
            Path(program_files) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"
        )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
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

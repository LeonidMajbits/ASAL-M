from __future__ import annotations

import argparse
from pathlib import Path

from ..core.artifacts import (
    default_artifact_root,
    inspect_artifact_root,
    write_artifact_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only inventory of a local ARTIFACTS directory (optional)."
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Artifact root. Defaults to ARTIFACTS in the current directory or its parent.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="runs/artifact_inspection",
        help="Directory for the generated report files.",
    )
    args = parser.parse_args()

    artifact_root = Path(args.root) if args.root else default_artifact_root()
    report = inspect_artifact_root(artifact_root)
    outputs = write_artifact_report(report, args.output_dir)

    print(f"artifact_root={report['artifact_root']}")
    print(f"artifact_report_json={outputs['json']}")
    print(f"artifact_report_md={outputs['markdown']}")
    print(f"gpu_safe_for_heavy_jobs={report['gpu']['safe_for_heavy_jobs']}")
    print(f"gpu_recommendation={report['gpu']['recommendation']}")
    for child in report.get("children", []):
        print(
            f"{child['name']}: files={child['file_count']} "
            f"auto_run_policy={child['auto_run_policy']} executables={child['executable_count']}"
        )


if __name__ == "__main__":
    main()

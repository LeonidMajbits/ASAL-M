from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize an ASAL-M experiment output."
    )
    parser.add_argument("summary", type=str, help="Path to experiment_summary.json")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))

    counts = payload.get("counts", {})
    print(json.dumps(counts, indent=2))
    for name, winner in payload.get("winners", {}).items():
        if not winner:
            print(f"{name}: none")
            continue
        print(
            f"{name}: total={winner['total_score']:.3f} "
            f"occupancy={winner['summary_metrics'].get('occupancy', 0.0):.3f} "
            f"diversity={winner['summary_metrics'].get('diversity', 0.0):.3f}"
        )


if __name__ == "__main__":
    main()

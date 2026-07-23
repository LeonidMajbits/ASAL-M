from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..public_output import to_public_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export winner records from an ASAL-M experiment summary."
    )
    parser.add_argument("summary", type=str, help="Path to experiment_summary.json")
    parser.add_argument(
        "--output", type=str, default=None, help="Optional output path for winners.json"
    )
    args = parser.parse_args()

    summary_path = Path(args.summary)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    winners = payload.get("winners", {})

    output_path = (
        Path(args.output) if args.output else summary_path.with_name("winners.json")
    )
    output_path.write_text(
        json.dumps(to_public_data(winners), indent=2, sort_keys=True), encoding="utf-8"
    )
    print(output_path)


if __name__ == "__main__":
    main()

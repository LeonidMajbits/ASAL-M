from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot winner frontiers from an ASAL-M experiment summary."
    )
    parser.add_argument("summary", type=str, help="Path to experiment_summary.json")
    parser.add_argument(
        "--output", type=str, default=None, help="Optional output image path"
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    winners = [winner for winner in payload.get("winners", {}).values() if winner]
    if not winners:
        raise ValueError("No winners found in summary.")

    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Plotting requires the analysis extra: pip install 'asal-m[analysis]'"
        ) from exc

    novelty = [winner["score_components"].get("novelty", 0.0) for winner in winners]
    robustness = [
        winner["score_components"].get("robustness", 0.0) for winner in winners
    ]
    total = [winner["total_score"] for winner in winners]
    labels = [winner["candidate"]["search_mode"] for winner in winners]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(
        novelty,
        robustness,
        s=[180 * max(0.1, score) for score in total],
        c=total,
        cmap="viridis",
    )
    for x_pos, y_pos, label in zip(novelty, robustness, labels):
        ax.text(x_pos + 0.01, y_pos + 0.01, label, fontsize=8)
    ax.set_xlabel("Novelty")
    ax.set_ylabel("Robustness")
    ax.set_title("ASAL-M Winner Frontier")
    fig.tight_layout()

    output = (
        Path(args.output)
        if args.output
        else Path(args.summary).with_name("winner_frontier.png")
    )
    fig.savefig(output, dpi=180)
    print(output)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..public_output import to_public_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Mutation Cells winners across multiple experiment summaries."
    )
    parser.add_argument(
        "summaries",
        nargs="*",
        help="Optional experiment_summary.json paths. Defaults to the mainline, robust, and promotion Mutation Cells runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="runs/mutation_cells_analysis",
        help="Directory for the generated comparison report.",
    )
    args = parser.parse_args()

    if args.summaries:
        summary_paths = [Path(item) for item in args.summaries]
    else:
        summary_paths = [path for path in _default_summary_paths() if path.exists()]
        if not summary_paths:
            raise FileNotFoundError(
                "No experiment summaries found. Pass paths explicitly or run the starter "
                "mutation_cells experiments first (mainline / robust / promotion)."
            )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries = [_load_summary(path) for path in summary_paths]
    ranked = _rank_winners(summaries)

    payload = {
        "summaries": [str(path) for path in summary_paths],
        "winner_count": len(ranked),
        "flagship": ranked[0] if ranked else None,
        "ranked_winners": ranked,
    }
    public_payload = to_public_data(payload)

    json_path = output_dir / "mutation_winner_comparison.json"
    md_path = output_dir / "mutation_winner_comparison.md"
    json_path.write_text(
        json.dumps(public_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    md_path.write_text(_render_markdown(public_payload), encoding="utf-8")

    print(f"comparison_json={json_path}")
    print(f"comparison_md={md_path}")
    if ranked:
        public_flagship = public_payload["ranked_winners"][0]
        print(
            f"flagship_artifact={public_flagship['artifact_dir']} "
            f"mode={public_flagship['search_mode']} "
            f"flagship_score={public_flagship['flagship_score']:.3f}"
        )


def _default_summary_paths() -> list[Path]:
    return [
        Path("runs/mutation_cells_mainline/experiment_summary.json"),
        Path("runs/mutation_cells_robust/experiment_summary.json"),
        Path("runs/mutation_cells_promotion/experiment_summary.json"),
    ]


def _load_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Summary not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _rank_winners(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    winners_by_artifact: dict[str, dict[str, Any]] = {}

    for summary in summaries:
        experiment_name = str(summary.get("experiment", {}).get("name", "unknown"))
        for role, winner in summary.get("winners", {}).items():
            if not winner:
                continue
            artifact_dir = str(winner.get("artifact_dir") or "")
            if not artifact_dir:
                continue
            record = winners_by_artifact.setdefault(
                artifact_dir,
                {
                    "artifact_dir": artifact_dir,
                    "search_mode": winner["candidate"]["search_mode"],
                    "budget_mode": winner["candidate"]["rule_variants"].get(
                        "budget_mode"
                    ),
                    "initialization_strategy": winner["candidate"][
                        "initial_conditions"
                    ].get("initialization_strategy"),
                    "lineage_budget_strength": winner["candidate"]["params"].get(
                        "lineage_budget_strength"
                    ),
                    "roles": [],
                    "source_experiments": [],
                    "winner": winner,
                },
            )
            record["roles"].append(role)
            record["source_experiments"].append(experiment_name)

    ranked: list[dict[str, Any]] = []
    for artifact_dir, record in winners_by_artifact.items():
        winner = record["winner"]
        score_components = winner.get("score_components", {})
        summary_metrics = winner.get("summary_metrics", {})
        validation = winner.get("validation") or {}

        promotion_score = float(validation.get("promotion_score", 0.0) or 0.0)
        flagship_score = (
            0.35 * float(winner.get("total_score", 0.0))
            + 0.2 * promotion_score
            + 0.15 * float(score_components.get("robustness", 0.0))
            + 0.15 * float(score_components.get("mechanism_signal", 0.0))
            + 0.1 * float(summary_metrics.get("budget_entropy", 0.0))
            + 0.05 * float(score_components.get("lineage_signal", 0.0))
        )

        ranked.append(
            {
                "artifact_dir": artifact_dir,
                "search_mode": record["search_mode"],
                "budget_mode": record["budget_mode"],
                "initialization_strategy": record["initialization_strategy"],
                "lineage_budget_strength": record["lineage_budget_strength"],
                "roles": sorted(set(record["roles"])),
                "source_experiments": sorted(set(record["source_experiments"])),
                "total_score": float(winner.get("total_score", 0.0)),
                "promotion_score": promotion_score,
                "flagship_score": float(flagship_score),
                "score_components": {
                    key: float(score_components.get(key, 0.0))
                    for key in (
                        "novelty",
                        "persistence",
                        "robustness",
                        "lineage_signal",
                        "mechanism_signal",
                        "artifact_penalty",
                    )
                },
                "summary_metrics": {
                    key: float(summary_metrics.get(key, 0.0))
                    for key in (
                        "occupancy",
                        "diversity",
                        "lineage_entropy",
                        "lineage_concentration",
                        "budget_entropy",
                        "budget_utilization",
                        "cluster_coherence",
                        "mean_age",
                        "mean_charge",
                        "mutability_mean",
                        "birth_rate",
                        "death_rate",
                    )
                },
                "validation": {
                    key: validation.get(key)
                    for key in (
                        "deterministic_replay",
                        "replay_difference",
                        "long_horizon_score",
                        "perturbation_score",
                        "neighborhood_score",
                        "holdout_score",
                        "promotion_score",
                    )
                },
            }
        )

    ranked.sort(
        key=lambda item: (
            item["flagship_score"],
            item["promotion_score"],
            item["total_score"],
        ),
        reverse=True,
    )
    return ranked


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Mutation Cells Winner Comparison",
        "",
        "## Inputs",
        "",
    ]
    for summary in payload["summaries"]:
        lines.append(f"- `{summary}`")

    flagship = payload.get("flagship")
    if flagship:
        lines.extend(
            [
                "",
                "## Flagship",
                "",
                f"- Artifact: `{flagship['artifact_dir']}`",
                f"- Search mode: `{flagship['search_mode']}`",
                f"- Budget mode: `{flagship['budget_mode']}`",
                f"- Initialization: `{flagship['initialization_strategy']}`",
                f"- Roles: {', '.join(flagship['roles'])}",
                f"- Flagship score: {flagship['flagship_score']:.3f}",
                f"- Total score: {flagship['total_score']:.3f}",
                f"- Promotion score: {flagship['promotion_score']:.3f}",
            ]
        )

    lines.extend(
        [
            "",
            "## Ranking",
            "",
        ]
    )

    for index, winner in enumerate(payload["ranked_winners"], start=1):
        metrics = winner["summary_metrics"]
        scores = winner["score_components"]
        lines.extend(
            [
                f"### {index}. {winner['search_mode']} :: {winner['budget_mode']}",
                "",
                f"- Artifact: `{winner['artifact_dir']}`",
                f"- Roles: {', '.join(winner['roles'])}",
                f"- Source experiments: {', '.join(winner['source_experiments'])}",
                f"- Flagship score: {winner['flagship_score']:.3f}",
                f"- Total score: {winner['total_score']:.3f}",
                f"- Promotion score: {winner['promotion_score']:.3f}",
                f"- Mechanism signal: {scores['mechanism_signal']:.3f}",
                f"- Robustness: {scores['robustness']:.3f}",
                f"- Occupancy: {metrics['occupancy']:.3f}",
                f"- Budget entropy: {metrics['budget_entropy']:.3f}",
                f"- Budget utilization: {metrics['budget_utilization']:.3f}",
                f"- Cluster coherence: {metrics['cluster_coherence']:.3f}",
            ]
        )

    return "\n".join(lines).strip() + "\n"


if __name__ == "__main__":
    main()

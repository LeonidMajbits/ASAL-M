from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..archive import EliteArchive, NoveltyArchive, RobustnessArchive
from ..core import CandidateConfig, ScoredCandidate, SimulationRunner
from ..core.runner import _to_serializable
from ..scoring import (
    compute_behavior_embedding,
    compute_composite_score,
    evaluate_validation_proxy,
)
from ..substrates import create_substrate, get_search_space
from ..validation import validate_candidate
from .frontier import FrontierSearchMode
from .novelty import OutlierSearchMode
from .promotion import PromotionSearchMode
from .proposals import mutate_sections, sample_sections
from .robustness import RobustnessSearchMode

SEARCH_MODE_REGISTRY = {
    "frontier": FrontierSearchMode,
    "outlier": OutlierSearchMode,
    "robustness": RobustnessSearchMode,
    "promotion": PromotionSearchMode,
}


def create_search_mode(name: str):
    try:
        return SEARCH_MODE_REGISTRY[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown search mode: {name}") from exc


def run_search_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    artifact_root = Path(experiment.get("artifact_root", "runs")) / experiment.get(
        "name",
        f"{experiment['substrate']}_{experiment['search_mode']}",
    )
    artifact_root.mkdir(parents=True, exist_ok=True)

    runner = SimulationRunner(artifact_root)
    rng = np.random.default_rng(int(experiment.get("seed", 0)))
    search_mode = create_search_mode(experiment["search_mode"])
    search_space = _deep_merge(
        get_search_space(experiment["substrate"]), experiment.get("search_space", {})
    )
    elite_archive = EliteArchive(capacity=int(experiment.get("elite_capacity", 24)))
    novelty_archive = NoveltyArchive(
        capacity=int(experiment.get("novelty_capacity", 48))
    )
    robustness_archive = RobustnessArchive(
        capacity=int(experiment.get("robustness_capacity", 24))
    )

    records: list[ScoredCandidate] = []
    steps = int(experiment.get("steps", 96))
    frame_stride = int(experiment.get("frame_stride", 4))
    capture_state_every = int(experiment.get("capture_state_every", 16))
    validation_cfg = experiment.get("validation", {})
    bootstrap_specs = experiment.get("bootstrap_candidates", [])
    bootstrap_evaluated = 0

    for bootstrap_index, bootstrap_candidate in enumerate(
        _load_bootstrap_candidates(
            bootstrap_specs,
            substrate=experiment["substrate"],
            search_mode=search_mode.name,
        )
    ):
        scored = _evaluate_candidate(
            candidate=bootstrap_candidate,
            runner=runner,
            steps=steps,
            frame_stride=frame_stride,
            capture_state_every=capture_state_every,
            experiment=experiment,
            search_mode=search_mode,
            search_space=search_space,
            validation_cfg=validation_cfg,
            elite_archive=elite_archive,
            novelty_archive=novelty_archive,
            robustness_archive=robustness_archive,
            records=records,
            iteration=-(bootstrap_index + 1),
            force_validate=True,
        )
        if scored is not None:
            bootstrap_evaluated += 1

    for iteration in range(int(experiment.get("budget", 24))):
        candidate = _propose_candidate(
            rng=rng,
            iteration=iteration,
            substrate=experiment["substrate"],
            search_mode=search_mode,
            search_space=search_space,
            elite_archive=elite_archive,
            novelty_archive=novelty_archive,
            robustness_archive=robustness_archive,
            explore_probability=float(experiment.get("explore_probability", 0.55)),
        )
        _evaluate_candidate(
            candidate=candidate,
            runner=runner,
            steps=steps,
            frame_stride=frame_stride,
            capture_state_every=capture_state_every,
            experiment=experiment,
            search_mode=search_mode,
            search_space=search_space,
            validation_cfg=validation_cfg,
            elite_archive=elite_archive,
            novelty_archive=novelty_archive,
            robustness_archive=robustness_archive,
            records=records,
            iteration=iteration,
        )

    winners = _select_winners(records)
    summary = {
        "experiment": experiment,
        "counts": {
            "bootstrap_evaluated": bootstrap_evaluated,
            "evaluated": len(records),
            "elite_archive": len(elite_archive.entries),
            "novelty_archive": len(novelty_archive.entries),
            "robustness_archive": len(robustness_archive.entries),
            "certified": sum(
                1
                for item in records
                if item.validation
                and item.validation.certification.get("passed") is True
            ),
            "rejected": sum(
                1
                for item in records
                if item.validation
                and item.validation.certification.get("passed") is False
            ),
        },
        "winners": {
            name: entry.winner_record() if entry else None
            for name, entry in winners.items()
        },
    }
    with (artifact_root / "experiment_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(_to_serializable(summary), handle, indent=2, sort_keys=True)
    return summary


def _should_validate(
    scored: ScoredCandidate, search_mode, iteration: int, validation_cfg: dict[str, Any]
) -> bool:
    interval = int(validation_cfg.get("interval", 4))
    threshold = float(
        validation_cfg.get("score_threshold", search_mode.validation_threshold())
    )
    if scored.total_score >= threshold:
        return True
    return interval > 0 and iteration % interval == 0


def _passes_prefilter(
    summary_metrics: dict[str, float], executed_steps: int, prefilter: dict[str, Any]
) -> bool:
    min_steps = int(prefilter.get("min_steps", 12))
    min_activity = float(prefilter.get("min_activity", 0.005))
    min_occupancy = float(prefilter.get("min_occupancy", 0.01))
    return (
        executed_steps >= min_steps
        and summary_metrics.get("activity", 0.0) >= min_activity
        and summary_metrics.get("occupancy", 0.0) >= min_occupancy
    )


def _propose_candidate(
    rng: np.random.Generator,
    iteration: int,
    substrate: str,
    search_mode,
    search_space: dict[str, Any],
    elite_archive: EliteArchive,
    novelty_archive: NoveltyArchive,
    robustness_archive: RobustnessArchive,
    explore_probability: float,
) -> CandidateConfig:
    parent = None
    if iteration > 0 and rng.random() > explore_probability:
        archive_name = search_mode.preferred_archive()
        if archive_name == "novelty":
            parent = novelty_archive.sample_parent(rng)
        elif archive_name == "robustness":
            parent = robustness_archive.sample_parent(rng)
        else:
            parent = elite_archive.sample_parent(rng)

    if parent is None:
        sections = sample_sections(search_space, rng)
        metadata = {"proposal": "fresh", "iteration": iteration}
    else:
        sections = {
            "params": dict(parent.candidate.params),
            "rule_variants": dict(parent.candidate.rule_variants),
            "environment": dict(parent.candidate.environment),
            "initial_conditions": dict(parent.candidate.initial_conditions),
        }
        mutate_sections(sections, search_space, rng)
        metadata = {
            "proposal": "mutated",
            "iteration": iteration,
            "parent_total": parent.total_score,
            "parent_seed": parent.candidate.seed,
        }

    return CandidateConfig(
        substrate=substrate,
        search_mode=search_mode.name,
        seed=int(rng.integers(0, 2**31 - 1)),
        params=sections["params"],
        rule_variants=sections["rule_variants"],
        environment=sections["environment"],
        initial_conditions=sections["initial_conditions"],
        metadata=metadata,
    )


def _evaluate_candidate(
    candidate: CandidateConfig,
    runner: SimulationRunner,
    steps: int,
    frame_stride: int,
    capture_state_every: int,
    experiment: dict[str, Any],
    search_mode,
    search_space: dict[str, Any],
    validation_cfg: dict[str, Any],
    elite_archive: EliteArchive,
    novelty_archive: NoveltyArchive,
    robustness_archive: RobustnessArchive,
    records: list[ScoredCandidate],
    iteration: int,
    force_validate: bool = False,
) -> ScoredCandidate | None:
    objective_weights = dict(search_mode.objective_weights())
    objective_weights.update(experiment.get("objective_weights", {}))
    needs_proxy_validation = bool(experiment.get("validation_proxy"))

    run = runner.run_candidate(
        create_substrate(candidate.substrate),
        candidate,
        steps=steps,
        frame_stride=frame_stride,
        capture_state_every=capture_state_every,
        save_artifacts=True,
    )
    if not _passes_prefilter(
        run.summary_metrics, run.executed_steps, experiment.get("prefilter", {})
    ):
        return None

    run.embedding = compute_behavior_embedding(run)
    novelty = novelty_archive.novelty(run.embedding)
    diversity_bonus = elite_archive.coverage_bonus(run.embedding)
    proxy_validation = None
    proxy_validation_score = None
    if needs_proxy_validation:
        proxy_validation = evaluate_validation_proxy(
            candidate,
            steps=steps,
            frame_stride=frame_stride,
            capture_state_every=capture_state_every,
            proxy_config=experiment.get("validation_proxy", {}),
            search_space=search_space,
        )
        proxy_validation_score = float(proxy_validation["promotion_proxy"])
    components = compute_composite_score(
        run,
        novelty=novelty,
        diversity_bonus=diversity_bonus,
        target_metrics=experiment.get("target_metrics"),
        validation=None,
        objective_weights=objective_weights,
        validation_proxy_score=proxy_validation_score,
    )
    scored = ScoredCandidate(
        run=run, score_components=components, total_score=components["total"]
    )
    if proxy_validation:
        for key, value in proxy_validation.items():
            if key.endswith("_proxy"):
                scored.score_components[key] = float(value)

    if force_validate or _should_validate(
        scored, search_mode, iteration, validation_cfg
    ):
        validation = validate_candidate(
            candidate,
            steps=steps,
            frame_stride=frame_stride,
            capture_state_every=capture_state_every,
            validation_config=validation_cfg,
            search_space=search_space,
        )
        components = compute_composite_score(
            run,
            novelty=novelty,
            diversity_bonus=diversity_bonus,
            target_metrics=experiment.get("target_metrics"),
            validation=validation,
            objective_weights=objective_weights,
            validation_proxy_score=proxy_validation_score,
        )
        scored.score_components = components
        scored.total_score = components["total"]
        scored.validation = validation

    if scored.total_score >= search_mode.archive_threshold():
        if elite_archive.add(scored):
            scored.archived_in.append("elite")
        if novelty_archive.add(scored):
            scored.archived_in.append("novelty")
    if scored.score_components.get("robustness", 0.0) >= 0.2 and robustness_archive.add(
        scored
    ):
        scored.archived_in.append("robustness")

    records.append(scored)
    return scored


def _load_bootstrap_candidates(
    items: list[Any],
    substrate: str,
    search_mode: str,
) -> list[CandidateConfig]:
    candidates: list[CandidateConfig] = []
    for index, item in enumerate(items):
        source = f"bootstrap_{index}"
        payload = item
        if isinstance(item, (str, Path)):
            path = Path(item)
            source = str(path)
            payload = _load_candidate_payload(path)
        elif not isinstance(item, dict):
            raise TypeError(f"Unsupported bootstrap candidate spec: {type(item)!r}")

        if isinstance(payload, dict) and "candidate" in payload:
            payload = payload["candidate"]
        candidate = CandidateConfig(**payload)
        if candidate.substrate != substrate:
            raise ValueError(
                f"Bootstrap candidate substrate mismatch: expected {substrate}, got {candidate.substrate}"
            )
        candidate = candidate.with_updates(
            substrate=substrate,
            search_mode=search_mode,
            metadata={
                "proposal": "bootstrap",
                "bootstrap_source": source,
            },
        )
        candidates.append(candidate)
    return candidates


def _load_candidate_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Bootstrap candidate path not found: {path}")
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _select_winners(
    records: list[ScoredCandidate],
) -> dict[str, ScoredCandidate | None]:
    if not records:
        return {
            "mainline": None,
            "novelty": None,
            "robustness": None,
            "promotion": None,
        }

    def novelty_value(item: ScoredCandidate) -> float:
        return item.score_components.get(
            "novelty", 0.0
        ) - 0.5 * item.score_components.get("artifact_penalty", 0.0)

    def robustness_value(item: ScoredCandidate) -> float:
        return item.score_components.get(
            "robustness", 0.0
        ) + 0.2 * item.score_components.get("persistence", 0.0)

    def promotion_value(item: ScoredCandidate) -> tuple[int, float, float]:
        validation_score = item.validation.promotion_score() if item.validation else 0.0
        certification_rank = -1
        if item.validation:
            certification_rank = (
                1 if item.validation.certification.get("passed") is True else 0
            )
        return (
            certification_rank,
            validation_score,
            item.total_score,
        )

    return {
        "mainline": max(records, key=lambda item: item.total_score),
        "novelty": max(records, key=novelty_value),
        "robustness": max(records, key=robustness_value),
        "promotion": max(records, key=promotion_value),
    }


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged

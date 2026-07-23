from asal_m.core.candidate import (
    CandidateConfig,
    RunArtifacts,
    ScoredCandidate,
    ValidationReport,
)
from asal_m.search import _select_winners


def _record(
    seed: int,
    *,
    total_score: float,
    promotion_score: float = 0.0,
    certified: bool | None = None,
) -> ScoredCandidate:
    candidate = CandidateConfig(
        substrate="alpha_alife", search_mode="promotion", seed=seed
    )
    run = RunArtifacts(
        candidate=candidate,
        executed_steps=1,
        frames=[],
        metrics_trace=[],
        state_snapshots=[],
        summary_metrics={},
    )
    validation = None
    if certified is not None:
        validation = ValidationReport(
            deterministic_replay=True,
            replay_difference=1.0 - promotion_score,
            long_horizon_score=promotion_score,
            perturbation_score=promotion_score,
            neighborhood_score=promotion_score,
            holdout_score=promotion_score,
            certification={
                "status": "certified" if certified else "rejected",
                "passed": certified,
            },
        )
    return ScoredCandidate(
        run=run,
        score_components={},
        total_score=total_score,
        validation=validation,
    )


def test_select_winners_returns_all_roles_for_empty_input() -> None:
    winners = _select_winners([])

    assert set(winners) == {"mainline", "novelty", "robustness", "promotion"}
    assert all(winner is None for winner in winners.values())


def test_promotion_prefers_certified_over_higher_scoring_rejected_candidate() -> None:
    certified = _record(1, total_score=0.20, promotion_score=0.70, certified=True)
    rejected = _record(2, total_score=0.99, promotion_score=0.99, certified=False)

    assert _select_winners([rejected, certified])["promotion"] is certified


def test_promotion_prefers_rejected_evidence_over_unvalidated_candidate() -> None:
    rejected = _record(1, total_score=0.20, promotion_score=0.40, certified=False)
    unvalidated = _record(2, total_score=0.99)

    assert _select_winners([unvalidated, rejected])["promotion"] is rejected


def test_promotion_uses_pure_promotion_score_before_total_score() -> None:
    validation_winner = _record(
        1, total_score=0.20, promotion_score=0.90, certified=True
    )
    discovery_winner = _record(
        2, total_score=0.99, promotion_score=0.80, certified=True
    )

    assert (
        _select_winners([discovery_winner, validation_winner])["promotion"]
        is validation_winner
    )


def test_promotion_uses_total_score_only_as_final_tie_breaker() -> None:
    lower_total = _record(1, total_score=0.60, promotion_score=0.80, certified=True)
    higher_total = _record(2, total_score=0.70, promotion_score=0.80, certified=True)

    assert _select_winners([lower_total, higher_total])["promotion"] is higher_total


def test_promotion_uses_total_score_for_unvalidated_candidates() -> None:
    lower_total = _record(1, total_score=0.60)
    higher_total = _record(2, total_score=0.70)

    assert _select_winners([lower_total, higher_total])["promotion"] is higher_total

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from ..core.candidate import ValidationReport


@dataclass(frozen=True)
class CertificationPolicy:
    """Hard gates for promoting a discovered regime under a named protocol.

    The aggregate promotion score is useful for ranking, but it must not allow a
    strong dimension to hide a failed or unevaluated one.  These defaults are
    engineering thresholds for the bundled demos, not universal scientific
    constants.
    """

    name: str = "default-v1"
    require_deterministic_replay: bool = True
    max_replay_difference: float = 1e-9
    min_long_horizon_score: float = 0.70
    min_perturbation_score: float = 0.65
    min_neighborhood_score: float = 0.45
    min_holdout_score: float = 0.70
    min_promotion_score: float = 0.75

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any] | None = None
    ) -> "CertificationPolicy":
        values = dict(payload or {})
        unknown = sorted(set(values) - set(cls.__dataclass_fields__))
        if unknown:
            raise ValueError(
                f"Unknown certification policy fields: {', '.join(unknown)}"
            )
        policy = cls(**values)
        policy._validate()
        return policy

    def _validate(self) -> None:
        bounded = {
            "max_replay_difference": self.max_replay_difference,
            "min_long_horizon_score": self.min_long_horizon_score,
            "min_perturbation_score": self.min_perturbation_score,
            "min_neighborhood_score": self.min_neighborhood_score,
            "min_holdout_score": self.min_holdout_score,
            "min_promotion_score": self.min_promotion_score,
        }
        invalid = [
            name for name, value in bounded.items() if not 0.0 <= float(value) <= 1.0
        ]
        if invalid:
            raise ValueError(
                f"Certification thresholds must be within [0, 1]: {', '.join(invalid)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CertificationDecision:
    status: str
    passed: bool
    policy: dict[str, Any]
    promotion_score: float
    checks: dict[str, dict[str, Any]]
    failure_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_certification(
    report: ValidationReport,
    policy: CertificationPolicy | Mapping[str, Any] | None = None,
) -> CertificationDecision:
    """Return an explicit pass/reject result without averaging away failures."""

    if policy is None:
        resolved = CertificationPolicy()
    elif isinstance(policy, CertificationPolicy):
        resolved = policy
        resolved._validate()
    else:
        resolved = CertificationPolicy.from_mapping(policy)

    evaluated = {
        "deterministic_replay": True,
        "long_horizon": "long_run_summary" in report.details,
        "perturbation": bool(report.details.get("perturbations")),
        "neighborhood": bool(report.details.get("neighborhood")),
        "holdout": bool(report.details.get("holdout")),
        "promotion": True,
    }
    promotion_score = float(report.promotion_score())
    specifications = {
        "deterministic_replay": {
            "value": bool(report.deterministic_replay),
            "threshold": True,
            "operator": "is",
            "required": bool(resolved.require_deterministic_replay),
            "passed": bool(report.deterministic_replay),
        },
        "replay_difference": {
            "value": float(report.replay_difference),
            "threshold": float(resolved.max_replay_difference),
            "operator": "<=",
            "required": True,
            "passed": float(report.replay_difference)
            <= float(resolved.max_replay_difference),
        },
        "long_horizon": {
            "value": float(report.long_horizon_score),
            "threshold": float(resolved.min_long_horizon_score),
            "operator": ">=",
            "required": True,
            "passed": float(report.long_horizon_score)
            >= float(resolved.min_long_horizon_score),
        },
        "perturbation": {
            "value": float(report.perturbation_score),
            "threshold": float(resolved.min_perturbation_score),
            "operator": ">=",
            "required": True,
            "passed": float(report.perturbation_score)
            >= float(resolved.min_perturbation_score),
        },
        "neighborhood": {
            "value": float(report.neighborhood_score),
            "threshold": float(resolved.min_neighborhood_score),
            "operator": ">=",
            "required": True,
            "passed": float(report.neighborhood_score)
            >= float(resolved.min_neighborhood_score),
        },
        "holdout": {
            "value": float(report.holdout_score),
            "threshold": float(resolved.min_holdout_score),
            "operator": ">=",
            "required": True,
            "passed": float(report.holdout_score) >= float(resolved.min_holdout_score),
        },
        "promotion": {
            "value": promotion_score,
            "threshold": float(resolved.min_promotion_score),
            "operator": ">=",
            "required": True,
            "passed": promotion_score >= float(resolved.min_promotion_score),
        },
    }

    failures: list[str] = []
    checks: dict[str, dict[str, Any]] = {}
    for name, spec in specifications.items():
        evidence_name = "deterministic_replay" if name == "replay_difference" else name
        was_evaluated = bool(evaluated[evidence_name])
        required = bool(spec["required"])
        passed = bool(spec["passed"]) and (was_evaluated or not required)
        checks[name] = {**spec, "evaluated": was_evaluated, "passed": passed}
        if required and not was_evaluated:
            failures.append(f"{name}_not_evaluated")
        elif required and not passed:
            failures.append(f"{name}_below_policy")

    passed = not failures
    return CertificationDecision(
        status="certified" if passed else "rejected",
        passed=passed,
        policy=resolved.to_dict(),
        promotion_score=promotion_score,
        checks=checks,
        failure_codes=failures,
    )

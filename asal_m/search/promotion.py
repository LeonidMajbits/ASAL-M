from __future__ import annotations


class PromotionSearchMode:
    name = "promotion"

    def objective_weights(self):
        return {
            "target_fit": 0.05,
            "novelty": 0.08,
            "diversity_bonus": 0.12,
            "persistence": 0.22,
            "robustness": 0.33,
            "lineage_signal": 0.2,
            "artifact_penalty": 0.3,
        }

    def preferred_archive(self) -> str:
        return "robustness"

    def validation_threshold(self) -> float:
        return 0.24

    def archive_threshold(self) -> float:
        return 0.16

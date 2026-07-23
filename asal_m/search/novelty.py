from __future__ import annotations


class OutlierSearchMode:
    name = "outlier"

    def objective_weights(self):
        return {
            "target_fit": 0.05,
            "novelty": 0.35,
            "diversity_bonus": 0.18,
            "persistence": 0.12,
            "robustness": 0.1,
            "lineage_signal": 0.2,
            "artifact_penalty": 0.3,
        }

    def preferred_archive(self) -> str:
        return "novelty"

    def validation_threshold(self) -> float:
        return 0.34

    def archive_threshold(self) -> float:
        return 0.2

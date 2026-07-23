from __future__ import annotations


class FrontierSearchMode:
    name = "frontier"

    def objective_weights(self):
        return {
            "target_fit": 0.1,
            "novelty": 0.22,
            "diversity_bonus": 0.18,
            "persistence": 0.22,
            "robustness": 0.13,
            "lineage_signal": 0.15,
            "artifact_penalty": 0.25,
        }

    def preferred_archive(self) -> str:
        return "elites"

    def validation_threshold(self) -> float:
        return 0.4

    def archive_threshold(self) -> float:
        return 0.24

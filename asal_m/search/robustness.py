from __future__ import annotations


class RobustnessSearchMode:
    name = "robustness"

    def objective_weights(self):
        return {
            "target_fit": 0.05,
            "novelty": 0.1,
            "diversity_bonus": 0.08,
            "persistence": 0.22,
            "robustness": 0.35,
            "lineage_signal": 0.1,
            "artifact_penalty": 0.32,
        }

    def preferred_archive(self) -> str:
        return "robustness"

    def validation_threshold(self) -> float:
        return 0.28

    def archive_threshold(self) -> float:
        return 0.18

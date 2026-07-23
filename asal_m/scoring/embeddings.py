from __future__ import annotations

import math

import numpy as np

from ..core.candidate import RunArtifacts

_METRIC_KEYS = (
    "occupancy",
    "diversity",
    "lineage_entropy",
    "cluster_coherence",
    "activity",
    "mean_age",
    "mean_energy",
    "resource_balance",
    "gene_variance",
    "mean_charge",
    "mutability_mean",
    "budget_entropy",
    "budget_utilization",
    "lineage_concentration",
    "birth_rate",
    "death_rate",
    "survival_fraction",
)


def compute_behavior_embedding(run: RunArtifacts) -> np.ndarray:
    frame_features = _frame_features(run.frames)
    metric_features = np.asarray(
        [float(run.summary_metrics.get(key, 0.0)) for key in _METRIC_KEYS], dtype=float
    )
    embedding = np.concatenate([frame_features, metric_features])
    norm = np.linalg.norm(embedding)
    if norm == 0.0:
        return embedding
    return embedding / norm


def embedding_distance(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0:
        return 0.0
    return float(np.linalg.norm(left - right) / math.sqrt(left.size))


def _frame_features(frames: list[np.ndarray]) -> np.ndarray:
    if not frames:
        return np.zeros(8, dtype=float)

    stack = np.asarray(frames, dtype=float) / 255.0
    grayscale = stack.mean(axis=-1)
    temporal_delta = (
        np.abs(np.diff(grayscale, axis=0)).mean() if len(stack) > 1 else 0.0
    )
    temporal_std = np.std(grayscale.mean(axis=(1, 2)))
    spatial_std = grayscale.std()
    brightness = grayscale.mean()
    high_energy = float((grayscale > 0.8).mean())
    low_energy = float((grayscale < 0.05).mean())
    edge_density = float(
        (
            np.abs(np.diff(grayscale, axis=1)).mean()
            + np.abs(np.diff(grayscale, axis=2)).mean()
        )
        / 2.0
    )
    entropy = _estimate_entropy(grayscale)
    return np.asarray(
        [
            brightness,
            spatial_std,
            temporal_delta,
            temporal_std,
            high_energy,
            low_energy,
            edge_density,
            entropy,
        ],
        dtype=float,
    )


def _estimate_entropy(values: np.ndarray) -> float:
    hist, _ = np.histogram(values, bins=16, range=(0.0, 1.0), density=True)
    hist = hist / np.maximum(1e-8, hist.sum())
    return float(-(hist * np.log(hist + 1e-12)).sum() / np.log(len(hist)))

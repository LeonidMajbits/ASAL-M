from __future__ import annotations

from typing import Any

import numpy as np

_NEIGHBOR_SHIFTS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def neighbor_sum(values: np.ndarray) -> np.ndarray:
    total = np.zeros_like(values, dtype=float)
    for dy, dx in _NEIGHBOR_SHIFTS:
        total += np.roll(np.roll(values, dy, axis=0), dx, axis=1)
    return total


def neighbor_mean(values: np.ndarray, alive: np.ndarray) -> np.ndarray:
    weighted_sum = neighbor_sum(values * alive)
    counts = neighbor_sum(alive.astype(float))
    return weighted_sum / np.maximum(1.0, counts)


def step_mutation_cells(
    state: dict[str, Any],
    rng: np.random.Generator,
    config: dict[str, Any],
) -> dict[str, Any]:
    params = config["params"]
    rules = config["rule_variants"]

    lineage = state["lineage"]
    gene = state["gene"]
    charge = state["charge"]
    mutability = state["mutability"]
    age = state["age"]

    prev_lineage = lineage.copy()
    prev_gene = gene.copy()

    alive = lineage > 0
    age[alive] += 1
    counts = neighbor_sum(alive.astype(float))
    mean_gene = neighbor_mean(gene, alive)
    similarity = 1.0 - np.abs(gene - mean_gene)
    similarity = np.clip(similarity, 0.0, 1.0)

    charge_delta = counts / 8.0 * params["charge_gain"] * (0.45 + 0.55 * similarity)
    charge[:] = np.clip(
        charge + charge_delta * alive - params["charge_decay"] * alive, 0.0, 2.0
    )
    charge[:] -= (
        np.clip(counts - rules["survival_max"], 0.0, None)
        * params["crowding_cost"]
        * alive
    )

    mutation_roll = rng.random(gene.shape)
    inplace_mutation = alive & (mutation_roll < params["background_mutation"])
    if inplace_mutation.any():
        gene[inplace_mutation] = np.clip(
            gene[inplace_mutation] + rng.normal(0.0, mutability[inplace_mutation]),
            0.0,
            1.0,
        )
        mutability[inplace_mutation] = np.clip(
            mutability[inplace_mutation]
            + rng.normal(
                0.0, params["mutability_drift"], size=int(inplace_mutation.sum())
            ),
            params["min_mutability"],
            params["max_mutability"],
        )

    death_mask = alive & (
        (charge <= params["death_charge"])
        | (counts < rules["survival_min"])
        | (counts > rules["survival_max"])
        | (rng.random(gene.shape) < params["background_mortality"])
    )
    death_count = int(death_mask.sum())
    lineage[death_mask] = 0
    gene[death_mask] = 0.0
    charge[death_mask] = 0.0
    mutability[death_mask] = 0.0
    age[death_mask] = 0

    alive = lineage > 0
    counts = neighbor_sum(alive.astype(float))
    birth_mask = (
        (~alive) & (counts >= rules["birth_min"]) & (counts <= rules["birth_max"])
    )

    birth_sites = np.argwhere(birth_mask)
    rng.shuffle(birth_sites)
    budget_mode = str(rules.get("budget_mode", "uniform"))
    lineage_quotas: dict[int, int] = {}
    quota_total = len(birth_sites)
    if budget_mode == "dynamic":
        lineage_quotas, budget_entropy = _compute_lineage_birth_quotas(
            lineage=lineage,
            gene=gene,
            charge=charge,
            mutability=mutability,
            target_births=quota_total,
            strength=float(params["lineage_budget_strength"]),
        )
        state["last_budget_entropy"] = budget_entropy
        state["last_budgeted_lineages"] = float(len(lineage_quotas))
    else:
        state["last_budget_entropy"] = 0.0
        state["last_budgeted_lineages"] = float(np.unique(lineage[alive]).size)
    birth_count = 0
    for row, col in birth_sites:
        parents: list[tuple[int, int]] = []
        weights: list[float] = []
        for d_row, d_col in _NEIGHBOR_SHIFTS:
            n_row = (row + d_row) % lineage.shape[0]
            n_col = (col + d_col) % lineage.shape[1]
            if lineage[n_row, n_col] <= 0:
                continue
            if (
                budget_mode == "dynamic"
                and lineage_quotas.get(int(lineage[n_row, n_col]), 0) <= 0
            ):
                continue
            if charge[n_row, n_col] < params["offspring_charge"] * 0.6:
                continue
            parents.append((n_row, n_col))
            weights.append(max(0.01, charge[n_row, n_col]))

        if not parents:
            continue

        parent_index = int(
            rng.choice(len(parents), p=np.asarray(weights) / np.sum(weights))
        )
        parent_row, parent_col = parents[parent_index]
        parent_lineage = int(lineage[parent_row, parent_col])
        child_gene = float(
            np.clip(
                gene[parent_row, parent_col]
                + rng.normal(0.0, max(0.01, mutability[parent_row, parent_col])),
                0.0,
                1.0,
            )
        )
        child_mutability = float(
            np.clip(
                mutability[parent_row, parent_col]
                + rng.normal(0.0, params["mutability_drift"]),
                params["min_mutability"],
                params["max_mutability"],
            )
        )
        child_lineage = parent_lineage
        if (
            abs(child_gene - gene[parent_row, parent_col])
            > params["lineage_split_threshold"]
        ):
            child_lineage = int(state["lineage_counter"])
            state["lineage_counter"] += 1

        lineage[row, col] = child_lineage
        gene[row, col] = child_gene
        mutability[row, col] = child_mutability
        charge[row, col] = params["offspring_charge"]
        age[row, col] = 0
        charge[parent_row, parent_col] = max(
            0.0, charge[parent_row, parent_col] - params["reproduction_cost"]
        )
        if budget_mode == "dynamic":
            lineage_quotas[parent_lineage] = max(
                0, lineage_quotas.get(parent_lineage, 0) - 1
            )
        birth_count += 1

    alive = lineage > 0
    state["step_index"] += 1
    changed = (lineage != prev_lineage) | (np.abs(gene - prev_gene) > 0.02)
    state["last_change_rate"] = float(changed.mean())
    state["last_births"] = birth_count
    state["last_deaths"] = death_count
    state["last_alive_fraction"] = float(alive.mean())
    state["last_budget_utilization"] = (
        float(birth_count / max(1, quota_total)) if budget_mode == "dynamic" else 1.0
    )
    return state


def _compute_lineage_birth_quotas(
    lineage: np.ndarray,
    gene: np.ndarray,
    charge: np.ndarray,
    mutability: np.ndarray,
    target_births: int,
    strength: float,
) -> tuple[dict[int, int], float]:
    alive = lineage > 0
    live_lineages = np.unique(lineage[alive])
    if target_births <= 0 or live_lineages.size == 0:
        return {}, 0.0

    strength = float(np.clip(strength, 0.0, 1.0))
    global_gene_mean = float(gene[alive].mean()) if alive.any() else 0.5

    charge_scores: list[float] = []
    novelty_scores: list[float] = []
    mutability_scores: list[float] = []
    for lineage_id in live_lineages:
        mask = lineage == lineage_id
        lineage_gene = gene[mask]
        charge_scores.append(float(charge[mask].mean()))
        novelty_scores.append(
            float(abs(lineage_gene.mean() - global_gene_mean) + lineage_gene.std())
        )
        mutability_scores.append(float(mutability[mask].mean()))

    dynamic = (
        0.5 * _normalize_scores(np.asarray(charge_scores, dtype=float))
        + 0.3 * _normalize_scores(np.asarray(novelty_scores, dtype=float))
        + 0.2 * _normalize_scores(np.asarray(mutability_scores, dtype=float))
    )
    if dynamic.sum() <= 0.0:
        dynamic = np.full(live_lineages.size, 1.0 / live_lineages.size, dtype=float)
    else:
        dynamic = dynamic / dynamic.sum()

    uniform = np.full(live_lineages.size, 1.0 / live_lineages.size, dtype=float)
    shares = (1.0 - strength) * uniform + strength * dynamic
    quotas = _round_to_total(shares, target_births)
    entropy = float(
        -(shares * np.log(shares + 1e-12)).sum() / np.log(max(2, shares.size))
    )
    return {
        int(lineage_id): int(quota) for lineage_id, quota in zip(live_lineages, quotas)
    }, entropy


def _normalize_scores(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    values = np.clip(values, 0.0, None)
    max_value = float(values.max(initial=0.0))
    if max_value <= 0.0:
        return np.zeros_like(values)
    return values / max_value


def _round_to_total(shares: np.ndarray, total: int) -> np.ndarray:
    if shares.size == 0 or total <= 0:
        return np.zeros_like(shares, dtype=int)
    raw = shares / max(1e-12, shares.sum()) * float(total)
    quotas = np.floor(raw).astype(int)
    remainder = int(total - quotas.sum())
    if remainder > 0:
        order = np.argsort(-(raw - quotas))
        quotas[order[:remainder]] += 1
    return quotas

# Architecture

## Layers

```text
┌─────────────────────────────────────────────────────────┐
│  CLI · experiment YAMLs · analysis and exports          │
├─────────────────────────────────────────────────────────┤
│  proposal · scoring · archives · certification          │
├─────────────────────────────────────────────────────────┤
│  substrate contract (alpha_alife, mutation_cells, …)    │
└─────────────────────────────────────────────────────────┘
                         │ freeze candidate + policy
                         ▼
┌─────────────────────────────────────────────────────────┐
│  operator-owned final audit on untouched evidence       │
└─────────────────────────────────────────────────────────┘
```

Certification is part of the workbench. The final audit is a separate protocol
boundary: a generic search cannot guarantee evidence is untouched because only
the operator knows what influenced candidate selection and policy calibration.
The bundled benchmark demonstrates a leakage-safe audit explicitly.

### `asal_m/core`

- candidate records and validation report types
- experiment runner glue
- optional read-only artifact inventory helpers

### `asal_m/substrates`

Independent simulation programs. They must not import search/archive policy. They only implement the substrate contract (reset/step/render/state/metrics/perturbation/extinction).

### `asal_m/search`

Deterministic reference proposal, budget loop, mode-specific archive preference,
and experiment orchestration. External optimizers may supply candidates instead.

### `asal_m/scoring`

Composite score terms and validation proxies. Scores are tools, not truth.

### `asal_m/archive`

Three archives:

| Archive | Role |
|---|---|
| elite | high total / promotion pressure |
| novelty | behavioral / feature diversity |
| robustness | survival under stress |

### `asal_m/validation`

Adversarial suite plus named hard-gate policy. Aggregate scores rank candidates;
the certification decision rejects any required dimension that fails or was not
evaluated.

### `asal_m/analysis`

Post-run summaries, winner exports, plots, winner comparison, artifact inventory,
and flagship revalidation. These commands consume written summaries or explicit
specifications; they do not silently alter a search result.

## End-to-end data flow

```text
experiment YAML
  -> resolved mapping + seeded proposer
  -> CandidateConfig
  -> SimulationRunner
  -> RunArtifacts
  -> composite score + archive admission
  -> optional ValidationReport
  -> CertificationDecision
  -> experiment_summary.json
```

The discovery rollout is persisted before prefiltering. Validation reruns are
held in memory by default; their scalar results and evidence summaries are
serialized into validated winner records. This is why attempted candidate
directories can outnumber scored records.

## Public contracts

### Candidate contract

`CandidateConfig` freezes the substrate, search mode, seed, and four simulation
sections: parameters, rule variants, environment, and initial conditions.

### Substrate contract

Substrates implement deterministic reset/step behavior, rendering, state
round-trip, scalar metrics, perturbations, and extinction detection. They do not
own search or certification policy.

### Validation contract

`ValidationReport` contains replay, long-horizon, perturbation, neighborhood,
and held-out-seed values plus evidence details. `CertificationDecision` applies
a named hard policy and emits stable failure codes.

### Artifact contract

`experiment_summary.json` is the experiment-level interchange surface. Paths
written into public JSON are normalized to repository-relative POSIX form where
possible; outside-tree paths are reduced to a leaf name to avoid leaking host
roots.

## Modes

| Mode | Intent |
|---|---|
| `frontier` | explore high-scoring new regimes |
| `outlier` | chase unusual mechanism signatures |
| `robustness` | prefer stress-stable candidates |
| `promotion` | maximum validation pressure before “keep” |

The experiment mode controls proposal and validation pressure. The final
`promotion` winner uses a separate lexicographic rule: certification state,
aggregate promotion score, then total score as the final tie-breaker. A failed
or unevaluated candidate cannot outrank a certified candidate through discovery
score alone.

## Design rules

1. **Substrate isolation** — simulation code is not allowed to become a junk drawer for search policy.
2. **Protocol over vibe** — claims attach to YAML + seeds + suite, not screenshots alone.
3. **Archives are plural** — one elite list is not enough.
4. **Validation is adversarial** — interesting is cheap; durable is expensive.
5. **Missing is not failed** — incomplete evidence is reported as `not_evaluated`.
6. **Audit stays untouched** — final evidence cannot participate in candidate or policy selection.
7. **No private path requirements** — public runs must work without host-specific freezes.
8. **Table vs blueprint** — ASAL-M is the workbench; users bring guest substrates and freezes.

See also: [USER_GUIDE.md](USER_GUIDE.md),
[EXPERIMENTS.md](EXPERIMENTS.md), and
[ADDING_A_SUBSTRATE.md](ADDING_A_SUBSTRATE.md).

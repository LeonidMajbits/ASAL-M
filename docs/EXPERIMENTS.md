# Experiment reference

ASAL-M experiments are YAML mappings. Public starter specs live in
`asal_m/experiments/` and are packaged with the wheel.

For a guided first run, start with [USER_GUIDE.md](USER_GUIDE.md). This page is
the field reference.

## Packaged starters

| Name | Substrate | Mode | Purpose |
|---|---|---|---|
| `alpha_mainline` | `alpha_alife` | `frontier` | lightweight general search |
| `alpha_robust` | `alpha_alife` | `robustness` | stronger stress pressure |
| `mut_cells_mainline` | `mutation_cells` | `frontier` | general mutation-cells search |
| `mut_cells_robust` | `mutation_cells` | `robustness` | stress-oriented mutation cells |
| `mut_cells_promotion` | `mutation_cells` | `promotion` | certification-oriented selection |
| `flagship_template_example` | frozen candidate template | n/a | out-of-loop revalidation shape |

Run a packaged starter by name:

```sh
python -m asal_m --experiment alpha_mainline --budget 4 --steps 32
```

Or run a YAML path:

```sh
python -m asal_m --experiment asal_m/experiments/alpha_mainline.yaml --budget 4 --steps 32
```

Packaged-name lookup is used only when the argument is a plain name. A string
containing path components is treated as a path and must exist.

## Complete example

```yaml
name: my_experiment
seed: 1
substrate: alpha_alife
search_mode: promotion
budget: 12
steps: 64
frame_stride: 4
capture_state_every: 12
artifact_root: runs

elite_capacity: 24
novelty_capacity: 48
robustness_capacity: 24
explore_probability: 0.55

target_metrics:
  occupancy: 0.18
  diversity: 0.20

objective_weights:
  mechanism_signal: 0.10

prefilter:
  min_steps: 12
  min_activity: 0.005
  min_occupancy: 0.01

validation:
  interval: 2
  score_threshold: 0.24
  long_steps_multiplier: 2
  neighbor_samples: 4
  holdout_steps: 64
  holdout_seed_offsets: [101, 202, 303]
  perturbations:
    - kind: wipe_patch
      size: 0.18
    - kind: mortality_burst
      rate: 0.18
  certification_policy:
    name: alpha-demo-v1
    require_deterministic_replay: true
    max_replay_difference: 1.0e-9
    min_long_horizon_score: 0.70
    min_perturbation_score: 0.65
    min_neighborhood_score: 0.45
    min_holdout_score: 0.70
    min_promotion_score: 0.75
```

## Top-level fields

Only `substrate` and `search_mode` are structurally required by the runner. A
named, explicit experiment is strongly recommended for reproducibility.

| Field | Default | Meaning |
|---|---:|---|
| `name` | `<substrate>_<mode>` | output directory and experiment identity |
| `seed` | `0` | seeded proposer random-number generator |
| `substrate` | required | registered substrate name |
| `search_mode` | required | `frontier`, `outlier`, `robustness`, or `promotion` |
| `budget` | `24` | number of proposals attempted after bootstraps |
| `steps` | `96` | base discovery rollout steps |
| `frame_stride` | `4` | frame/metric capture cadence |
| `capture_state_every` | `16` | state-snapshot cadence during in-memory runs |
| `artifact_root` | `runs` | root for candidate artifacts and summary |
| `elite_capacity` | `24` | maximum elite archive entries |
| `novelty_capacity` | `48` | maximum novelty archive entries |
| `robustness_capacity` | `24` | maximum robustness archive entries |
| `explore_probability` | `0.55` | probability of a fresh sample instead of parent mutation |
| `target_metrics` | `{}` | target values used by the target-fit component |
| `objective_weights` | mode defaults | component-weight overrides |
| `prefilter` | defaults below | cheap acceptance checks before scoring records |
| `validation` | defaults below | full validation cadence, evidence, and hard policy |
| `validation_proxy` | absent | optional extra proxy reruns for every accepted candidate |
| `search_space` | `{}` | deep-merged overrides for the substrate default space |
| `bootstrap_candidates` | `[]` | frozen candidates evaluated before generated proposals |
| `reference` | ignored | operator metadata retained in the summary |
| `metadata` | ignored | additional operator metadata retained in the summary |

CLI `--budget` and `--steps` replace the resolved values in memory and in the
written experiment summary. They do not edit the source YAML.

### Objective components

`objective_weights` may override:

- `target_fit`
- `novelty`
- `diversity_bonus`
- `persistence`
- `robustness`
- `lineage_signal`
- `mechanism_signal`
- `validation_proxy`
- `artifact_penalty`

The artifact penalty is subtracted; the other weighted components are added.
Weights are ranking policy, not certification thresholds.

## Search modes

| Mode | Preferred parent archive | Validation score trigger | Intent |
|---|---|---:|---|
| `frontier` | elite | `0.40` | explore high-scoring regimes |
| `outlier` | novelty | `0.34` | prefer unusual behavioral signatures |
| `robustness` | robustness | `0.28` | prefer stress-stable candidates |
| `promotion` | robustness | `0.24` | maximize pressure before keeping a winner |

The score trigger applies before the periodic cadence: a candidate at or above
the threshold is validated immediately. `validation.score_threshold` overrides
the mode value.

## Prefilter

The prefilter runs after the discovery artifact is saved but before a scored
record is added.

| Field | Default | Pass condition |
|---|---:|---|
| `min_steps` | `12` | executed steps at least this value |
| `min_activity` | `0.005` | final `activity` at least this value |
| `min_occupancy` | `0.01` | final `occupancy` at least this value |

Because the raw rollout is already saved, an attempted proposal can leave an
artifact directory while not appearing in the `evaluated` count.

## Search-space overrides

A substrate default search space contains four sections:

- `params`
- `rule_variants`
- `environment`
- `initial_conditions`

Experiment `search_space` values are deep-merged into that default. A partial
override is therefore valid for a registered substrate.

Supported entry types:

```yaml
search_space:
  params:
    mortality:
      type: float
      min: 0.0
      max: 0.1
  environment:
    grid_size:
      type: int
      min: 48
      max: 96
  rule_variants:
    mode:
      type: choice
      values: [dynamic, uniform]
      weights: [0.8, 0.2]
```

`int` bounds are inclusive. `float` samples uniformly within the bounds.
`choice` requires at least one value; optional weights must match the value
count and have a positive sum.

## Validation scheduling

| Field | Default | Meaning |
|---|---:|---|
| `interval` | `4` | validate every Nth zero-based proposal |
| `score_threshold` | mode-specific | validate any candidate reaching this score |
| `long_steps_multiplier` | `2` | base steps multiplied for the long-horizon run |
| `neighbor_samples` | `4` | number of nearby configurations tested |
| `holdout_steps` | base `steps` | rollout length for each held-out seed |
| `holdout_seed_offsets` | `[101, 202, 303]` | offsets added to each candidate seed |
| `holdout_seeds` | absent | optional explicit held-out seeds instead of offsets |
| `perturbations` | `[]` | substrate-specific mid-horizon shocks |
| `certification_policy` | `default-v1` | named hard-gate mapping |
| `artifact_root` | `runs/validation` | validation runner root; reruns are not persisted by default |

Setting `interval: 0` disables periodic validation, but candidates can still
validate through the score threshold. To suppress full validation in a smoke
test, use `interval: 0` and a deliberately unreachable `score_threshold`.

`holdout_seeds` must not contain the discovery seed and must contain at least
one distinct value. For search experiments, offsets are usually safer because
generated discovery seeds vary candidate by candidate.

An empty perturbation list produces no perturbation evidence. It is therefore
`not_evaluated` for that gate and cannot pass the default certification policy.

## Default certification policy

```yaml
validation:
  certification_policy:
    name: default-v1
    require_deterministic_replay: true
    max_replay_difference: 1.0e-9
    min_long_horizon_score: 0.70
    min_perturbation_score: 0.65
    min_neighborhood_score: 0.45
    min_holdout_score: 0.70
    min_promotion_score: 0.75
```

All numeric thresholds must lie in `[0, 1]`. Unknown policy fields are rejected
rather than ignored. Every required check must be evaluated and pass.

These thresholds are transparent starter heuristics. A domain policy should
have a new name, calibration evidence, and an untouched audit partition.

## Perturbation kinds in the built-in substrates

`alpha_alife` supports:

| Kind | Main parameter |
|---|---|
| `wipe_patch` | `size` |
| `nutrient_shock` | `delta` |
| `mortality_burst` | `rate` |
| `resource_drought` | `factor` |

`mutation_cells` supports:

| Kind | Main parameter |
|---|---|
| `wipe_patch` | `size` |
| `radiation` | `magnitude` |
| `charge_drop` | `factor` |
| `shuffle_patch` | `size` |

Unknown perturbation kinds raise an error. A custom substrate defines its own
vocabulary through `apply_perturbation`.

## Validation proxy

`validation_proxy` is an advanced, nonempty mapping that asks the runner to
perform extra replay, long-horizon, perturbation, neighborhood, and holdout
reruns for every prefilter-passing candidate. To affect ranking, also assign a
positive `objective_weights.validation_proxy`.

Supported overrides are:

- `artifact_root`
- `replay_steps`
- `long_steps`
- `perturbation_steps`
- `neighborhood_steps`
- `neighbor_samples`
- `frame_stride`
- `capture_state_every`
- `perturbations`
- `holdout_steps`
- `holdout_seeds`
- `holdout_seed_offsets`

The built-in default perturbations are Mutation Cells oriented. Always provide
a substrate-appropriate `perturbations` list when enabling this advanced path
for another substrate. Proxy values are ranking signals and never replace the
full certification decision.

## Bootstrap candidates

`bootstrap_candidates` accepts inline candidate mappings or paths to JSON/YAML
candidate records. A record may be the candidate itself or contain a top-level
`candidate` mapping, as winner records do.

```yaml
bootstrap_candidates:
  - path/to/candidate.json
  - substrate: alpha_alife
    search_mode: frontier
    seed: 17
    params: {}
    rule_variants: {}
    environment: {}
    initial_conditions: {}
```

The candidate substrate must match the experiment. Bootstrap candidates are
force-validated before generated proposals; their search mode is normalized to
the experiment mode.

## Flagship specifications

`flagship_template_example.yaml` is not a normal search experiment. Copy it,
replace the candidate with a real winner, and run:

```sh
python -m asal_m.analysis.validate_flagship asal_m/experiments/your_flagship.yaml
```

Template values are not published scientific claims. Revalidation is not an
untouched final audit unless its evidence was reserved before candidate and
policy selection.

## Hygiene

- Write generated runs under an ignored directory such as `runs/`.
- Prefer repository-relative paths.
- Do not commit host paths, secrets, unreviewed private artifacts, or large
  freezes.
- Publish the resolved experiment mapping, candidate seed, policy, and evidence
  partition with every numeric claim.

# Adding a substrate

ASAL-M keeps simulation mechanics separate from proposal, scoring, archives,
and certification. A substrate supplies the simulation; the workbench supplies
the evaluation workflow.

Version 0.1.3 uses an explicit in-package registry. Adding a substrate requires
a small source module, a default search space, a registry entry, an experiment,
and tests.

## 1. Create the package

A typical layout is:

```text
asal_m/substrates/my_substrate/
  __init__.py
  sim.py
  perturb.py       # optional separation
  metrics.py       # optional separation
  render.py        # optional separation
```

The file split is optional; the contract is not.

## 2. Implement the contract

```python
from typing import Any

import numpy as np


class MySubstrate:
    name = "my_substrate"

    def reset(self, config: dict[str, Any], seed: int) -> None:
        """Create a deterministic initial state from config and seed."""

    def step(self, n: int = 1) -> None:
        """Advance the simulation by n steps."""

    def render_frame(self) -> np.ndarray:
        """Return a consistent H×W×3 uint8-compatible image."""

    def get_state(self) -> dict[str, Any]:
        """Return enough state for exact restoration and final export."""

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore a state previously returned by get_state."""

    def extract_metrics(self) -> dict[str, float]:
        """Return finite scalar metrics for the current state."""

    def apply_perturbation(self, perturbation: dict[str, Any]) -> None:
        """Apply one declared domain shock; reject unknown kinds."""

    def is_extinct(self) -> bool:
        """Return whether the run should stop early."""
```

### Contract expectations

- `reset(config, seed)` must reproduce the same trajectory for the same inputs.
- `step(n)` and repeated `step()` calls must have consistent semantics.
- `render_frame()` should keep shape and channel layout stable across a run.
- `get_state()` should return a mapping whose values can be converted to NumPy
  arrays; `set_state()` must restore it without sharing mutable references.
- `extract_metrics()` should return finite scalar values. The built-in scoring
  and validation formulas expect `activity`, `occupancy`, and `diversity` for
  useful default behavior. Additional domain metrics are encouraged.
- `apply_perturbation()` owns the substrate-specific perturbation vocabulary.
  Raise `ValueError` for an unknown `kind` instead of silently doing nothing.
- `is_extinct()` should be cheap and deterministic.

The runner converts frames to `uint8` and scalar metrics to floats. Consistent
native output avoids surprising clipping or serialization.

## 3. Define a default search space

The registered search runner needs all four candidate sections, even if some
are empty:

```python
MY_SUBSTRATE_DEFAULT_SEARCH_SPACE = {
    "params": {
        "growth_rate": {"type": "float", "min": 0.01, "max": 0.25},
    },
    "rule_variants": {
        "update_mode": {
            "type": "choice",
            "values": ["local", "mixed"],
            "weights": [0.8, 0.2],
        },
    },
    "environment": {
        "grid_size": {"type": "int", "min": 48, "max": 96},
    },
    "initial_conditions": {
        "density": {"type": "float", "min": 0.05, "max": 0.35},
    },
}
```

Supported types are `float`, inclusive `int`, and `choice`. See
[EXPERIMENTS.md](EXPERIMENTS.md#search-space-overrides) for exact semantics.

## 4. Register it

Add an entry to `asal_m/substrates/__init__.py`:

```python
SUBSTRATE_REGISTRY = {
    # existing entries...
    "my_substrate": {
        "module": "asal_m.substrates.my_substrate.sim",
        "factory_name": "MySubstrate",
        "search_space_name": "MY_SUBSTRATE_DEFAULT_SEARCH_SPACE",
    },
}
```

`factory_name` may name a class or zero-argument factory. `search_space_name`
must name the default mapping in that module.

Registration has intentionally been explicit since version 0.1.2. There is no
dynamic entry-point/plugin discovery layer yet.

## 5. Define meaningful perturbations

Certification requires perturbation evidence under the default policy. Choose
shocks that represent real failure modes for the domain, for example:

```python
def apply_perturbation(self, perturbation: dict[str, Any]) -> None:
    kind = perturbation.get("kind")
    if kind == "damage_patch":
        size = float(perturbation.get("size", 0.15))
        # remove or damage a seeded region
    elif kind == "resource_drop":
        factor = float(perturbation.get("factor", 0.5))
        # reduce the relevant resource field
    else:
        raise ValueError(f"Unknown MySubstrate perturbation: {kind}")
```

The perturbation suite reruns the discovery seed, applies each shock halfway
through the horizon, and measures recovery. A nonempty list is required for
that gate to be evaluated.

## 6. Write an experiment

```yaml
name: my_first_search
seed: 1
substrate: my_substrate
search_mode: promotion
budget: 12
steps: 64
frame_stride: 4
capture_state_every: 12
artifact_root: runs

target_metrics:
  occupancy: 0.20
  diversity: 0.30

prefilter:
  min_steps: 12
  min_activity: 0.005
  min_occupancy: 0.01

validation:
  interval: 2
  long_steps_multiplier: 2
  neighbor_samples: 4
  holdout_seed_offsets: [101, 202, 303]
  perturbations:
    - kind: damage_patch
      size: 0.15
    - kind: resource_drop
      factor: 0.5
  certification_policy:
    name: my-substrate-demo-v1
    min_long_horizon_score: 0.70
    min_perturbation_score: 0.65
    min_neighborhood_score: 0.45
    min_holdout_score: 0.70
    min_promotion_score: 0.75
```

Run a small smoke search first:

```sh
python -m asal_m --experiment path/to/my_first_search.yaml --budget 2 --steps 24
```

Then use the intended budget and horizons for real evidence. Do not present a
reduced smoke protocol as a substantive validation result.

## 7. Add focused tests

At minimum, test:

1. same config and seed produce identical trajectories;
2. `get_state()` followed by `set_state()` preserves the next step;
3. metrics are finite and include the required common signals;
4. each declared perturbation changes state and remains deterministic;
5. unknown perturbations fail clearly;
6. the default search space samples within bounds;
7. a two-candidate search smoke writes a valid summary;
8. validation contains holdout, neighborhood, perturbation, and certification
   records.

Run the complete gate:

```sh
python tools/verify_public_docs.py
python -m ruff check asal_m tests examples tools
python -m pytest -q
```

## 8. Calibrate before making claims

The default certification thresholds demonstrate the mechanism; they are not
automatically appropriate for a new domain.

Before publishing a substrate result:

- define what each metric means;
- calibrate a named policy without looking at final audit evidence;
- freeze the candidate and policy;
- run a separately reserved audit partition;
- report failures and what was not tested.

Use the flagship template for out-of-loop revalidation:

```sh
python -m asal_m.analysis.validate_flagship path/to/your_flagship.yaml
```

Revalidation becomes a final audit only when its evidence was genuinely held
outside every earlier selection and calibration decision.

## Design rules

1. **Substrate isolation** — simulation modules do not import search or archive
   policy.
2. **Protocol over screenshots** — claims attach to configuration, seeds,
   thresholds, and evidence partitions.
3. **Averages do not certify** — every required gate passes independently.
4. **Unknown shocks fail loudly** — silent no-ops manufacture false evidence.
5. **Private freezes stay private** — publish only reviewed artifacts you have
   the right and intention to release.

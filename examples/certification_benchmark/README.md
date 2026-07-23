# Leakage-safe certification benchmark

This benchmark asks a narrow question:

> Does hard-gated certification select a regime that transfers better than the
> candidate with the highest single-rollout discovery score?

It uses three disjoint stages:

1. Generate a deterministic pool of 30 `mutation_cells` candidates and score one discovery rollout each.
2. Certify only the six highest discovery scores using replay, longer horizon, perturbation, neighborhood, and held-out-seed checks.
3. Freeze the raw winner and certification-selected winner, then audit both on 12 unseen seeds and stronger perturbations that played no role in selection.

The final audit score is:

```text
0.55 × unseen long-horizon score + 0.45 × strong perturbation score
```

An audit trial passes at `0.75`. Selection holdout seeds are derived from each
candidate and are disjoint from the 12 fixed audit seeds. Audit perturbations
are stronger than the selection suite and never enter candidate choice.

Regenerate from the repository root:

```sh
python -m pip install -c requirements-repro.txt -e .
python examples/certification_benchmark/regenerate.py
```

The command uses the core installation, overwrites the two checked-in outputs,
and can take a few minutes on CPU because it evaluates the complete pool,
shortlist, and audit. With the release constraints, both outputs regenerate
byte-identically across the documented Windows/Ubuntu matrix.

Outputs:

- `benchmark.json` — protocol, candidate pool, shortlist decisions, per-seed audit evidence, and comparison.
- `certification-comparison.png` — evidence-first summary graphic used in the main README.
- `fonts/` — checksum-verified DejaVu Sans 2.37 rendering inputs and license.

Scientific computation uses full precision. The public JSON representation is
canonicalized to 12 decimal places, and the image uses repository-bound fonts
plus a deterministic PNG encoder. See the
[reproducibility contract](../../docs/REPRODUCIBILITY.md).

The benchmark is a fixed, reproducible engineering demonstration on one bundled
substrate. It is not evidence of universal superiority across search systems or
scientific domains.

Fast integrity check without rerunning the benchmark:

```sh
python tools/verify_public_evidence.py
python -O tools/verify_public_evidence.py
```

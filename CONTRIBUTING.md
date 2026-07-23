# Contributing

ASAL-M welcomes focused fixes, documentation improvements, additional
substrates, validation methods, and reproducible protocol-scoped benchmarks.

## Development setup

```sh
python -m venv .venv
python -m pip install -U pip
python -m pip install -e ".[dev,analysis]"
```

Activate the virtual environment using the command appropriate for your shell.
Then run:

```sh
python tools/verify_public_docs.py
python tools/verify_public_evidence.py
python -m ruff check asal_m tests examples tools
python -m pytest -q
```

## Contribution expectations

- Keep substrates isolated from search, archive, and certification policy.
- Add or update tests for behavior changes.
- Keep seeded examples deterministic and disclose all evidence partitions.
- Treat aggregate scores as ranking signals, not substitutes for hard gates.
- Report missing evidence as unevaluated rather than manufacturing a zero-value
  experiment.
- Keep public artifacts small and free of secrets, absolute host paths, private
  datasets, and unrelated binaries.
- Update the user guide and field reference when public behavior changes.

New claims must identify substrate, seeds, budget, policy, thresholds, and what
was not tested. Universal optimization, life, consciousness, and scientific
proof claims are out of scope; see [CLAIM_BOUNDARY.md](CLAIM_BOUNDARY.md).

## Substrates and benchmarks

For a substrate, follow [docs/ADDING_A_SUBSTRATE.md](docs/ADDING_A_SUBSTRATE.md)
and include focused contract, determinism, perturbation, and search smoke tests.

For a benchmark, keep discovery/selection evidence separate from the final
audit. The audit must not influence candidate choice or policy calibration.
Commit the protocol and machine-readable evidence, not only a chart.

## Pull requests

Keep a pull request narrow. Explain:

1. the problem or protocol change;
2. the implementation;
3. verification commands and results;
4. compatibility or claim-boundary impact.

Contributions intentionally submitted to the project are accepted under the
Apache License 2.0 unless explicitly marked otherwise.

# Public demo postcard

This folder is intentionally small. It should contain only:

| File | Role |
|---|---|
| `mutation_cells_seed42.gif` | Fixed-seed simulation postcard animation |
| `benchmark.json` | Fixed-seed metrics + validation summary |
| `regenerate.py` | Reproduces the two assets above |
| `README.md` | This note |

No intermediate `runs/`, search dumps, or host paths belong here.

## Regenerate

From the **repository root**:

```sh
python -m pip install -c requirements-repro.txt -e .
python examples/public_demo/regenerate.py
```

Optional larger display scale (default 4 → 384×384 from a 96×96 grid):

```sh
python examples/public_demo/regenerate.py --scale 5
```

Intermediates are written to a temp directory and deleted. The postcard JSON is checked for absolute host path leakage before write.

The command requires only the core installation and overwrites the checked-in
GIF and JSON. With the default scale and release constraints, both files
regenerate byte-identically across the documented Windows/Ubuntu matrix.
Scientific computation uses full precision; only the public JSON
representation is canonicalized to 12 decimal places. See the
[reproducibility contract](../../docs/REPRODUCIBILITY.md).

This postcard demonstrates one simulation and its certification record. The
separate [certification benchmark](../certification_benchmark/README.md) contains
the partition-disjoint selection comparison used for the main project claim.

The current fixed postcard is honestly **rejected** by the default policy: it
survives replay, long horizon, perturbations, and held-out seeds, but does not
meet the neighborhood-stability floor. The aggregate score is retained for
ranking; it cannot override that failed gate.

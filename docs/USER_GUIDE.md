# User guide

This guide takes ASAL-M from a fresh checkout to an interpreted certification
result. For the complete YAML field reference, see
[EXPERIMENTS.md](EXPERIMENTS.md). For extension work, see
[ADDING_A_SUBSTRATE.md](ADDING_A_SUBSTRATE.md).

## 1. What ASAL-M does

ASAL-M searches parameterized simulations, scores their trajectories, and
subjects promising candidates to a hard-gated validation policy.

The normal search path is:

```text
candidate proposal
  -> discovery rollout
  -> prefilter and scoring
  -> elite / novelty / robustness archives
  -> validation when cadence or score threshold triggers
  -> certified or rejected decision
  -> role-specific winners in experiment_summary.json
```

Certification and final audit are deliberately different:

- **Certification** is built into validated search candidates. It uses replay,
  longer horizon, perturbations, nearby configurations, and held-out seeds.
- **Final audit** is a separately frozen evaluation on evidence that did not
  influence discovery, policy tuning, certification, or candidate selection.
  The bundled certification benchmark demonstrates this separation. A generic
  search does not invent an untouched audit set for you.

`certified` therefore means “passed the named ASAL-M policy.” It does not mean
scientifically proven, universally robust, or alive. Read
[CLAIM_BOUNDARY.md](../CLAIM_BOUNDARY.md) before publishing results.

## 2. Install

ASAL-M supports Python 3.10 and newer. A GPU and model API are not required.

From a checkout:

```sh
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or on Linux and macOS:

```sh
source .venv/bin/activate
```

Install the core workbench:

```sh
python -m pip install -U pip
python -m pip install -e .
```

For development and plotting:

```sh
python -m pip install -e ".[dev,analysis]"
```

The `analysis` extra installs Matplotlib. The other analysis commands use the
core dependencies only.

Verify the installation:

```sh
python -m asal_m --help
```

The installed `asal-m` command is equivalent to `python -m asal_m`. This guide
uses the module form because it works consistently across shells.

## 3. Run the first search

Run the promotion-mode Mutation Cells starter from the repository root:

```sh
python -m asal_m --experiment mut_cells_promotion --budget 6 --steps 48
```

`--experiment` accepts either a packaged starter name or a YAML path:

```sh
python -m asal_m --experiment asal_m/experiments/alpha_mainline.yaml --budget 4 --steps 32
```

`--budget` and `--steps` override the YAML for that invocation. The source YAML
is not modified.

The command prints archive counts and four winner roles:

- `mainline`: highest composite score;
- `novelty`: strongest novelty-oriented record;
- `robustness`: strongest stress-oriented record;
- `promotion`: certification state first (`certified`, then `rejected`, then not
  evaluated), highest aggregate promotion score next, and total score only as
  the final tie-breaker.

A candidate can fill more than one role. It is also normal for `evaluated` to
be smaller than `budget`: `budget` counts attempted proposals, while candidates
that fail the prefilter are excluded from the scored records.

## 4. Find the outputs

The default experiment directory is:

```text
runs/<experiment-name>/
```

It contains `experiment_summary.json` plus one directory per attempted
candidate. A candidate directory normally contains:

| File | Meaning |
|---|---|
| `candidate.json` | exact seed and simulation configuration |
| `summary.json` | terminal metrics and executed-step count |
| `metrics_trace.json` | metrics captured across the rollout |
| `frames.npz` | compressed rendered frames |
| `final_state.npz` | serialized final substrate state |
| `rollout.gif` | visual replay when Pillow can encode the frames |

`experiment_summary.json` is the experiment-level record. It contains:

- the resolved experiment mapping, including CLI overrides;
- attempted/scored archive and certification counts;
- the four winner records;
- each validated winner's policy, gate values, evaluation status, and failure
  codes.

Raw candidate artifacts are saved before the prefilter runs. This preserves
debug evidence, so a failed prefilter can still leave a candidate directory
even though it is absent from the `evaluated` count.

`runs/` is intentionally ignored by Git. Copy only small, reviewed evidence
into a public example folder when you mean to publish it.

## 5. Read a certification result

The CLI exposes three practical states:

| State | Meaning |
|---|---|
| `certified` | every required gate was evaluated and passed |
| `rejected` | at least one required gate failed or lacked evidence |
| `not-evaluated` | this winner did not receive the full validation suite |

Inside JSON, `validation.certification` contains:

- `status` and `passed`;
- the complete named `policy`;
- one record per check with value, operator, threshold, required/evaluated
  flags, and pass state;
- stable `failure_codes`, such as `perturbation_below_policy` or
  `neighborhood_not_evaluated`.

The aggregate `promotion_score` ranks candidates within the same certification
state. It cannot override a failed hard gate. For example, a candidate with
excellent holdout and replay scores is still rejected when its neighborhood
score is below policy.

The default thresholds are demo defaults, not scientific constants. Calibrate
a named policy for the domain before making substantive claims.

## 6. Summarize and export a run

Set a summary path first. The examples below use the default output of the
promotion starter:

```text
runs/mutation_cells_promotion/experiment_summary.json
```

Print counts and winner metrics:

```sh
python -m asal_m.analysis.summarize_run runs/mutation_cells_promotion/experiment_summary.json
```

Export the winner records to `winners.json`:

```sh
python -m asal_m.analysis.export_winners runs/mutation_cells_promotion/experiment_summary.json
```

Plot novelty versus robustness (requires the `analysis` extra):

```sh
python -m asal_m.analysis.plot_frontiers runs/mutation_cells_promotion/experiment_summary.json
```

Compare winners across several Mutation Cells searches:

```sh
python -m asal_m.analysis.compare_mutation_winners \
  runs/mutation_cells_mainline/experiment_summary.json \
  runs/mutation_cells_robust/experiment_summary.json \
  runs/mutation_cells_promotion/experiment_summary.json
```

Without explicit paths, the comparison command looks for those three default
locations. Generated comparison files go to `runs/mutation_cells_analysis/`
unless `--output-dir` overrides it.

Shareable JSON, Markdown, and resolved YAML pass through one public-output
boundary. Paths inside the working tree become POSIX-style relative paths;
outside-tree paths retain only their leaf name. Persisted timestamps are UTC.
This is a safety default, not permission to publish output without reviewing
it.

## 7. Freeze and revalidate a candidate

Copy `asal_m/experiments/flagship_template_example.yaml`, replace the candidate
mapping with a real winner, and keep the policy and evidence choices explicit.
Then run:

```sh
python -m asal_m.analysis.validate_flagship asal_m/experiments/your_flagship.yaml
```

Running the command without a positional path uses the packaged example, so it
also works from outside a source checkout:

```sh
python -m asal_m.analysis.validate_flagship
```

This writes a replay, resolved YAML, JSON report, and Markdown report. It is an
out-of-loop revalidation tool, not proof that the evidence is an untouched
final audit. To make that claim, freeze the candidate and policy first, then
evaluate a separately reserved seed/evidence partition exactly once. Use
[PROTOCOL_REGISTRATION.md](PROTOCOL_REGISTRATION.md) when the claim also needs
public evidence that reservation was prospective.

## 8. Run standalone substrates

The built-in simulations can run without the search layer:

```sh
python -m asal_m.substrates.alpha_alife.sim --steps 96 --seed 7
python -m asal_m.substrates.mutation_cells.sim --steps 96 --seed 5
```

Use `--output` to change the root destination; each command creates a
timestamped candidate subdirectory beneath it. These commands are useful for
checking rendering and substrate behavior; they do not certify a regime.

## 9. Reproduce the checked-in evidence

Install the exact direct dependencies used for the v0.1.1 release artifacts:

```sh
python -m pip install -c requirements-repro.txt -e .
```

Rebuild the fixed selection-versus-certification benchmark:

```sh
python examples/certification_benchmark/regenerate.py
```

Rebuild the standalone postcard:

```sh
python examples/public_demo/regenerate.py
```

Both scripts overwrite only their documented checked-in output files. Public
JSON is canonicalized only at serialization; scoring and certification use full
precision. The certification graphic uses checksum-verified bundled fonts and
a deterministic PNG encoder. Under the release constraints and Windows/Ubuntu
CI matrix, all four files regenerate byte-identically. The benchmark is
intentionally heavier than the postcard.

Verify the checked-in evidence and documentation without regenerating it:

```sh
python tools/verify_public_evidence.py
python -O tools/verify_public_evidence.py
python tools/verify_public_docs.py
python tools/verify_public_repository.py
```

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the exact hashes, rounding
boundary, font provenance, release matrix, and limitations of the byte
contract.

## 10. Inspect an external artifact collection

ASAL-M includes an optional read-only inventory command for a local artifact
tree:

```sh
python -m asal_m.analysis.inspect_artifacts --root path/to/ARTIFACTS
```

It reports file counts, extensions, and executable presence. It never executes
binaries found in the artifact tree. Absolute roots and machine/GPU information
are omitted by default. Local GPU model, driver, CUDA, memory, and utilization
can be recorded only by explicit opt-in:

```sh
python -m asal_m.analysis.inspect_artifacts \
  --root path/to/ARTIFACTS \
  --include-machine-details
```

This tool is not needed for normal ASAL-M runs.

## 11. Launch a local parallel campaign on Windows

The source distribution includes a PowerShell helper for launching several
experiment YAMLs:

```powershell
.\tools\launch_parallel_campaign.ps1 `
  -CampaignName comparison-01 `
  -Experiments @(
    "asal_m\experiments\alpha_mainline.yaml",
    "asal_m\experiments\mut_cells_promotion.yaml"
  )
```

It writes a resume-oriented manifest and log pointers under
`runs/campaigns/<name>/`. Persisted paths are repository-relative by default.
`-IncludeLocalPaths` explicitly opts into absolute local paths. The helper does
not resume, terminate, or interpret a run; completion still means an
`experiment_summary.json` exists for that experiment.

## 12. Add a substrate

The built-in runner currently uses an explicit in-package registry. A custom
substrate therefore needs:

1. an implementation of the substrate contract;
2. a default search space with all four candidate sections;
3. a registry entry;
4. domain perturbations and metrics;
5. a YAML experiment and focused tests.

Follow [ADDING_A_SUBSTRATE.md](ADDING_A_SUBSTRATE.md) for the complete process.

## 13. Troubleshooting

### `Experiment not found`

Use a packaged name such as `alpha_mainline`, or provide a path that exists
from the current working directory.

### `Unknown substrate`

The YAML `substrate` must match an entry in
`asal_m/substrates/__init__.py`. Registration is explicit in version 0.1.1.

### The evaluated count is below the budget

Some proposals failed `prefilter`. Inspect their candidate artifact directories
and lower a prefilter only when the domain justifies it.

### Everything is rejected

Rejection is a valid result, not a runtime failure. Read `failure_codes`. Empty
perturbations or an empty neighborhood search space are missing evidence under
the default policy and cannot certify.

### `No module named matplotlib`

Install the analysis extra:

```sh
python -m pip install -e ".[analysis]"
```

### A run is slow

Validation performs multiple simulation reruns. Reduce `budget`, `steps`,
`neighbor_samples`, or validation cadence for development smoke tests. Do not
publish those reduced settings as if they were the stronger protocol.

### Disk use grows quickly

Every attempted proposal saves frames and final state before prefiltering.
Archive or remove old ignored `runs/` directories deliberately; do not commit
them by accident.

## 14. Safe result reporting

When publishing a result, include:

- ASAL-M version or commit;
- substrate and experiment name;
- candidate seed and search budget;
- discovery, selection, certification, and audit evidence partitions;
- policy name and thresholds;
- failure codes or pass status;
- what was not tested.

Never include credentials, absolute host paths, private artifact collections,
or unreviewed multi-gigabyte freezes in a public report.

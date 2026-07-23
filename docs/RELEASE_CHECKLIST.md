# Release checklist

This is the maintainer checklist for a public ASAL-M release. It prepares a
release; it does not authorize a commit, push, tag, or package upload.

## Scope and claims

- [ ] Version and release scope are explicit.
- [ ] README result numbers match `examples/certification_benchmark/benchmark.json`.
- [ ] Discovery/certification evidence is disjoint from the final audit.
- [ ] Claims stay within [CLAIM_BOUNDARY.md](../CLAIM_BOUNDARY.md).
- [ ] `AUTHORS.md`, `NOTICE`, and license metadata are current.

## Public surface

- [ ] `vendor/`, `runs/`, local artwork, backups, and machine-local files are
  excluded.
- [ ] No credentials, tokens, personal email addresses, private paths, internal
  workspace names, private filenames, prompts, conversations, raw advisor
  material, or private artifacts are present.
- [ ] All generated evidence intended for publication is small, reviewed, and
  reproducible.
- [ ] The exact staged file list is reviewed before commit.
- [ ] Author and committer metadata use the maintainer's GitHub noreply address.
- [ ] The candidate history contains only deliberate public commits and refs.

## Fast verification

```sh
python tools/verify_public_docs.py
python tools/verify_public_evidence.py
python -O tools/verify_public_evidence.py
python -m ruff check asal_m tests examples tools
python -m pytest -q
```

## Reproducibility verification

Install the release constraints, then run the same commands enforced by the
Windows/Ubuntu reproducibility matrix. These commands overwrite the checked-in
example outputs. The final verifier checks canonical JSON, semantic invariants,
font assets, image structure, and the four release SHA-256 digests.

```sh
python -m pip install -c requirements-repro.txt -e .
python examples/certification_benchmark/regenerate.py
python examples/public_demo/regenerate.py
python tools/verify_public_evidence.py
python -O tools/verify_public_evidence.py
```

- [ ] Full-precision scientific computation remains separate from 12-decimal
  public JSON serialization.
- [ ] `requirements-repro.txt` matches the release matrix.
- [ ] Bundled font files match their documented digests and license.
- [ ] Regeneration leaves all four checked-in artifact hashes unchanged.
- [ ] Normal and optimized Python accept the clean evidence and reject the
  adversarial verifier tests.

## Package verification

```sh
python -m build
```

Confirm that:

- the wheel contains the packaged experiment YAMLs, `LICENSE`, and `NOTICE`;
- the source distribution contains the public docs, examples, tests, and tools;
- the source distribution contains the reproduction constraints, release fonts,
  and DejaVu license;
- neither archive contains `vendor/`, `runs/`, secrets, or host paths;
- the wheel imports and `python -m asal_m --help` works from a temporary
  directory outside the checkout.

## Publication

- [ ] Run the public-repository safety report before staging.
- [ ] Initialize Git only inside the intended project directory, if needed.
- [ ] Stage the approved file list deliberately; do not begin with a broad add.
- [ ] Review the staged diff and public repository URL.
- [ ] Inspect author and committer metadata on the exact commit to be pushed.
- [ ] Push `main`, wait for CI to pass, then create the annotated version tag.
- [ ] Create and inspect the corresponding GitHub Release.
- [ ] Commit, push, tag, release, or publish only after explicit maintainer
  approval.

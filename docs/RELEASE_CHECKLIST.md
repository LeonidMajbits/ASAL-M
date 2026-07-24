# Release checklist

This is the maintainer checklist for a public ASAL-M release. It prepares a
release; it does not authorize a commit, push, tag, or package upload.

## Scope and claims

- [ ] Version and release scope are explicit.
- [ ] README result numbers match `examples/certification_benchmark/benchmark.json`.
- [ ] Discovery/certification evidence is disjoint from the final audit.
- [ ] A prospective-reservation claim is made only when
  [PROTOCOL_REGISTRATION.md](PROTOCOL_REGISTRATION.md) was followed before
  discovery.
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
- [ ] The exact staged file list and staged blob bytes are reviewed before
  commit.
- [ ] Author and committer metadata use the maintainer's GitHub noreply address.
- [ ] Every reachable historical blob and path, commit message, annotated-tag
  message, identity, and public ref is deliberate or explicitly baselined.
- [ ] The exact index, divergent worktree content, reachable history, tags, and
  every built archive pass
  `tools/verify_public_repository.py`.

## Fast verification

```sh
python tools/verify_public_docs.py
python tools/verify_public_repository.py
python tools/verify_public_evidence.py
python -O tools/verify_public_evidence.py
python -m ruff check asal_m tests examples tools
python -m ruff format --check asal_m tests examples tools
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
python tools/build_sbom.py --help
python tools/build_release_assets.py
python tools/build_release_assets.py --verify
python tools/verify_public_repository.py --archives dist --release-files dist
```

Confirm that:

- the wheel contains the packaged experiment YAMLs, `LICENSE`, and `NOTICE`;
- the source distribution contains the public docs, examples, tests, and tools;
- the source distribution includes the PowerShell campaign launcher;
- the source distribution contains the reproduction constraints, release fonts,
  and DejaVu license;
- neither archive contains `vendor/`, `runs/`, secrets, or host paths;
- the wheel imports and `python -m asal_m --help` works from a temporary
  directory outside the checkout;
- the installed wheel can run the default flagship validator outside the
  checkout with small positive step overrides;
- the SPDX 2.3 SBOM binds the exact wheel digest and resolved runtime
  dependencies;
- `SHA256SUMS` matches the exact wheel, source distribution, SBOM, public
  signing key, and allowed-signers policy.

## Publication

- [ ] Run the public-repository safety report before staging.
- [ ] Initialize Git only inside the intended project directory, if needed.
- [ ] Stage the approved file list deliberately; do not begin with a broad add.
- [ ] Review the staged diff and public repository URL.
- [ ] Inspect author and committer metadata on the exact commit to be pushed.
- [ ] Require CI on the protected default branch before merge or release.
- [ ] Sign the release commit with the dedicated registered SSH signing key.
- [ ] Merge only the signed reviewed commit, wait for exact-main CI, then
  create and verify the signed annotated version tag.
- [ ] Confirm the version tag exactly matches `pyproject.toml`.
- [ ] Enable immutable future Releases before creating the release draft.
- [ ] Push the tag and require the `release-artifacts` workflow to build the
  wheel, source distribution, SPDX SBOM, checksums, provenance attestation,
  and SBOM attestation.
- [ ] Download the exact workflow outputs and verify both GitHub attestations.
- [ ] Sign `SHA256SUMS` locally with the dedicated release key; verify
  `SHA256SUMS.sig` against `docs/keys/allowed_signers`.
- [ ] Create the GitHub Release as a draft, attach the wheel, source
  distribution, SBOM, public signing key, allowed-signers policy,
  `SHA256SUMS`, and `SHA256SUMS.sig`, then publish once.
- [ ] Verify the resulting immutable Release and every asset with
  `gh release verify` and `gh release verify-asset`.
- [ ] Enable private vulnerability reporting, secret scanning, push protection,
  Dependabot security updates, read-only workflow tokens, and GitHub-owned
  Actions.
- [ ] Confirm active branch and tag rulesets block deletion, force pushes,
  unsigned commits, direct default-branch updates, and version-tag movement.
- [ ] Delete merged release branches after the final release audit.
- [ ] Set repository description, homepage, and topics deliberately.
- [ ] Publish to PyPI only as a separate, explicitly authorized action after
  testing the exact distribution files.
- [ ] Commit, push, tag, release, or publish only after explicit maintainer
  approval.

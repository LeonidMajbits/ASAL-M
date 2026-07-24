# Release integrity

ASAL-M v0.1.2 makes the release boundary independently inspectable. This
document distinguishes repository policy, cryptographic identity, build
provenance, artifact contents, and GitHub's release controls.

## Repository scanner

`tools/verify_public_repository.py` fails closed across four surfaces:

1. The prospective commit surface is enumerated from the Git index plus
   untracked, non-ignored files. Tracked bytes are read from their exact staged
   blob objects, not substituted from the worktree. A divergent tracked
   worktree copy is scanned as an additional pre-stage safeguard. Unmerged and
   intent-to-add index entries fail.
2. Every reachable commit message, historical path, and unique historical blob
   under all refs and `HEAD` is scanned. Author and committer identities remain
   restricted to the maintainer's GitHub noreply address.
3. Every annotated-tag message and tagger identity is scanned.
4. Every text payload and path in the wheel and source distribution is scanned.

The decoder recognizes UTF-8 with or without a byte-order mark, UTF-16
little-endian and big-endian text, and UTF-32 byte-order marks. High-confidence
provider-token shapes, private-key blocks, assigned secret values, personal
email addresses, host paths, forbidden public paths, and digest-identified
workspace labels are rejected.

The scanner is a release gate, not a claim that regular expressions can prove
the absence of every possible secret. Human diff, manifest, archive, and
release-asset review remain required.

## Historical disclosure boundary

Five exact v0.1.1-era blob IDs contain the three non-sensitive workspace labels
that the old verifier embedded as fixtures. Fifteen exact historical blobs
contain only synthetic host-path fixtures or the regular expressions that
detect them. Rewriting published history to erase those fixtures would
invalidate existing commit and tag identities, so v0.1.2 removes the labels
and file-wide fixture exemptions from the current tree and records only those
object IDs as narrow historical baselines.

The label baseline suppresses only the internal-label finding; the host-fixture
baseline suppresses only the absolute-host-path finding. The same blobs still
fail for every other credential, personal email, forbidden filename, or secret
finding. No private path, source, prompt, conversation, credential, or research
content is included in either baseline.

## Version lineage and immutability

v0.1.0 and v0.1.1 were published before GitHub release immutability was
enabled. They are preserved by maintainer policy and protected tag rules, but
GitHub cannot retroactively grant them an immutable release attestation.

v0.1.2 is the first ASAL-M Release published after repository-level immutable
releases were enabled. Its tag and assets become locked when the prepared draft
is published, and GitHub generates a release attestation binding the tag,
commit, and assets.

## Signed identity

The v0.1.2 commit, annotated tag, and `SHA256SUMS` use the dedicated public key
in [`keys/asal-m-release-signing.pub`](keys/asal-m-release-signing.pub). The
private key is not stored in this repository or in a GitHub Actions secret.
Its OpenSSH SHA-256 fingerprint is
`SHA256:AcVmWdXtxjOJagwIlL635w7WdQzOvHK3d144G0HC6ng`.

Configure Git's allowed signers and verify the commit and tag:

```sh
git config gpg.ssh.allowedSignersFile docs/keys/allowed_signers
git verify-commit v0.1.2^{}
git verify-tag v0.1.2
```

Verify the detached checksum signature:

```sh
ssh-keygen -Y verify \
  -f allowed_signers \
  -I asal-m-release \
  -n file \
  -s SHA256SUMS.sig < SHA256SUMS
```

Then verify the artifact bytes:

```sh
python tools/build_release_assets.py --dist . --verify
```

## Build provenance and SBOM

The tag-triggered `release-artifacts` workflow:

- checks out full history without persisted credentials;
- requires the version tag to match `pyproject.toml` exactly;
- builds and scans the wheel and source distribution;
- installs the exact wheel in a clean environment under the certified direct
  dependency constraints;
- generates a deterministic SPDX 2.3 JSON SBOM for the wheel and its resolved
  runtime dependencies;
- generates `SHA256SUMS`;
- includes the public signing key and allowed-signers policy in that checksum
  manifest for offline verification;
- creates GitHub/Sigstore build-provenance attestations for every checksummed
  artifact;
- creates an SBOM attestation binding the SPDX document to the wheel; and
- uploads the exact attested files for controlled Release publication.

Verify a downloaded artifact's workflow provenance:

```sh
gh attestation verify asal_m-0.1.2-py3-none-any.whl \
  --repo LeonidMajbits/ASAL-M
```

Verify GitHub's immutable Release and an exact downloaded asset:

```sh
gh release verify v0.1.2 --repo LeonidMajbits/ASAL-M
gh release verify-asset v0.1.2 asal_m-0.1.2-py3-none-any.whl \
  --repo LeonidMajbits/ASAL-M
```

An attestation binds identity and provenance; it does not assert that the
software is vulnerability-free or scientifically correct.

## Repository controls

After v0.1.2 publication:

- the active `main` ruleset blocks deletion and force pushes;
- updates require a successful package gate on the exact SHA, linear history,
  and GitHub-verified commit signatures;
- the release workflow reviews that exact SHA in a pull request before a
  signature-preserving fast-forward;
- version tags are protected from deletion and movement;
- future Releases are immutable;
- private vulnerability reporting is enabled; and
- secret scanning, push protection, Dependabot security updates,
  GitHub-owned-only Actions, and read-only default workflow permissions remain
  enabled.

# Changelog

All notable public changes are documented here.

## 0.1.4

- Scan UTF-8 text containing isolated NUL bytes instead of treating any NUL as
  proof that the payload is binary.
- Inspect every tar member name, symlink target, and hardlink target; reject
  unsafe link paths and unsupported special-file members instead of silently
  skipping them.
- Sanitize embedded Linux paths rooted at `/root`, `/workspace`, and `/opt`,
  and preserve formatting while redacting paths terminated by newlines or
  Markdown table boundaries.
- Remove the line-scoped host-fixture annotation escape. Current fixtures are
  assembled without literal host paths, while immutable historical fixtures
  remain acknowledged only by exact blob object ID.
- Keep the synthetic secret fixture effective at runtime without retaining a
  credential-shaped literal in the current source tree or source distribution.
- Correct the immutable v0.1.3 release-note test counts: the final v0.1.3 tree
  contains 140 collected tests. The published 133/132 figures recorded
  pre-final local runs and remain unchanged because the Release is immutable.

## 0.1.3

- Preserve root dotfile names during path normalization so forbidden files such
  as `.env` and `.git/config` cannot bypass prospective or archive scans.
- Detect BOM-less UTF-16 and UTF-32 text conservatively before permissive
  UTF-8 decoding, while keeping control-heavy binary payloads out of the text
  scanner.
- Sanitize unquoted, space-containing directory and extensionless host paths
  without truncating valid path components that contain conjunctions.
- Require the exact installed subject, every direct dependency package, its
  version and purl, and the complete expected relationship graph when locally
  verifying an SPDX SBOM.
- Validate release SBOMs independently with the pinned official SPDX tools in
  addition to ASAL-M's release-specific completeness checks.
- Resolve the existing static-analysis findings and make zero-error mypy
  analysis a required CI dependency of the protected `Package` gate.
- Baseline the one exact historical synthetic fixture fingerprint so standard
  Gitleaks remains strict while reporting no known false positive.

## 0.1.2

- Read prospective tracked content from exact staged Git blobs and additionally
  scan divergent tracked worktree content.
- Scan every reachable historical blob and path, commit message, annotated-tag
  message, and existing noreply identity.
- Decode UTF-16/UTF-32 text and detect common GitHub-token and AWS access-key
  shapes without publishing private workspace labels in scanner source.
- Remove the old internal-label fixtures from the current tree while narrowly
  documenting their immutable historical blob IDs.
- Replace file-wide host-fixture scan exemptions with explicit line-scoped
  annotations and exact historical-blob baselines.
- Sanitize mapping keys and quoted or space-containing embedded paths, with
  collision detection after key redaction.
- Reject all real-number work limits, including integral floats, rather than
  truncating them to integers.
- Add a deterministic SPDX 2.3 SBOM, GitHub/Sigstore artifact provenance and
  SBOM attestations, a dedicated SSH release-signing key, detached checksum
  signatures, and exact verification instructions.
- Reject release tags whose version does not exactly match package metadata.
- Correct v0.1.0 and v0.1.1 release-boundary wording; protect `main` and version
  tags; enable private vulnerability reporting and immutable future Releases.

## 0.1.1

- Centralize safe serialization for shareable JSON, Markdown, and YAML output.
- Omit machine/GPU inventory by default and make local details explicit opt-in.
- Load the default flagship specification from installed package resources.
- Prevent artifact-directory collisions and reject non-positive work limits.
- Make PowerShell campaign manifests path-safe by default and package the
  launcher in the source distribution.
- Add prospective protocol commitments, whole-repository/archive privacy
  scanning, release checksums, citation metadata, and expanded regressions.
- Keep real-history identity checks strict while recognizing GitHub's
  ephemeral two-parent pull-request test merge.
- Pin the release-branch formatter and declare a stable baseline lint policy.
- Narrow the bundled benchmark label from `leakage-safe` to the
  provenance-supported `partition-disjoint` claim.

## 0.1.0

- Initial public release of the ASAL-M certification workbench.
- Add two deterministic reference substrates, search modes, archives,
  hard-gated validation, fixed public evidence, packaging, documentation, and
  cross-platform reproducibility CI.

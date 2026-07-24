# Security policy

## Supported versions

ASAL-M is alpha research software. Security fixes target the latest public
release and the default branch; older snapshots may not receive patches.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository when it is
available. Do not publish exploit details, credentials, private artifact paths,
or sensitive datasets in a public issue.

If private reporting is unavailable, open a minimal issue stating that you
have a security report and request a private contact channel. Include no
exploit details in that issue.

Useful private reports include affected version/commit, environment,
reproduction steps, impact, and a minimal proof of concept.

## Security model

- Experiment YAML is parsed with safe YAML loading, but configurations should
  still be treated as untrusted input and reviewed before expensive runs.
- ASAL-M reads and writes local experiment artifacts. Run it with normal user
  privileges and use a dedicated output directory for untrusted workloads.
- The optional artifact inventory is read-only and never auto-executes binaries.
- Shareable reports redact absolute host roots and omit machine/GPU inventory
  by default. Local machine details require explicit opt-in.
- Repository verification scans exact staged blobs, divergent tracked
  worktree content, untracked public files, every reachable historical blob
  and path, commit and annotated-tag messages, noreply identities, the wheel,
  and source distribution for common secret, personal-email, internal-name,
  and host-path leakage. Tar link names and targets are scanned, and
  unsupported special-file members fail closed. Root dotfiles retain their
  leading dot during path checks, and the text scanner recognizes UTF-8 with
  isolated NUL bytes plus BOM-marked and high-confidence BOM-less
  UTF-16/UTF-32. It is not a substitute for reviewing the exact public diff or
  for a dedicated secret-scanning service.
- `.gitleaksignore` acknowledges one exact published fingerprint for a
  historical synthetic scanner test value. The current source and source
  distribution do not contain that credential-shaped literal. The baseline
  does not suppress that commit, file, rule, or any future finding broadly.

Release signing, SBOM, provenance, historical baseline, and immutable-release
boundaries are documented in
[RELEASE_INTEGRITY.md](docs/RELEASE_INTEGRITY.md).

Scientific disagreements, benchmark limitations, and claim-boundary concerns
are important project issues but are not security vulnerabilities.

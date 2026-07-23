# Claim boundary

Part of the public contract for ASAL-M.

## What this software is

ASAL-M is a **held-out certification and stress-testing workbench** for
discovered regimes on ALife-style and other simulation substrates.

It helps an operator:

1. Propose candidate configurations for a registered substrate.
2. Filter and score short trajectories.
3. Maintain elite / novelty / robustness archives.
4. Stress-test promising hits with replay, long-horizon, same-seed perturbation, neighborhood, and **held-out seed** checks.
5. Apply explicit hard gates so an average score cannot hide a failed or unevaluated dimension.

Results are **scoped metrics under named protocols**. They are not metaphysical proofs.
The bundled scores and default certification thresholds are explicit engineering
heuristics, not externally calibrated scientific instruments. `certified` means
"passed the named ASAL-M policy," not "scientifically proven." Stronger claims
require independent baselines, statistical analysis, and domain review beyond
this repository.

Certification is not automatically a final audit. Certification evidence may
participate in candidate selection. A final audit must be reserved from
discovery, policy calibration, certification, and selection until the candidate
and policy are frozen. The bundled benchmark's program and output demonstrate
disjoint discovery, certification, and audit partitions under one fixed
protocol. They were first published together, so public repository provenance
does not independently prove that a human prospectively reserved the audit.
Generic searches leave audit ownership to the operator. Use
[protocol registration](docs/PROTOCOL_REGISTRATION.md) when a future claim
requires a timestamped pre-discovery commitment and later reveal.

## Table and tools vs blueprint

- **Shipped contribution:** the workbench (contract, reference proposal loop, scoring, archives, certification, starter demos).
- **User contribution:** guest substrates, freezes, and claims about *their* regimes.
- Demo substrates exist so the table is not empty. They are not a claim that every regime found on them is universally optimal or “alive.”

## Allowed claims

You may say ASAL-M:

- implements protocol-scoped search, stress testing, and held-out certification over independent substrates
- separates simulation from search / scoring / archives / validation
- supports composite scoring and multi-archive promotion pressure
- provides YAML-driven experiments and analysis utilities
- can surface regimes that survive a **stated** validation suite on the metrics of that suite
- distinguishes ranked scores from explicit pass/reject certification decisions
- ships a fixed benchmark whose program keeps discovery, certification, and audit inputs disjoint

## Forbidden or misleading claims

Do **not** present this repository as:

- proof of artificial life, consciousness, sentience, or personhood
- a digital species or legal/biological life system
- quantum advantage
- a universal optimizer that “beats everything” without scoped tasks, seeds, budgets, and metrics
- proof of prospective audit reservation unless an earlier public commitment,
  candidate/policy freeze, and exact reveal are available
- a dump of private third-party commercial packaging or unrelated monorepo systems

If you publish numbers, always include substrate, experiment identity, seeds/budget, validation definition, and what was not tested.

## Artifacts and freezes

Optional local freezes are **not** required to run the workbench and are **not** shipped here by default.

Absence of freezes does not invalidate the engine.
Presence of a freeze in a private lab does not automatically make a public claim true.

## Related ASAL work

[Sakana AI's ASAL](https://github.com/SakanaAI/asal) is related upstream research
on foundation-model-guided artificial-life search. ASAL-M is independent, focuses
on downstream certification, and does not ship the upstream source tree. See
`NOTICE` for the pinned development reference.

## How to talk about results

**Good:** “Under policy *P*, candidate *X* passed every declared gate and then
scored *Y* on a partition-disjoint audit that did not feed the program's
discovery or certification stages.”

**Stronger, only with registration:** “The audit protocol was prospectively
committed at reference *R* and remained reserved until the candidate and policy
freeze at reference *F*.”

**Bad:** “ASAL-M discovered life.” / “This proves digital organisms.”

When in doubt: **narrow the claim to the protocol that was run.**

Operational guidance: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

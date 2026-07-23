# Protocol registration

ASAL-M can prove that a fixed program used disjoint discovery, certification,
and audit partitions. A repository published with code and results together
cannot, by itself, prove that the audit protocol was prospectively reserved
before a human saw the outcome.

Use this procedure when a future result needs that stronger provenance claim.

## Two public freezes

### 1. Pre-discovery audit commitment

Before discovery begins:

1. Write the exact audit protocol, including seed-generation rules, metrics,
   perturbations, pass thresholds, retry policy, and software revision.
2. Include a high-entropy random nonce if hidden audit details could otherwise
   be guessed from their hash.
3. Create a commitment to the exact files:

   ```sh
   python tools/protocol_commitment.py create \
     --input audit_protocol=private/audit_protocol.yaml \
     --input environment=private/environment.lock \
     --output registration/pre_discovery_commitment.json
   ```

4. Publish the commitment in a timestamped, immutable location. A signed Git
   tag or release is preferable. Do not publish the hidden audit inputs yet.

The commitment contains only roles, leaf filenames, byte counts, hashes, and a
UTC creation time. It does not contain absolute host paths.

### 2. Candidate and policy freeze

After discovery and calibration, but before reading audit outcomes:

1. Freeze the selected candidate, named certification policy, selection
   evidence, code revision, and dependency lock.
2. Create and publish a second commitment to those exact bytes.
3. Record that no audit result has been read and state how interrupted or
   failed audit execution will be handled.

## Execute and reveal

Run the registered audit exactly as declared. Preserve raw evidence, exit
status, and the complete environment identity. Then publish:

- the previously hidden protocol inputs and nonce;
- the candidate/policy freeze;
- the raw audit evidence and derived report;
- both commitment files and their immutable publication references;
- any deviation, interruption, rerun, or excluded trial.

Verify the reveal:

```sh
python tools/protocol_commitment.py verify \
  registration/pre_discovery_commitment.json \
  --input audit_protocol=private/audit_protocol.yaml \
  --input environment=private/environment.lock
```

The verifier fails if a role, filename, byte count, or SHA-256 digest differs.

## Claim language

Without prospective registration, say:

> The fixed benchmark uses partition-disjoint discovery, certification, and
> audit stages.

With a publicly timestamped commitment, candidate/policy freeze, exact reveal,
and documented execution history, it is reasonable to add:

> The audit protocol was prospectively committed and remained reserved until
> candidate and policy freeze.

Registration strengthens provenance. It does not replace statistical power,
independent replication, domain review, or an honest report of what was not
tested.

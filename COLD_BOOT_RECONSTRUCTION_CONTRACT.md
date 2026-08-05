# COLD_BOOT_RECONSTRUCTION_CONTRACT.md

**Status:** Draft specification, v1. Precedes and constrains
`test_cold_boot_reconstruction.py` — no reconstruction code should be
written against a claim not listed here as SHALL, and any test
asserting a SHALL NOT claim is itself a contract violation.

**Scope:** applies to a verifier operating on three persisted
append-only logs — `RegistrationAuditLog`, `DecisionLog`,
`ExecutionAuditLog` — with no live runtime objects, no in-memory state
from any prior process, per the isolation boundary already proven in
`test_verifier_runtime_isolation.py`.

**Core principle:** the verifier is evidence-driven, not
inference-driven. It reconstructs only properties explicitly
represented by persisted artifacts, and refuses to infer properties
not uniquely determined by those artifacts. This single sentence
explains nearly every SHALL and SHALL NOT below, and is the direct
reason Gap 1b exists: reset-generation identity is not uniquely
determined by anything currently persisted, so the verifier does not
claim to determine it.

**Purpose of this document:** this document functions as a proof
obligation. Every SHALL requires supporting evidence — a named,
passing test. Every SHALL NOT requires either supporting evidence of
a demonstrated limitation, or an information-theoretic argument for
why the claim cannot hold given what the schema persists. Where a
term isn't precisely defined yet, it's listed as deferred rather than
smuggled into a SHALL clause.

---

## The verifier SHALL reconstruct:

1. **Module registration history** — every registration attempt,
   success and failure, in append order, per
   `ModuleRegistrationAttemptRecord`.
   Evidence: `test_registration_audit_log_append.py`.

2. **Authorization history** — every authorization decision reaching
   the boundary, allowed and denied, in append order, per
   `DecisionRecord`.
   Evidence: `test_decision_record_log_append.py`.

3. **Execution ordering** — reconstruct and verify per-module
   `sequence_id` monotonicity within the decision log and within the
   audit log, independently.
   Evidence: `causal_history_verifier.py` Check 2,
   `test_causal_history_verifier.py`.

4. **The two specific persisted causal relationships the current
   schema represents:**
   - decision→audit ancestry (every audit record has exactly one
     preceding allowed decision record) —
     `causal_history_verifier.py` Check 1
   - module identity cross-reference (every `module_id` in the
     decision/audit logs has a successful registration attempt on
     record) — `causal_history_verifier.py` Check 3

   This is explicitly **not** a general causal graph. No other
   cross-artifact relationship is currently verified, and none should
   be assumed to exist.

5. **Hash consistency between persisted artifacts and their published
   deterministic derivation algorithm** — recomputing and verifying a
   stored hash against what the same published algorithm derives from
   the stored fields (analogous to recomputing and verifying a
   SHA-256 digest, which requires no second independent SHA-256
   implementation).

   **Implementation constraint, not just a wording note:** "the same
   published algorithm" means the verifier MUST recompute hashes by
   constructing the actual record classes
   (`ModuleRegistrationAttemptRecord`, `DecisionRecord`,
   `ExecutionAuditRecord`) and reading the hash their own
   `__post_init__` derives — never a separately reimplemented hash
   computation. The existing persistence tests prove recomputation
   works specifically via this path (`record_from_json` constructs a
   real instance of the record class, triggering its own derivation);
   they do NOT cover, and provide no evidence for, any independently
   reimplemented hash logic a verifier might otherwise be tempted to
   write for performance. A verifier that reimplements hash derivation
   separately from the record classes falls outside what is proven
   here, regardless of how carefully that reimplementation is written.

   - Already fully proven, under the above constraint, for
     `ModuleRegistrationAttemptRecord.attempt_hash`,
     `DecisionRecord.record_hash`, and
     `ExecutionAuditRecord.audit_hash`, via the tampering tests in
     each record type's persistence test file.
   - **Not yet available** for `KernelStateEnvelope.state_hash` — this
     capability is contingent on Gap 1 closing
     (`execution_kernel_state.py`'s derivation being incorporated into
     the verifier, via the same class-construction path described
     above). Until then, `state_hash` consistency is unverified by any
     reconstruction code.

---

## The verifier SHALL NOT claim to:

1. **Reconstruct RAM state, transient scheduler state, or discarded
   queues** — none of these are persisted anywhere in the current
   schema; there is nothing on disk to reconstruct them from.

2. **Detect or reconstruct administrative reset generations.**
   Experimentally confirmed indistinguishable from fresh execution
   histories under the current persisted schema: `state_hash`,
   `decision_hash`, and `record_hash` all collide across a reset when
   other fields (module, lifecycle state, policy, capabilities) match.
   `ExecutionPolicyState.observed_invocation_count` genuinely differs
   across a reset but is excluded from every persisted hash and never
   reaches `DecisionRecord` as a field at all.
   **This limitation is information-theoretic, not
   implementation-specific: the schema contains zero bits of
   reset-generation information for any algorithm, however clever, to
   recover.** No amount of verifier sophistication can extract a
   distinction the persisted data does not encode.
   Evidence: `test_reset_epoch_observability.py` (Gap 1b).

3. **Reconstruct policy counters that were never persisted** —
   `ExecutionPolicyState.invocation_counts` exists only in memory; no
   log in the current schema captures it.

4. **Prove that the original live runtime computed any hash correctly
   at execution time.** The verifier can only confirm that a persisted
   artifact is *consistent with* the published deterministic
   derivation algorithm (see SHALL item 5) — never a claim about
   whether that algorithm executed correctly in the original process,
   since no independent second implementation exists to check against.

5. **Rely on any hash in this schema as a chain that survives an
   administrative reset** — including `ExecutionAuditRecord.audit_hash`'s
   incorporation of `prior_state_hash`. That incorporation is a
   reference, not an independent guarantee: since `prior_state_hash`
   itself collides across a reset (per SHALL NOT item 2), the
   reference carries no reset-disambiguating information downstream.
   Inclusion of ambiguous information does not remove the ambiguity.
   Any apparent distinguishability between two colliding-snapshot
   records observed in testing came only from incidental frame-content
   differences (`input_hash` / `output_hash`), never from any chaining
   property of the hash itself.

---

## Explicitly undefined, deferred pending precise specification:

- **"Replay eligibility"** — not included as a SHALL or SHALL NOT
  until a concrete, checkable definition exists. Candidate definition
  to evaluate before use: *"the persisted sequence contains no
  sequence_id gaps and exhibits no state_hash collision pattern
  consistent with a reset boundary"* — but detecting the second half
  of that isn't built, and per SHALL NOT item 2, may not be buildable
  at all under the current schema without a new persisted field (a
  reset/generation counter — see Gap 1b's "Required to close" in
  `PHOENIX_VERIFICATION_STATE.md`).

- **`execution_context.py`'s "chaining" behavior** — referenced in
  design discussion, not verified against source. Not asserted as
  either present or absent in this contract until reviewed directly
  against the actual file.

---

## Relationship to other project documents

This contract is the authoritative specification for what cold-boot
reconstruction can and cannot claim. `causal_history_verifier.py`
implements the portion of it that already exists (SHALL items 3 and
4); any future reconstruction code extends that verifier rather than
replacing it, and must not exceed what this contract permits.
`PHOENIX_VERIFICATION_STATE.md` is the broader, general-purpose
verification charter — if either document is updated, check the other
for consistency in the same commit, since this contract's Gap 1 and
Gap 1b references depend on staying aligned with that document's
entries for the same gaps.

`test_reset_epoch_observability.py` is the experimental evidence
behind every reset-related SHALL NOT clause above.

## Revision history

- **v1** (2026-08-04): initial draft, incorporating corrections from
  two rounds of review — narrowed "causal dependencies" to the two
  specific checks that exist, corrected "cryptographic state chain" to
  reflect the Gap 1b collision finding, removed "replay eligibility"
  pending definition, refined the kernel-state-derivation SHALL NOT to
  distinguish verifying consistency with a published algorithm
  (achievable) from proving original runtime correctness (not
  achievable from persisted evidence alone), added the
  evidence-driven/not-inference-driven framing statement, marked the
  reset-generation limitation as information-theoretic rather than
  implementation-specific, and constrained SHALL item 5 to require
  hash recomputation via the actual record classes rather than a
  separately reimplemented derivation.

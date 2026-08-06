# COLD_BOOT_RECONSTRUCTION_CONTRACT.md

**Status:** Draft specification, v1.2. Precedes and constrains
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

   - **Not available under the current persistence schema** for
     `KernelStateEnvelope.state_hash`.

     **Status correction:** this is NOT blocked by derivation-algorithm
     availability — the derivation exists, fully known, in
     `KernelStateMachine.get_envelope()`. It is blocked because that
     derivation depends on TRANSIENT RUNTIME STATE
     (`last_processed_seq`, `total_frames_processed`, `current_state`,
     `fault_reason`) that the current schema never persists. Closure
     requires either (A) replay-based reconstruction through the
     canonical state machine, or (B) persistence of the derivation
     inputs. **Path (A) was selected** — see "Canonical Replay
     Verification" below — specifically because it preserves schema
     stability: no existing record type gains new fields, no existing
     test's field-signature assertions break.

     Unlike the three record types above, `KernelStateEnvelope` has no
     `__post_init__` and derives no hash of its own — `state_hash` is
     computed externally, inside `KernelStateMachine.get_envelope()`,
     from that machine's PRIVATE mutable state. None of these four
     scalar inputs are persisted anywhere in the current schema — not
     in `ExecutionAuditRecord`, not in any log. Only the OUTPUT
     (`prior_state_hash`, an opaque 32 bytes) is ever stored; the
     inputs needed to recompute it are not.

     This means SHALL 5's implementation constraint (recompute via the
     actual class's own derivation, never reimplement) has no clean
     target for `state_hash` as things stand, because there is no
     self-contained derivation on a persisted object to call into.
     Closing this requires one of two materially different paths, not
     a simple extension of the existing SHALL 5 pattern:

     (a) **Persist the four raw derivation inputs** as new fields on
         some future log entry. This would then require a NEW pure
         function replicating `get_envelope()`'s packing logic — which
         is itself a reimplementation SHALL 5's constraint currently
         forbids, and would need a deliberate, explicitly documented
         exception to that constraint, not a quiet exception.

     (b) **Sequential replay** (SELECTED — see "Canonical Replay
         Verification" section below): construct a real
         `KernelStateMachine`, replay every transition from genesis
         through the persisted history in order, and compare its
         `get_envelope().state_hash` at each step against the
         corresponding `prior_state_hash` already on disk. This uses
         the actual class (satisfying SHALL 5's spirit more faithfully
         than (a)), but introduces a real, mutable, stateful runtime
         object into what has so far been a passive-record-only
         verifier — a change to the verifier's isolation posture
         handled as a deliberate, documented, separate extension
         rather than folded silently into SHALL 5.

     Partial closure status: Path (b) is now implemented
     (`kernel_state_replay.py`) and proven for the single-engine,
     no-administrative-reset case (`test_kernel_state_replay.py`,
     6/6). It remains unavailable for histories spanning an
     administrative reset (Gap 1b) and for multi-engine interleaved
     logs (no session identifier exists in the schema to detect that
     case) — see "Canonical Replay Verification" below for the
     documented scope limits.

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

## Canonical Replay Verification (extension — opt-in, different isolation posture)

This section governs `kernel_state_replay.py` and anything built on
its `KernelStateVerifier` interface. It is explicitly SEPARATE from
the passive verification SHALL/SHALL NOT items above — those govern
`cold_boot_reconstruction.py` and `causal_history_verifier.py`, which
remain strictly passive (no live runtime objects), unchanged by this
section.

**Why this is a separate section, not an amendment to SHALL 5 above:**
closing the state_hash gap via replay requires constructing a real,
mutable `KernelStateMachine` — a genuine departure from the
evidence-driven, passive-record-only posture the rest of this contract
holds to. That departure is deliberate and bounded, not incidental,
and callers must opt into it explicitly (see
`reconstruct_cold_boot_with_replay()` vs. `reconstruct_cold_boot()`,
the latter unchanged by this extension).

**A canonical replay verifier SHALL:**
- Construct the state machine only via the actual, unmodified
  `KernelStateMachine` class from `execution_kernel_state.py` — never
  a separate reimplementation of its transition or hashing logic.
  Evidence: `kernel_state_replay.py` imports and instantiates
  `KernelStateMachine` directly; no hashing logic is reimplemented.
- Replay transitions in the exact sequence the original engine would
  have performed them, inferred only from fields already present on
  `ExecutionAuditRecord` (`sequence_id`, `success`, `error_message`).
- Refuse to continue replay past an unresolved fault (see Gap 1b) —
  report affected records as explicitly unverified via
  `unverified_after_fault_count`, never guess whether a reset occurred.
  Evidence: `test_kernel_state_replay.py::test_records_appended_after_a_fault_are_marked_unverified_not_guessed`.
- Expose its capability behind the `KernelStateVerifier` interface, so
  a future Path (A) implementation (should a schema change ever
  persist the raw derivation inputs) could be substituted without
  callers changing. Evidence: `SequentialReplayKernelVerifier`
  implements `KernelStateVerifier`; `reconstruct_cold_boot_with_replay()`
  accepts any implementation via its `kernel_verifier` parameter.

**A canonical replay verifier SHALL NOT:**
- Claim validity across multiple interleaved engine/module runs in one
  log. No session identifier exists anywhere in the current schema to
  detect this case — `kernel_state_replay.py`'s own docstring names
  this as scope limitation 1, not a silently assumed non-issue.
- Claim to verify whether the FIRST record in a given history was
  itself preceded by an undetected reset (scope limitation 2) —
  genesis is always assumed, never proven, per the same
  information-theoretic argument behind Gap 1b.
- Be silently merged into `reconstruct_cold_boot()`'s default
  behavior. Combining passive and replay verification is available
  only via the explicitly separate `reconstruct_cold_boot_with_replay()`
  entry point in `cold_boot_replay_extension.py` —
  `cold_boot_reconstruction.py` itself is not modified by this
  extension.

**Status:** Path (b) implemented and proven for the single-engine,
no-reset case. Gap 1b remains open and continues to bound this
extension's claims exactly as it bounds the passive verifier's.

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

- **v1.1** (2026-08-04): corrected the SHALL 5 entry for
  `KernelStateEnvelope.state_hash`. The prior wording ("contingent on
  Gap 1 closing, `execution_kernel_state.py`'s derivation being
  incorporated") understated the actual gap — re-examination of
  `execution_kernel_state.py` shows `state_hash`'s four scalar inputs
  are private `KernelStateMachine` state, never persisted anywhere in
  the current schema; only the output hash is stored. Replaced with an
  accurate description of the two genuinely different closure paths
  (persisting new fields with an explicit reimplementation exception,
  or sequential replay through a real state machine instance) and why
  neither is a simple extension of the existing SHALL 5 pattern.

- **v1.2** (2026-08-04): corrected Gap 1's framing again — from
  "algorithm unavailable" (imprecise) to "algorithm known, its inputs
  are transient runtime state never persisted" (precise). Selected and
  implemented Path (b), sequential replay, specifically because it
  preserves schema stability over Path (a)'s field additions. Added
  the "Canonical Replay Verification" section formalizing
  `kernel_state_replay.py`'s `KernelStateVerifier` interface as a
  documented, bounded, opt-in exception to this contract's
  passive-only posture — proven for the single-engine, no-reset case;
  Gap 1b continues to bound its claims across resets exactly as it
  bounds the passive verifier.

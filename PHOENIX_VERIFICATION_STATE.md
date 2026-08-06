# PHOENIX_VERIFICATION_STATE.md

**Purpose:** a single reference for "what has actually been proven, and by what evidence" — so six months from now the answer to "did we actually prove this?" is in one place, not scattered across chat history.

**Scope note on language:** nothing below is marked "VERIFIED" as a standalone claim. Every line is phrased as *covered by a specific, named, passing test suite as of the most recent full run*, currently 352/352, all green, zero regressions. That is a narrower and more honest claim than "verified" — it means these properties hold for the test suite's inputs and this codebase's current state, not that the system has been adversarially tested, audited by a third party, or run under production load.

---

## In-Memory Invariants (single live process, no persistence involved)

| Property | Evidence |
|---|---|
| Record construction invariants (mutual exclusivity of success/error fields, non-empty required fields, well-formed hash lengths) | `test_module_registration_audit.py`, `test_execution_audit.py`, `decision_record_contract.py`'s own `__post_init__` checks |
| Cryptographic hash stability (identical inputs → identical hash; any field change → different hash) | Fuzz tests across all three record types: `test_fuzz_identical_*`, `test_fuzz_changed_*` in each persistence/audit test file |
| Registration atomicity (failed registration leaves no lifecycle trace; retry works; duplicates still blocked) | `test_registration_atomicity.py`, 5/5 |
| Registration attempt telemetry (failures are recorded, not forgotten, without affecting duplicate protection) | `test_registration_attempt_history.py`, 5/5 |
| Decision ancestry, in-memory (every audit record has exactly one preceding allowed decision) | `test_decision_record_invariants.py` Invariant B |
| Decision count matches attempt count, replay ordering preserved | `test_decision_record_invariants.py` Invariants A and C |
| State-hash chaining across frames, within a live engine instance | `test_engine_audit_integration.py::test_audit_record_chains_to_prior_state_hash`, `test_deterministic_execution_engine.py::test_happy_path_and_cryptographic_state_chaining` |
| Replay determinism, in-memory (same engine, same inputs, same output hashes) | `test_deterministic_execution_engine.py::test_replay_equivalence_determinism`, `test_pipeline_integration.py::test_deterministic_replay_across_runs`, `test_replay_engine_audit_chain.py` |
| Module lifecycle state machine (legal/illegal transitions, terminal states) | `test_module_lifecycle.py`, 22/22 |
| Compliance check suite (determinism, no context mutation, graceful rejection of pathological input, hashable output, auditable failure) | `test_module_contract_compliance.py`, both `PhoenixAExecutionModule` and `ExampleExecutionModule` |

## Execution Generation Identity

**Added 2026-08-05.** A 16-byte `generation_id`, minted once at true kernel genesis (`KernelStateMachine.__init__`) and re-minted only on an administrative reset (`FAULTED → INITIALIZING`), now participates in the hash derivation of `KernelStateEnvelope.state_hash` and `DecisionRecord.record_hash`. This closes part of what Gap 1b (below) originally found — see that entry for the corrected, narrower current scope of what remains open.

| Property | Evidence |
|---|---|
| Kernel state hash distinguishes pre-reset and post-reset generations, even when every scalar field (`last_processed_seq`, `total_frames_processed`, `state`, `fault_reason`) is otherwise identical | `test_reset_epoch_observability.py::test_kernel_and_record_hash_now_distinguish_reset_generations_but_decision_hash_does_not` |
| `DecisionRecord.record_hash` also distinguishes reset generations — `generation_id` is threaded in from `prior_envelope.generation_id` at construction time, independent of the (still generation-blind) `decision_hash` it wraps | same test as above |
| `ExecutionAuditRecord.prior_state_hash` and `audit_hash` inherit the kernel-level distinction | same test as above |
| `generation_id` survives JSON disk round-trip for both `DecisionRecord` and `ExecutionAuditRecord` (added as an opaque field, preserved byte-for-byte, same treatment as the other hash fields) | `test_decision_record_persistence.py`, `test_execution_audit_persistence.py` |
| Sequential kernel-state replay (`kernel_state_replay.py`, Path B) reconstructs a machine seeded with a persisted history's own `generation_id`, via `KernelStateMachine.from_history()`, instead of assuming a fresh genesis | `test_kernel_state_replay.py`, all 6 tests |
| Two independently-constructed engine/kernel instances sharing an explicit `generation_id` (via `DeterministicExecutionEngine.with_generation()`) produce identical hashes; two ordinary independently-constructed instances do NOT, by design, since they are different generations | `test_deterministic_execution_engine.py::test_replay_equivalence_determinism`, `test_module_contract_compliance.py::test_module_replay_matches`, and every other replay-equivalence test across the suite |

**Explicitly NOT covered by the above:**
- `ExecutionPolicyDecision.decision_hash` (computed in `execution_authorizer.py`, one layer above the kernel) still does **not** distinguish reset generations — it has no `generation_id` input at all, deliberately, to avoid giving the authorizer a kernel dependency. See the Gap 1b update below.
- Replay across an *actual* generation boundary — a persisted history that contains a real reset partway through — is out of scope for both `KernelStateMachine.from_history()` and `kernel_state_replay.py`. Both are scoped to reconstructing a single generation; `kernel_state_replay.py` detects a generation change mid-history and stops, reporting `generation_boundary_index`, rather than attempting to replay through it. Lineage-spanning reconstruction has a frozen, fully-specified design — see `REPLAY_GENERATION_MODEL.md` — but is not built. See that document's Phase 1–3 decomposition and its own explicit "when to revisit" criteria before starting this work.

## Disk Persistence (single-record round-trip)

| Property | Evidence |
|---|---|
| `ModuleRegistrationAttemptRecord` survives JSON disk round-trip, hash intact | `test_registration_audit_persistence.py`, 9/9 |
| `DecisionRecord` survives JSON disk round-trip — both the opaque `decision_hash` and the derived `record_hash` independently checked | `test_decision_record_persistence.py`, 11/11 |
| `ExecutionAuditRecord` survives JSON disk round-trip — all three opaque hashes plus derived `audit_hash` independently checked | `test_execution_audit_persistence.py`, 15/15 |
| Reconstructed hashes are genuinely recomputed, not trusted from storage (tampering tests) | Tampering test cases in all three persistence test files above |
| Malformed or incomplete persisted data fails loudly, not silently | Corruption-rejection tests in all three persistence test files |

## Disk Persistence (multi-record, append-only)

| Property | Evidence |
|---|---|
| Registration attempt log preserves append order and hash integrity across many records | `test_registration_audit_log_append.py`, 11/11 |
| Decision record log preserves append order and both hashes across many records | `test_decision_record_log_append.py`, 11/11 |
| Execution audit log preserves append order and all four hashes across many records | `test_execution_audit_log_append.py`, 11/11 |
| Corrupt lines are rejected with a locatable line number, not silently skipped | Corruption tests in all three append-log test files |
| Reopen-and-append across separate calls does not clobber prior content | `test_appending_across_separate_calls_preserves_prior_records` in all three append-log test files |

## Cross-Log Verification (disk-only, no live runtime objects — the external verifier boundary)

| Property | Evidence |
|---|---|
| Decision ancestry, re-derived purely from disk (every audit record on disk has a matching allowed decision record on disk) | `causal_history_verifier.py` Check 1, `test_causal_history_verifier.py` |
| Per-module sequence ordering holds within the persisted decision and audit logs | `causal_history_verifier.py` Check 2 |
| Every module_id in the decision/audit logs has a corresponding successful registration attempt on disk | `causal_history_verifier.py` Check 3 |
| Verifier has zero import dependency on the live engine, registry, lifecycle manager, or authorizer — proven by subprocess, not just import inspection | `test_verifier_runtime_isolation.py` |

## Cold Boot Reconstruction

| Property | Evidence |
|---|---|
| Registration, authorization, and execution histories reconstructed as real objects from disk alone, with verified ordering and causal relationships | `cold_boot_reconstruction.py`, `test_cold_boot_reconstruction.py`, 11/11, every test traced to a specific clause of `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` |
| Hash recomputation happens only via the actual record classes' own derivation — never reimplemented | Structural AST-based import tests in `test_cold_boot_reconstruction.py` |

## Repository Reproducibility

| Property | Evidence |
|---|---|
| Repository is self-contained: a fresh `git clone` into an unrelated directory, with `cargo build --release` run once as a documented manual step, produces a full passing suite with zero hidden local-state dependencies | Manual verification: clean clone into a sibling directory, `cargo build --release`, `pytest -v` — full suite passed |

**Scope note:** this confirms the repository's committed source is sufficient to reproduce the full test suite. It does NOT yet confirm this works with zero manual steps (the Rust build step is a documented manual prerequisite — see `BUILD.md`).

---

## Known Non-Verifiable Areas (explicit gaps, not silent omissions)

### Gap 1 — Kernel state-hash consistency, from disk alone

**Status:** Not available under the current persistence schema.

**EDITORIAL FLAG, added 2026-08-05, not yet resolved:** this entry's "Required to close" section below describes sequential replay (option (b)) as a hypothetical, unbuilt path. `kernel_state_replay.py` already exists, already implements exactly that approach, and its tests were already part of the passing suite before the `generation_id` migration began this session. This entry does not cite `kernel_state_replay.py` anywhere. Left as-is pending a decision on whether this means Gap 1 should actually be considered closed (or substantially narrowed) by Path B's existence, or whether Path B's known limitations (single-engine/no-reset assumption, now single-generation) mean the gap is real but this entry's framing needs updating to reflect what Path B already covers. Not resolved unilaterally here — see the Execution Generation Identity section above for what Path B currently proves.

**What was previously believed:** that this capability was "contingent on Gap 1 closing (`execution_kernel_state.py`'s derivation being incorporated into the verifier)" — implying the fix was simply exposing an existing algorithm to the verifier.

**What is actually true, on re-examination of `execution_kernel_state.py`:** `KernelStateEnvelope.state_hash` is derived from `KernelStateMachine`'s PRIVATE mutable state (`last_processed_seq`, `total_frames_processed`, `current_state`, `fault_reason`, and now `generation_id`) — none of which are persisted anywhere in the current schema except via the resulting opaque hash. Only the resulting hash (`prior_state_hash`, opaque 32 bytes) is ever stored on disk. There is nothing to recompute the hash *from*, independent of whether the derivation algorithm is known.

**Required to close:** NOT simply "incorporate the derivation into the verifier." Closing this requires one of two materially different paths:
  - **(a)** Persist the raw derivation inputs as new fields on some future log entry, then build a new pure function replicating `get_envelope()`'s packing logic — which is itself a reimplementation the project's existing "never reimplement, always recompute via the actual class" constraint currently forbids, and would need an explicit, documented exception.
  - **(b)** Sequential replay: construct a real `KernelStateMachine`, replay every transition from genesis through the persisted history, and compare its `get_envelope().state_hash` at each step against persisted `prior_state_hash` values. This is materially larger in scope than exposing an algorithm, and introduces live, mutable runtime state into what has so far been a passive-record-only verifier.

See `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` SHALL 5 for the full corrected analysis.

### Gap 1b — No reset-generation disambiguation in any persisted hash

**Status:** PARTIALLY CLOSED 2026-08-05. See update below. Original finding (all three hashes collided) is preserved as-written for historical accuracy; it no longer fully reflects current behavior.

**Original finding (2026-08-04, historical):** across a fault → administrative reset → resume cycle, every hash currently persisted — `KernelStateEnvelope.state_hash`, `ExecutionPolicyDecision.decision_hash`, `DecisionRecord.record_hash` — collides between the pre-reset and post-reset generations, when lifecycle state, policy, and capabilities are otherwise identical. `ExecutionPolicyState.observed_invocation_count` genuinely differs across the reset but is excluded from `decision_hash`'s computation and is not carried forward as a field on `DecisionRecord` at all.

**Original evidence:** `test_reset_epoch_observability.py`, both tests, run against the real `DeterministicExecutionEngine`, `KernelStateMachine`, and `ExecutionAuthorizer`.

**UPDATE 2026-08-05 — generation_id migration:** a `generation_id` field was added to `KernelStateEnvelope` and `DecisionRecord` (see the Execution Generation Identity section above for full evidence). As a direct result:
  - `KernelStateEnvelope.state_hash` **no longer collides** across a reset — this part of the original finding is corrected, not just closed.
  - `DecisionRecord.record_hash` **no longer collides** across a reset either, despite wrapping a `decision_hash` that still does.
  - `ExecutionPolicyDecision.decision_hash` **still collides**, unchanged — it was deliberately NOT given a `generation_id` input, to avoid coupling `execution_authorizer.py` to `KernelStateMachine`. This part of the original finding remains fully accurate.
  - `ExecutionPolicyState.observed_invocation_count` remains excluded from every persisted hash, exactly as originally found — `generation_id` is an orthogonal signal and does nothing to change this. See `test_invocation_count_differs_but_is_excluded_from_persisted_hash_fields`, unaffected by this migration.

**Current evidence:** `test_reset_epoch_observability.py::test_kernel_and_record_hash_now_distinguish_reset_generations_but_decision_hash_does_not` (renamed from the original test to state the corrected finding directly), plus `test_invocation_count_differs_but_is_excluded_from_persisted_hash_fields` (unchanged).

**This limitation is information-theoretic, not implementation-specific — narrowed scope:** this claim now applies only to `ExecutionPolicyDecision.decision_hash` and to `observed_invocation_count`'s absence from any persisted field. It no longer applies to `KernelStateEnvelope.state_hash` or `DecisionRecord.record_hash`, which now do carry reset-generation information.

**Practical consequence, narrowed:** a genuine identical-content replay after an administrative reset is now correctly distinguishable from the original run via `state_hash` and `record_hash`. It remains indistinguishable via `decision_hash` alone, and `observed_invocation_count` remains unrecoverable from any persisted field regardless of which hash is inspected.

**Current status, stated precisely (added 2026-08-05):**
  - **Schema: complete.** `generation_id` is a real, persisted, round-tripping field on `KernelStateEnvelope`, `DecisionRecord`, and `ExecutionAuditRecord`. No further schema work is planned for the single-generation case.
  - **Single-generation replay: complete.** `KernelStateMachine.from_history()` and `kernel_state_replay.py` (Path B) reconstruct and verify one real historical generation from disk alone — see the Execution Generation Identity section above.
  - **Multi-generation replay (reconstructing a lineage that crosses one or more real resets): intentionally deferred, design frozen, not implemented.** The design is fully specified in `REPLAY_GENERATION_MODEL.md` — a three-phase decomposition (Phase 1: segmentation, no replay; Phase 2: independent per-segment verification, reusing `kernel_state_replay.py` unmodified; Phase 3: candidate lineage graph construction, not proof) — but no phase has been built. That document is the authoritative reference for this work when it resumes; this entry should not be treated as a substitute for reading it.

**Required to close (remaining, narrowed by the above):**
  - Build Phases 1–3 per `REPLAY_GENERATION_MODEL.md` — not started, deliberately, until a concrete need arises. See that document's own "when to revisit" criteria for the related, separately-deferred question of whether a dedicated transition-logging record type is ever needed.
  - Thread `generation_id` (or an equivalent signal) into `ExecutionPolicyDecision.decision_hash`'s computation — the deliberate design choice not to do this may need revisiting if policy-layer generation-blindness turns out to matter in practice, but as of this update it is being kept as a considered tradeoff (kernel-decoupling), not an oversight.
  - `observed_invocation_count` visibility in persisted hashes remains a fully open, separate gap, untouched by this migration.

### Gap 2 — Policy decision hash provenance

**Status:** Not independently verifiable.

**What IS proven:** every persisted `DecisionRecord.decision_hash` is present and well-formed (32 bytes) — but this is true by construction (`DecisionRecord.__post_init__` enforces it), so confirming it again in the verifier would not be a meaningful check.

**What is NOT proven:** that `decision_hash` genuinely traces back to a real `ExecutionPolicyDecision` object computed by the authorizer/policy layer, since that source object is never persisted anywhere in the current three logs.

**Reason:** `DecisionRecord.decision_hash` is documented as a reference to `ExecutionPolicyDecision.decision_hash` — but the referenced object itself has no independent record on disk to check against.

**Required to close:** persist `ExecutionPolicyDecision` itself (a fourth log, not yet built), so `decision_hash` can be checked against an independent source rather than only against its own downstream reference.

---

## Explicitly Out of Scope (not gaps — never claimed)

- Trading signal validity, Sharpe ratio, or any live-capital readiness claim. This document covers the execution-kernel/persistence/verification layer only.
- Crash-mid-write safety, atomic append guarantees, or concurrent-writer coordination for any of the three logs.
- Schema versioning or migration between record format versions.
- Any claim about the broader Sentinel corpus outside this specific test suite (see the separate, earlier multi-document audit for that work's findings, including the still-unresolved hardcoded Transfer Entropy stub and terminology drift issues).

---

**Last updated against:** full suite run at 352/352 passing, zero regressions. `generation_id` execution-generation-identity migration completed 2026-08-05 (see Execution Generation Identity section above); Gap 1b partially closed the same day — see that entry for the corrected, narrower current scope, and for the schema-complete / single-generation-replay-complete / multi-generation-replay-deferred status split. `REPLAY_GENERATION_MODEL.md`, added 2026-08-05, is the authoritative frozen design for future multi-generation replay work (Phases 1–3) — not yet implemented, referenced from Gap 1b above. Confirmed reproducible from a fresh clone with one documented manual build step (see `BUILD.md`). Python dependency versions pinned via `requirements.txt` (Gap 3, closed). Gap 1 corrected 2026-08-04: prior framing understated the gap — see Gap 1 entry above and `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` v1.1. Gap 1's citation of `kernel_state_replay.py` flagged as missing/unresolved 2026-08-05 — see editorial flag in that entry.

**Maintenance note:** when a new check, record type, or log is added, add its row to the relevant table above with the specific test file/name as evidence — not a bare checkmark. When a gap closes, move its row from "Known Non-Verifiable Areas" into the appropriate verified table, citing the new evidence. When a gap's own description turns out to be wrong (as happened with Gap 1), correct it in place with the old framing left visible, not silently replaced.

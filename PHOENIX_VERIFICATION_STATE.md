# PHOENIX_VERIFICATION_STATE.md

**Purpose:** a single reference for "what has actually been proven, and by what evidence" — so six months from now the answer to "did we actually prove this?" is in one place, not scattered across chat history.

**Scope note on language:** nothing below is marked "VERIFIED" as a standalone claim. Every line is phrased as *covered by a specific, named, passing test suite as of the most recent full run*, currently 348/348, all green, zero regressions. That is a narrower and more honest claim than "verified" — it means these properties hold for the test suite's inputs and this codebase's current state, not that the system has been adversarially tested, audited by a third party, or run under production load.

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
| Kernel `state_hash` consistency, single-engine/no-reset case, via sequential replay through the real `KernelStateMachine` | `kernel_state_replay.py`, `test_kernel_state_replay.py`, 6/6 — see "Canonical Replay Verification" in `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` |

## Repository Reproducibility

| Property | Evidence |
|---|---|
| Repository is self-contained: a fresh `git clone` into an unrelated directory, with `cargo build --release` run once as a documented manual step, produces a full passing suite with zero hidden local-state dependencies | Manual verification: clean clone into a sibling directory, `cargo build --release`, `pytest -v` — full suite passed |

**Scope note:** this confirms the repository's committed source is sufficient to reproduce the full test suite. It does NOT yet confirm this works with zero manual steps (the Rust build step is a documented manual prerequisite — see `BUILD.md`).

---

## Known Non-Verifiable Areas (explicit gaps, not silent omissions)

### Gap 1 — Kernel state-hash consistency, from disk alone

**Status:** Partially closed. Single-engine, no-administrative-reset
case proven via sequential replay. Multi-engine interleaving and
histories spanning a reset remain open.

**Status correction (this session):** the gap was never algorithm
unavailability — `state_hash`'s derivation is fully known
(`KernelStateMachine.get_envelope()`). It was unavailability of the
derivation's INPUTS in persisted form (transient runtime state, never
written to any log). Path (A) — sequential replay through the
canonical state machine — was selected over Path (B) — persisting the
raw inputs — specifically because it preserves schema stability: no
existing record type gains new fields, no existing test's
field-signature assertions break.

**What is actually true, on re-examination of `execution_kernel_state.py`:** `KernelStateEnvelope.state_hash` is derived from `KernelStateMachine`'s PRIVATE mutable state (`last_processed_seq`, `total_frames_processed`, `current_state`, `fault_reason`) — none of which are persisted anywhere in the current schema. Only the resulting hash (`prior_state_hash`, opaque 32 bytes) is ever stored on disk.

**What IS now proven:** for a single engine/module run with no administrative reset anywhere in its history, sequential replay through a real `KernelStateMachine` — starting from genesis, replaying the exact transition sequence the original engine performed, inferred from `ExecutionAuditRecord`'s own fields — reproduces byte-identical `state_hash` values at every step. `kernel_state_replay.py`'s `KernelStateVerifier` interface makes this pluggable, and `cold_boot_replay_extension.py`'s `reconstruct_cold_boot_with_replay()` combines it with the existing passive verifier as an explicit, separate, opt-in entry point — `reconstruct_cold_boot()` itself is unmodified.

**What remains open:**
  - Histories spanning an administrative reset — Gap 1b proves resets are indistinguishable from fresh starts under the current schema, so replay correctly refuses to guess past a fault rather than silently continuing (`unverified_after_fault_count` reports this rather than hiding it).
  - Multi-engine/multi-module interleaving in one log — no session or engine identifier exists in the schema to detect or prevent this; replay assumes single-engine chronological order and cannot verify that assumption holds.

See `COLD_BOOT_RECONSTRUCTION_CONTRACT.md`'s "Canonical Replay Verification" section for the full specification.

### Gap 1b — No reset-generation disambiguation in any persisted hash

**Status:** Confirmed limitation, proven by direct experiment.

**Finding:** across a fault → administrative reset → resume cycle, every hash currently persisted — `KernelStateEnvelope.state_hash`, `ExecutionPolicyDecision.decision_hash`, `DecisionRecord.record_hash` — collides between the pre-reset and post-reset generations, when lifecycle state, policy, and capabilities are otherwise identical. `ExecutionPolicyState.observed_invocation_count` genuinely differs across the reset but is excluded from `decision_hash`'s computation and is not carried forward as a field on `DecisionRecord` at all.

**Evidence:** `test_reset_epoch_observability.py`, both tests, run against the real `DeterministicExecutionEngine`, `KernelStateMachine`, and `ExecutionAuthorizer`.

**This limitation is information-theoretic, not implementation-specific:** the schema contains zero bits of reset-generation information for any algorithm to recover.

**Practical consequence:** a genuine identical-content replay after an administrative reset would be indistinguishable from the original run across every hash field currently in the schema — distinguishable only by incidental frame-content differences, if any exist.

**Required to close:** a new persisted field (e.g. a monotonic boot/reset generation counter) threaded through `KernelStateEnvelope`, `ExecutionPolicyDecision`, and `DecisionRecord` — not a kernel-only fix, since the collision is confirmed at both layers independently.

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

**Last updated against:** full suite run at 348/348 passing, zero regressions, confirmed reproducible from a fresh clone with one documented manual build step (see `BUILD.md`). Python dependency versions pinned via `requirements.txt` (Gap 3, closed). Gap 1 corrected twice: 2026-08-04 initial correction (prior framing understated the gap), then again 2026-08-04 same session (Path (b) selected and implemented — see Gap 1 entry above and `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` v1.2's "Canonical Replay Verification" section). `test_cold_boot_replay_integration.py` (combining passive reconstruction with kernel replay end-to-end) has been written but its pass/fail status is not yet confirmed as of this update — do not cite it as evidence until a passing run is recorded here.

**Maintenance note:** when a new check, record type, or log is added, add its row to the relevant table above with the specific test file/name as evidence — not a bare checkmark. When a gap closes, move its row from "Known Non-Verifiable Areas" into the appropriate verified table, citing the new evidence. When a gap's own description turns out to be wrong (as happened with Gap 1), correct it in place with the old framing left visible, not silently replaced.

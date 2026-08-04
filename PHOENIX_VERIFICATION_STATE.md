# PHOENIX_VERIFICATION_STATE.md

**Purpose:** a single reference for "what has actually been proven, and by what evidence" — so six months from now the answer to "did we actually prove this?" is in one place, not scattered across chat history.

**Scope note on language:** nothing below is marked "VERIFIED" as a standalone claim. Every line is phrased as *covered by a specific, named, passing test suite as of the most recent full run (327/327, all green, zero regressions)*. That is a narrower and more honest claim than "verified" — it means these properties hold for the test suite's inputs and this codebase's current state, not that the system has been adversarially tested, audited by a third party, or run under production load.

---

## In-Memory Invariants (single live process, no persistence involved)

| Property | Evidence |
|---|---|
| Record construction invariants (mutual exclusivity of success/error fields, non-empty required fields, well-formed hash lengths) | `test_module_registration_audit.py`, `test_execution_audit.py`, `decision_record_contract.py`'s own `__post_init__` checks |
| Cryptographic hash stability (identical inputs → identical hash; any field change → different hash) | Fuzz tests across all three record types: `test_fuzz_identical_*`, `test_fuzz_changed_*` in each persistence/audit test file |
| Registration atomicity (failed registration leaves no lifecycle trace; retry works; duplicates still blocked) | `test_registration_atomicity.py`, 5/5 |
| Registration attempt telemetry (failures are recorded, not forgotten, without affecting duplicate protection) | `test_registration_attempt_history.py`, 5/5 |
| Decision ancestry, in-memory (every audit record has exactly one preceding allowed decision) | `test_decision_record_invariants.py` Invariant B, `test_invariant_b_every_audit_record_has_exactly_one_preceding_allowed_decision` |
| Decision count matches attempt count, replay ordering preserved | `test_decision_record_invariants.py` Invariants A and C |
| State-hash chaining across frames, within a live engine instance | `test_engine_audit_integration.py::test_audit_record_chains_to_prior_state_hash`, `test_deterministic_execution_engine.py::test_happy_path_and_cryptographic_state_chaining` |
| Replay determinism, in-memory (same engine, same inputs, same output hashes) | `test_deterministic_execution_engine.py::test_replay_equivalence_determinism`, `test_pipeline_integration.py::test_deterministic_replay_across_runs`, `test_replay_engine_audit_chain.py` (8 tests) |
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
| Decision ancestry, re-derived purely from disk (every audit record on disk has a matching allowed decision record on disk) | `causal_history_verifier.py` Check 1, `test_causal_history_verifier.py`, 2 failure-injection cases |
| Per-module sequence ordering holds within the persisted decision and audit logs | `causal_history_verifier.py` Check 2, 2 failure-injection cases including cross-module independence |
| Every module_id in the decision/audit logs has a corresponding successful registration attempt on disk | `causal_history_verifier.py` Check 3, 2 failure-injection cases |
| Verifier has zero import dependency on the live engine, registry, lifecycle manager, or authorizer — reads only the three log files | Confirmed by inspection of `causal_history_verifier.py`'s import list |
---
## Addition to PHOENIX_VERIFICATION_STATE.md

Insert this as a new section, after the "Cross-Log Verification" table
and before "Known Non-Verifiable Areas":

---

## Repository Reproducibility

| Property | Evidence |
|---|---|
| Repository is self-contained: a fresh `git clone` into an unrelated directory, with `cargo build --release` run once as a documented manual step, produces a full 327/327 passing suite with zero hidden local-state dependencies | Manual verification: `git clone` into `phoenix-clean-test` (sibling directory, no shared state with the working `phoenix-verify` directory), followed by `cargo build --release` in `phoenix_core_rs/`, followed by `pytest -v` — 327 passed, 0 failed |

**Scope note:** this confirms the repository's *committed source* is
sufficient to reproduce the full test suite. It does NOT yet confirm
this works with zero manual steps (the Rust build step is still a
manual, undocumented-until-now prerequisite — see BUILD.md) or that
Python dependency versions are pinned (no `requirements.txt` exists
yet — see BUILD.md's TODO section). Both are named, tracked gaps, not
silent assumptions.

---

Also add this line to the "Explicitly Out of Scope" section's list,
or better, move it OUT of "out of scope" and into a new small
"Known Gaps — Tooling" subsection alongside Gap 1 and Gap 2, since
unlike the truly out-of-scope items (trading signal validity, crash
safety), this one has a clear, near-term path to closing:

### Gap 3 — Pinned Python dependency versions

**Status:** Not yet closed.

**What IS proven:** the three Python dependencies actually needed
(`pytest`, `hypothesis`, `numpy`) are known, from direct inspection of
test file imports across the suite.

**What is NOT proven:** that any *specific version* of those three
packages is required, or that the suite is robust to version drift in
them.

**Required to close:** run `pip freeze > requirements.txt` in a
known-working environment and commit it.

---

## Also update the document's closing line to:

**Last updated against:** full suite run at 327/327 passing, zero
regressions, confirmed reproducible from a fresh clone with one
documented manual build step (see BUILD.md). Python dependency
versions not yet pinned (Gap 3).
---

## Known Non-Verifiable Areas (explicit gaps, not silent omissions)

### Gap 1 — Kernel state-hash chain, independently from disk

**Status:** Not verifiable by the current external verifier.

**What IS proven:** state-hash chaining across frames holds within a single live `DeterministicExecutionEngine` instance (see in-memory table above).

**What is NOT proven:** that the same chain can be independently reconstructed and verified from `execution_audit_log.jsonl` alone, without any live engine object, after the process that wrote it is gone.

**Reason:** `ExecutionAuditRecord.prior_state_hash` is documented as a reference to `KernelStateEnvelope.state_hash`, "captured before execution" — but the derivation logic for how that hash is computed and chained across frames lives in `execution_kernel_state.py`, which has not yet been made available to the verifier's design. Building this check without that file would mean guessing at chaining logic — a mistake this project already paid for once this session (the `ModuleComplianceError` inheritance investigation).

**Required to close:** `execution_kernel_state.py`'s `state_hash` derivation, reviewed and incorporated into the verifier.
### Gap 1b — No reset-generation disambiguation in any persisted hash

**Status:** Confirmed limitation, proven by direct experiment.

**Finding:** across a fault → administrative reset → resume cycle, every hash currently persisted — `KernelStateEnvelope.state_hash`, `ExecutionPolicyDecision.decision_hash`, `DecisionRecord.record_hash` — collides between the pre-reset and post-reset generations, when lifecycle state, policy, and capabilities are otherwise identical. `ExecutionPolicyState.observed_invocation_count` genuinely differs across the reset but is excluded from `decision_hash`'s computation and is not carried forward as a field on `DecisionRecord` at all.

**Evidence:** `test_reset_epoch_observability.py`, both tests, run against the real `DeterministicExecutionEngine`, `KernelStateMachine`, and `ExecutionAuthorizer`.

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

**Last updated against:** full suite run at 327/327 passing, zero regressions, all work through the causal history verifier's initial three checks and both append-only log extensions.

**Maintenance note:** when a new check, record type, or log is added, add its row to the relevant table above with the specific test file/name as evidence — not a bare checkmark. When a gap closes, move its row from "Known Non-Verifiable Areas" into the appropriate verified table, citing the new evidence.

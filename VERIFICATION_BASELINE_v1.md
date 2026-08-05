# VERIFICATION_BASELINE_v1.md

**A snapshot pointer, not a new claim.** Everything referenced here is
already proven elsewhere (`PHOENIX_VERIFICATION_STATE.md`,
`COLD_BOOT_RECONSTRUCTION_CONTRACT.md`, and the test files themselves).
This document exists so a future session — or a future person — can
find "what did the verification corpus look like at this point" in
one place, tagged in git, without re-deriving it from chat history.

**Tag:** `verification-baseline-v1`
**Date:** 2026-08-04
**Test count at this baseline:** 342 passed, 0 failed, full suite,
zero regressions across every commit that built toward this point.

---

## What this baseline covers

**Registry and lifecycle layer (v2.5–v2.7):**
- Registration atomicity (failed registration leaves no lifecycle
  trace; retry works; duplicate protection intact) —
  `test_registration_atomicity.py`
- Registration attempt telemetry (failures recorded, not forgotten,
  without breaking atomicity) — `test_registration_attempt_history.py`
- Decision record history (one record per authorization attempt,
  allowed or denied) — `test_decision_record_invariants.py`

**Persistence layer — three record types, individually proven:**
- `ModuleRegistrationAttemptRecord` disk round-trip —
  `test_registration_audit_persistence.py`
- `DecisionRecord` disk round-trip (opaque + derived hash distinction) —
  `test_decision_record_persistence.py`
- `ExecutionAuditRecord` disk round-trip (three opaque hashes + derived) —
  `test_execution_audit_persistence.py`

**Append-only logs — same three record types, multi-record + ordering:**
- `test_registration_audit_log_append.py`
- `test_decision_record_log_append.py`
- `test_execution_audit_log_append.py`

**Cross-log verification (disk-only, zero live-runtime dependency):**
- `causal_history_verifier.py` — decision ancestry, per-module
  ordering, module identity cross-reference —
  `test_causal_history_verifier.py`
- Runtime isolation proven by subprocess, not just import inspection —
  `test_verifier_runtime_isolation.py`

**Cold boot reconstruction:**
- `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` v1 — the specification
- `cold_boot_reconstruction.py` — the implementation, every clause
  traced to a test — `test_cold_boot_reconstruction.py`

**Reset epoch findings (Gap 1b):**
- `test_reset_epoch_observability.py` — neither kernel-level
  (`state_hash`) nor policy-level (`decision_hash`, `record_hash`)
  evidence distinguishes an administrative reset from a fresh start,
  under the current schema

**Repository reproducibility:**
- Confirmed clean-clone reproducibility with one documented build
  step — see `BUILD.md`, `requirements.txt`

---

## Known open gaps at this baseline (not resolved, not silently omitted)

- **Gap 1** — `KernelStateEnvelope.state_hash` consistency verification
  is unavailable to the cold-boot verifier; blocked on
  `execution_kernel_state.py`'s derivation being incorporated.
- **Gap 1b** — no persisted field anywhere in the schema
  (`KernelStateEnvelope`, `ExecutionPolicyDecision`, `DecisionRecord`)
  distinguishes an administrative reset generation from a fresh start.
  Confirmed information-theoretic, not implementation-specific — the
  schema contains zero bits of this information to recover.
- **Gap 2** — `ExecutionPolicyDecision.decision_hash` provenance is not
  independently verifiable; the object it references
  (`ExecutionPolicyDecision` itself) is never persisted.
- **Gap 3** — closed. Python dependency versions pinned via
  `requirements.txt`.
- **"Replay eligibility"** — deliberately undefined; not a claim this
  baseline makes in any form.

See `PHOENIX_VERIFICATION_STATE.md` and
`COLD_BOOT_RECONSTRUCTION_CONTRACT.md` for full detail on each.

## Explicitly out of scope at this baseline

- Trading signal validity, Sharpe ratio, live-capital readiness — this
  baseline covers the execution-kernel/persistence/verification layer
  only.
- Crash-mid-write safety, atomic append guarantees, concurrent-writer
  coordination for any of the three logs.
- Any claim about the broader Sentinel corpus outside this specific
  test suite.

---

## How to reproduce this baseline

```
git clone https://github.com/skyhacker156/deterministic-runtime-engine.git
cd deterministic-runtime-engine
git checkout verification-baseline-v1
cd phoenix_core_rs && cargo build --release && cd ..
pip install -r requirements.txt
pytest -v
```
Expected: 342 passed, 0 failed.

## What "baseline" means here, precisely

This is a **checkpoint marker**, not a certification. It says: at this
commit, these 342 tests exist, all pass, and the documents above
accurately describe what they prove and what they don't. It does not
mean the system is complete, production-ready, or free of undiscovered
issues outside what's been tested. Future sessions extending this work
should update this baseline's referenced documents in the same commit
as any change that affects what they claim — not let them drift.

# VERIFICATION_COVERAGE_MATRIX.md

**Purpose:** answer one question, exhaustively and without narrative: *what exactly does Phoenix claim, and what is the status of each claim?* This is a different artifact from `PHOENIX_VERIFICATION_STATE.md` — that document explains and justifies; this one indexes and cross-references. Deliberately boring. Every row should be checkable against a real file.

**Structural rule — no duplicate claim IDs.** Where a claim already has a dedicated registry (currently only Mode B, in `MODE_B_CLAIMS_REGISTRY.md`), this matrix **references** that registry's IDs rather than re-deriving or restating their content. This matrix is the index; the dedicated registry remains the source of record for its own claims.

**Status vocabulary (closed set):**
- **VERIFIED** — proven true, bounded by stated assumptions, tests exist and pass. **For policy claims** (a decision about how the project will behave, not a property of the code itself — e.g. SE-001), VERIFIED means the policy is documented and has been followed consistently in repository history since its adoption — not that it is mechanically enforced by a test that would catch a future violation. This is a real, narrower guarantee than the technical-claim reading of VERIFIED, and the Boundary column says so explicitly for every policy-type row rather than leaving it implied.
- **FORMALLY NOT PROVABLE** — proven impossible under a stated evidence model (a theorem exists, not merely an unattempted proof).
- **NOT YET BUILT** — the capability does not exist. Not proven possible or impossible — simply not attempted. The Boundary column distinguishes *deliberately deferred* (a documented tradeoff) from *genuinely open* (no decision made either way).

**Ledger Reference column values:** `IN LEDGER` (represented in `PHOENIX_VERIFICATION_STATE.md`), `NOT IN LEDGER` (claim and evidence exist; ledger entry missing), or `SEE <file>` (lives in its own dedicated document instead of the ledger by design, e.g. Mode B).

---

## Causal History Verifier (`causal_history_verifier.py`)

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| CH-001 | Decision ancestry: every audit record has a matching, allowed decision record, joined on `(sequence_id, module_id, generation_id)` | VERIFIED | `test_causal_history_verifier.py` Check 1 tests, incl. `test_decision_and_audit_sharing_sequence_and_module_but_different_generation_is_caught` | Join key includes `generation_id` as of the Check 1 fix this session — previously it did not, and could false-positive-link records across a reset (see `PROVENANCE_GRAPH_MODEL.md`, resolved headline finding) | IN LEDGER |
| CH-002 | Per-module sequence ordering is non-decreasing, checked independently for decision and audit logs | VERIFIED | `test_out_of_order_sequence_ids_within_a_module_are_caught`, `test_ordering_check_is_independent_per_module` | Does not interleave the two logs by wall-clock time — `frame_timestamp_ns` is documented as data, not a shared clock | IN LEDGER |
| CH-003 | Module identity cross-reference: every `module_id` in decision/audit logs has a successful registration attempt on disk | VERIFIED | `test_module_id_with_no_registration_record_is_caught`, `test_module_id_with_only_failed_registration_is_caught` | Checks persisted registration *attempts*, not live registry state (never persisted). `PolicyDecisionRecord.module_id` is not checked directly by this claim — see PG-001's transitive-edge note | IN LEDGER |
| CH-004 | Policy decision provenance: every `DecisionRecord.decision_hash` traces to a real `PolicyDecisionRecord`, joined on `(sequence_id, generation_id)` | VERIFIED, optional | `test_causal_history_verifier.py`'s 6 Check-4 tests, incl. the swapped-record test | Optional — only runs when caller supplies `policy_decision_log_path`; this is the closure of Gap 2 | IN LEDGER (as Gap 2, closed) |
| CH-005 | Verifier has zero import dependency on live runtime state (engine, registry, lifecycle, authorizer) | VERIFIED | `test_verifier_runtime_isolation.py`, subprocess-based, not import-inspection-based | Required extracting `ExecutionPolicyDecision` and `ModuleState` into dependency-free modules this session; proven for the current `FORBIDDEN_MODULES` set, not exhaustively | IN LEDGER |

## Hash-Chain Integrity (per record type)

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| HC-001 | `ModuleRegistrationAttemptRecord.attempt_hash` detects any field tampering | VERIFIED | `test_module_registration_audit.py` fuzz/tampering tests, `test_registration_audit_persistence.py` | No `generation_id` — this record type was never touched by that migration | IN LEDGER |
| HC-002 | `DecisionRecord.record_hash` detects tampering; `decision_hash` is an opaque, unmodified reference | VERIFIED | `test_decision_record_persistence.py` tampering tests | `record_hash` proves internal consistency, not that the referenced `decision_hash`'s underlying `ExecutionPolicyDecision` was genuine (see CH-004/HC-004). `decision_hash` itself excludes `generation_id`, collides across resets by deliberate design | IN LEDGER |
| HC-003 | `ExecutionAuditRecord.audit_hash` detects tampering across 3 independent opaque hash fields plus its own derived fields | VERIFIED | `test_execution_audit_persistence.py`, 4 separate tampering tests | Proves internal chain self-consistency only — does not authenticate that inputs were genuine (see MB-001's now-precise "What this proves" wording; the same boundary applies here) | IN LEDGER |
| HC-004 | `PolicyDecisionRecord`'s two hash layers (`decision_hash` inner, `entry_hash` outer) are independently tamper-evident | VERIFIED | `test_policy_decision_record_persistence.py`, inner/outer isolation explicitly tested | `entry_hash` proves `sequence_id`/`generation_id` binding to the decision; does not by itself prove the embedded decision's `module_id` was cross-checked against registration — that's CH-003 composed with CH-004, a transitive claim (see PG-001) | IN LEDGER (as Gap 2 closure) |

## Generation Identity / Mode B — see `MODE_B_CLAIMS_REGISTRY.md`

| ID | Claim (summary only — see registry for full text) | Status | Evidence | Ledger Reference |
|---|---|---|---|---|
| MB-001 | Within-generation hash-chain continuity | VERIFIED | `MODE_B_CLAIMS_REGISTRY.md` | SEE `MODE_B_CLAIMS_REGISTRY.md` |
| MB-002 | Generation boundary discovery (pure segmentation) | VERIFIED | `MODE_B_CLAIMS_REGISTRY.md` | SEE `MODE_B_CLAIMS_REGISTRY.md` |
| MB-003 | Cross-generation continuity | FORMALLY NOT PROVABLE | `MODE_B_CLAIMS_REGISTRY.md`, `REPLAY_GENERATION_MODEL.md` Theorem 2 | SEE `MODE_B_CLAIMS_REGISTRY.md` |
| MB-004 | Candidate lineage construction | VERIFIED (as construction, not proof) | `MODE_B_CLAIMS_REGISTRY.md` | SEE `MODE_B_CLAIMS_REGISTRY.md` |

*(This block exists so a reader scanning this matrix top to bottom doesn't have a visible hole where Mode B should be — it is not a second copy of the registry. Do not edit these four rows without editing `MODE_B_CLAIMS_REGISTRY.md` first.)*

## Deterministic Execution (Mode A1)

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| DA-001 | Given the same explicit `generation_id` and the same input sequence, two independently-constructed engine instances produce identical output hashes | VERIFIED | `test_deterministic_execution_engine.py::test_replay_equivalence_determinism`; `test_module_contract_compliance.py::test_module_replay_matches` (both `PhoenixAExecutionModule` and `ExampleExecutionModule`); the broader replay-equivalence cluster fixed via `DeterministicExecutionEngine.with_generation()` during the `generation_id` migration | This is Mode A1 specifically (`REPLAY_GENERATION_MODEL.md`'s own terminology) — a genuinely different claim from MB-001/CB-002 (Mode A2: does *one real, persisted* history match itself) and from MB-003 (cross-generation continuity). Requires explicitly holding `generation_id` constant via `with_generation()` — two *ordinary* `DeterministicExecutionEngine()` instances are, by design, different generations and are correctly expected *not* to match; that is not a counterexample to this claim, it is Gap 1b's own guarantee working as intended | IN LEDGER (as an existing, unlabeled row in "In-Memory Invariants" — "Replay determinism, in-memory" — never previously connected to Mode A/A1 terminology) |

## Schema Evolution

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| SE-001 | Archival boundary policy adopted: no backward-compatible reads, ever; every hash-invalidating migration carries a documented boundary note | VERIFIED | `SCHEMA_EVOLUTION_MODEL.md` | **Policy claim** — see the status vocabulary's policy-claim clause above. Evidence is that the one migration since adoption (`generation_id`) followed it; nothing currently detects a *future* violation automatically, since there is no test that could catch a migration that skips the boundary note | NOT IN LEDGER |
| SE-002 | Historical schema recognition correctly classifies a payload as current / recognized-historical / unrecognized | VERIFIED | `test_historical_schema_recognition.py`, 9/9 | Scoped to `DecisionRecord` and `ExecutionAuditRecord` only — the only two record types that ever had schema variation; `PolicyDecisionRecord` and `ModuleRegistrationAttemptRecord` structurally have none | NOT IN LEDGER |
| SE-003 | Recognition-is-not-verification is enforced structurally, not by convention | VERIFIED | `HistoricalVerificationResult.__post_init__`'s guard, `test_historical_verification.py`'s guard tests | Guard raises `ValueError` on invalid combinations — a future maintainer cannot construct a contradictory result even by accident | NOT IN LEDGER |
| SE-004 | Read-path corruption messages are enriched with schema classification, with zero change to signature/return-type/exception-type | VERIFIED | `decision_record_log.py`/`execution_audit_log.py`'s enriched `*LogCorruptionError`, 6 new tests total | Message-only change (Option A of `VERIFICATION_INTEGRATION_CONTRACT.md`); Options B (return-type change) and C (new non-aborting reader) both named, neither built | NOT IN LEDGER |

## Verification Pipeline (per-record state machine)

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| VP-001 | A single record resolves deterministically to exactly one of PASS/FAIL/UNSUPPORTED_HISTORICAL_FORMAT/CORRUPT | VERIFIED | `VERIFICATION_PIPELINE_MODEL.md`, `historical_verification.py` | Per-record only — genuinely separate from CH-001..005's cross-record claims, not yet composed with them. Scoped to `DecisionRecord`/`ExecutionAuditRecord` only. Not wired into `causal_history_verifier.py` itself, only into the two log readers' error messages (SE-004) | NOT IN LEDGER |

## Provenance Graph

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| PG-001 | The four record types' causal relationships form an explicit, checkable graph; direct edges are distinguished from transitively-composed ones | VERIFIED (as a formal model of existing checks, not new code) | `PROVENANCE_GRAPH_MODEL.md` | One edge (`PolicyDecisionRecord.module_id` → registration) is proven only by composing CH-004 + CH-003, never checked directly — documented as fragile if either check changes independently | NOT IN LEDGER |

## Named Gaps

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| GAP-001 | `KernelStateEnvelope.state_hash` can be recomputed from disk alone, with no live `KernelStateMachine` | NOT YET BUILT (genuinely open, no decision made) | `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` | "Path A" (persist raw derivation inputs) never attempted. Orthogonal to MB-001..004 — confirmed this session when a proposal that Mode B's completion "unlocks" this was checked and rejected as a category error | IN LEDGER (as Gap 1) |
| GAP-002 | Reset-generation disambiguation at the kernel/`DecisionRecord` level | VERIFIED / CLOSED | `test_reset_epoch_observability.py`, HC-002/HC-003's `generation_id` fields | Closed by the `generation_id` migration this session | IN LEDGER (as Gap 1b) |
| GAP-003 | Reset-generation disambiguation at the `ExecutionPolicyDecision.decision_hash` level | NOT YET BUILT (deliberately deferred, a documented tradeoff, not an oversight) | `decision_record_contract.py`'s own docstring | Deliberately not added, to avoid coupling the authorizer to kernel state — a considered tradeoff, revisitable if it ever matters in practice | IN LEDGER (as Gap 1b) |
| GAP-004 | Python dependency versions are pinned | VERIFIED / CLOSED | `requirements.txt` | — | IN LEDGER (as Gap 3) |

## Repository Reproducibility

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| RR-001 | A fresh clone, plus one documented manual build step, reproduces the full passing suite | VERIFIED | Manual verification, cited in `PHOENIX_VERIFICATION_STATE.md` | Does not confirm zero-manual-step reproducibility | IN LEDGER |

## Cold Boot Reconstruction

| ID | Claim | Status | Evidence | Boundary | Ledger Reference |
|---|---|---|---|---|---|
| CB-001 | Registration, authorization, and execution histories reconstruct from disk alone, with verified ordering and causal relationships | VERIFIED | `cold_boot_reconstruction.py`, `test_cold_boot_reconstruction.py`, 11/11, each test mapped to a `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` clause | Only 3 histories — not extended to include `PolicyDecisionRecord` as a 4th (separate, not-yet-built work; explicitly named at Gap 2's closure) | IN LEDGER |
| CB-002 | Canonical replay verification (single-generation) via the combined cold-boot entry point | VERIFIED | `cold_boot_replay_extension.py`, `test_cold_boot_replay_integration.py` | This is the same underlying mechanism as MB-001, accessed via `reconstruct_cold_boot_with_replay()` rather than Mode B's segmentation pipeline — not independent coverage, a second entry point onto the same claim | IN LEDGER |

---

## What this matrix makes visible

Counting `NOT IN LEDGER` rows above: **SE-001 through SE-004, VP-001, and PG-001 — six claims, each with real evidence, none represented in `PHOENIX_VERIFICATION_STATE.md`.** (DA-001 was checked during review and confirmed already present in the ledger, just unlabeled — not part of this count.) This is exactly the staleness this document was built to expose as data rather than as something I have to remember to mention. It does not fix the ledger. Whether to fold these six into `PHOENIX_VERIFICATION_STATE.md`, leave them living only here, or restructure the ledger around this matrix instead is a decision for whoever reads this row count, not resolved by writing it down.

## Explicitly out of scope for this document

- No new code. No new tests. Every VERIFIED row above cites evidence that already existed before this document was written.
- No claim about commercial applicability, governance suitability, or any use case beyond what each individual claim states.
- No resolution of the six `NOT IN LEDGER` rows — named, not fixed.
- No adversarial testing yet — this matrix is the prerequisite for that, not a substitute for it. An adversarial suite should target these rows specifically, once this enumeration is confirmed complete and accurate.

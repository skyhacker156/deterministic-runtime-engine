# ARCHITECTURE_FREEZE_v1.5.md

**Status:** Frozen
**As of tag:** `v1.5-audit-chain-replay`
**Scope:** deterministic-runtime-engine (Phoenix A)

## Purpose

This document is a constitution, not a changelog. It exists to answer one
question for any future change: *does this preserve what was already proven,
or does it silently replace it?*

The original architectural failure this project recovered from was not a bug.
It was an unreviewed rewrite that changed class names, hash algorithms, and
control flow while presenting itself as compatible with the existing system.
Nothing in that rewrite was individually malicious or even obviously wrong —
it was simply never checked against what already existed before being trusted.

This document is the check. Any change that violates a section below must
either be rejected or must explicitly amend this document as part of the same
change — never silently.

---

## 1. Frozen Invariants

Each invariant below is backed by at least one specific, currently-passing
test. If a future change breaks the invariant, the named test will fail.
If a future change requires modifying the named test, that is a signal to
stop and re-read this document before proceeding — not to quietly patch
the assertion.

| Invariant | Enforced by |
|---|---|
| A `CoreExecutionFrame` with a mismatched `provenance_hash` is rejected before any state mutation occurs. | `test_corrupted_frame_integrity_rejected`, `test_state_integrity_error` paths in `test_deterministic_execution_engine.py` |
| Frame sequence IDs must be strictly monotonic and contiguous; duplicates and gaps are rejected. | `test_out_of_order_and_duplicate_sequence_rejection`, `test_non_monotonic_frame_execution_rejected` |
| Illegal kernel state transitions force `FAULTED` and raise `InvalidStateTransitionError`; they never leave the kernel in an ambiguous state. | `test_illegal_transition_auto_faults` |
| Administrative reset (`FAULTED` → `INITIALIZING`) clears sequence counters and fault reason. | `test_administrative_reset_clears_sequence_counters` |
| Identical input frame streams processed through independent engine instances produce bit-identical state hash chains. | `test_replay_equivalence_determinism`, `test_causal_chain_determinism_true_for_identical_dataset` |
| `ExecutionResult` rejects non-finite (`NaN`/`Inf`) output payloads, wrong shape, wrong dtype, and any `success`/`error_message` contradiction. | `test_execution_result_fuzz.py` (full file) |
| `ExecutionResult.module_hash` never includes wall-clock or otherwise non-deterministic values (e.g. `execution_latency_us`). | `test_fuzz_hash_independence_from_dict_insertion_order`; enforced structurally by the metric-filtering logic in `ExecutionResult.__post_init__` |
| A module reporting `success=False` via `ExecutionResult` faults the kernel; the engine does not silently continue past a reported module failure. | `test_module_failure_trips_kernel_into_faulted_state` |
| `ExecutionAuditRecord` is emitted once per frame that reaches module dispatch, references (not recomputes) `input_hash`/`output_hash`/`success` from existing upstream values, and is appended before any resulting fault is raised. | `test_audit_record_emitted_on_successful_frame`, `test_audit_record_captures_module_failure_before_raising` |
| The full audit hash chain — not just final output — reproduces identically across two independent full-pipeline replay passes on identical input. | `test_causal_chain_determinism_true_for_identical_dataset`, `test_two_independent_replay_passes_produce_identical_audit_hashes` |
| `KernelStateEnvelope.state_hash` is a structural/positional fingerprint (sequence position, frame count, kernel state) and is **not** content-sensitive; content sensitivity lives exclusively in the audit chain. | Documented explicitly in `FullPipelineReplaySummary`'s docstring and in `test_different_datasets_produce_different_audit_chains` |
| The Python (`phoenix_a_core.py`) and Rust (`phoenix_core_rs`) implementations of the Phoenix A step function are bit-identical across adversarial IEEE-754 fuzzing. | `test_differential_parity.py::TestDifferentialParity::test_bit_exact_parity_python_vs_rust` |
| `VentAdapter`'s stratified tensor packing gives every input channel guaranteed non-zero representation in the output tensor; no channel can be silently truncated away. | `test_property_channel_equity` in `test_vent_adapter_properties.py` |

---

## 2. Component Boundaries

Raw Telemetry
|
v
VentAdapterContract (vent_adapter_contract.py)
|
v
BridgeIntegrator (bridge_integrator_contract.py)
|
v [seam conversion — bridge's 3-slice frame -> kernel's 256-payload frame]
v
CoreExecutionFrame (execution_kernel_contract.py)
|
v
DeterministicOrderingBarrier (ordering_barrier.py)
|
v
DeterministicExecutionEngine (deterministic_execution_engine.py)
| - owns: KernelStateMachine, integrity checks, sequencing, fault transitions
| - dispatches to: registered ExecutionModule
| - emits: ExecutionAuditRecord per frame (observational only)
v
ExecutionModule (Protocol) (execution_module_contract.py)
|
v
PhoenixAExecutionModule (phoenix_a_execution_module.py)
|
v
ExecutionResult (execution_module_contract.py)
|
v
ExecutionAuditRecord (execution_audit_contract.py)

**Key structural fact worth naming explicitly:** two distinct `CoreExecutionFrame`
classes exist in this codebase — one in `bridge_integrator_contract.py` (three
named slices: `ph_slice`, `seismic_slice`, `temp_slice`) and one in
`execution_kernel_contract.py` (single 256-element `payload`). These are not
interchangeable. Any code that treats them as the same type is a bug. The
conversion between them (`_bridge_frame_to_kernel_frame` in `replay_engine.py`)
is the only sanctioned seam.

---

## 3. Forbidden Dependencies

- **The engine does not import narrative or doctrine material.** No component
  under active execution (`deterministic_execution_engine.py`,
  `execution_kernel_state.py`, `execution_module_contract.py`) may depend on
  anything from the wider Sentinel corpus (governance frameworks, badge
  systems, ridge geometry, doctrine documents). Those remain a separate,
  unverified track and must stay structurally isolated from this runtime.
- **Contracts do not import the engine.** `execution_kernel_contract.py`,
  `execution_module_contract.py`, and `execution_audit_contract.py` are pure
  data/validation layers. None may import `deterministic_execution_engine.py`.
  Dependency flows one direction: contracts → engine, never engine → contracts
  in a way that creates a cycle.
- **A future external verifier must not import `deterministic_execution_engine.py`
  or any other control-flow module.** It may import the contract files
  (`execution_kernel_contract.py`, `execution_audit_contract.py`) to reuse
  their hash functions rather than reimplementing them — reimplementation
  risks silent drift between two independent hash schemes, which is exactly
  the failure class this project already recovered from once. The forbidden
  boundary is specifically *engine control flow*, not *contracts*.
- **No component may reconstruct or reinterpret a hash.** Every hash
  comparison in this codebase must call the producing object's own hash
  method or reference an already-computed hash value. No module recomputes
  another module's hash using its own parallel implementation.
- **`phoenix_core_rs/target/` and `.pytest_cache/` are never committed.**
  Build artifacts are reproduced locally via `cargo build --release`, not
  version-controlled.

---

## 4. Replay Guarantees

- Given an identical ordered stream of valid `CoreExecutionFrame` instances,
  two independent `DeterministicExecutionEngine` instances produce identical
  `KernelStateEnvelope.state_hash` sequences and identical
  `ExecutionResult.module_hash` sequences.
- Given an identical binary telemetry log file, two independent full-pipeline
  replay passes (`ReplayEngine.execute_full_pipeline_replay`) produce an
  identical `audit_hashes` tuple.
- Frame arrival order may be scrambled prior to the `DeterministicOrderingBarrier`;
  the barrier's output order is always strictly monotonic regardless of
  arrival order, and downstream determinism holds on the barrier's output,
  not on raw arrival order.
- Wall-clock time, execution latency, and any other non-deterministic runtime
  measurement are permitted to exist as informational metadata but are never
  permitted inside any hash computation.

---

## 5. Audit Guarantees

- Every frame that reaches module dispatch (i.e., a module is registered and
  is actually called) produces exactly one `ExecutionAuditRecord`, appended to
  `DeterministicExecutionEngine.audit_log`, regardless of whether the module
  reports success or failure.
- No `ExecutionAuditRecord` field is independently computed by the audit
  layer from raw data; every field is a direct reference to a hash or value
  already produced by an upstream component (`CoreExecutionFrame.provenance_hash`,
  `KernelStateEnvelope.state_hash`, `ExecutionResult.module_hash`,
  `ExecutionResult.success`, `ExecutionResult.error_message`).
- The audit layer is strictly observational: removing audit emission from
  `process_frame` must not change any pre-existing execution, sequencing, or
  fault behavior. (This is why `test_engine_audit_integration.py` is a
  separate file from the pre-existing engine tests — the pre-existing suite
  passing unchanged after Step 2's wiring was the actual proof of this
  property, not a separate assertion.)
- If a module raises an unhandled exception (rather than returning a graceful
  `ExecutionResult(success=False, ...)`), **no audit record is currently
  emitted** for that frame. This is a known, deliberate scope boundary of
  v1.5, not an oversight — extending audit coverage to unhandled-exception
  paths is a valid future change, but must be made explicitly and update this
  document when it happens.

---

## 6. Version Tag History

| Tag | What it certifies |
|---|---|
| `v1.0-verified` | Recovery from an unreviewed architectural rewrite confirmed complete; core pipeline reproducible from a fresh clone. |
| `v1.1-cleaned` | 53/53 tests passing; superseded kernel design (`SentinelExecutionKernel`) archived, not deleted; `ExecutionContext` hash-chaining completed. |
| `v1.2-ci-verified` | GitHub Actions CI live: fast suite runs on every push/PR; longevity benchmark separated into a nightly/manual workflow. |
| `v1.3-audit-contract` | `ExecutionAuditRecord` exists as a standalone, deterministic, fuzz-tested contract. No engine integration yet. |
| `v1.4-audit-integrated` | Engine emits one audit record per dispatched frame, observationally, without altering existing control flow. |
| `v1.5-audit-chain-replay` | Full pipeline replay (adapter → bridge → kernel engine) verifies the entire audit hash chain reproduces across independent passes, not just final output. **This document reflects the state as of this tag.** |

---

## 7. Amendment Rule

This document may only be amended as part of a commit that also changes the
code it describes. A change to the architecture without a corresponding
change to this document — or a change to this document without corresponding
code — is itself a violation of what this document exists to prevent.

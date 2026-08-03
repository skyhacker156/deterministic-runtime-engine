# execution_module_spec.md

**Status:** Normative
**Applies to:** any class implementing `ExecutionModule` (execution_module_contract.py)
**Governing document:** ARCHITECTURE_FREEZE_v1.5.md, Section 3

## Purpose

This document defines the contract every `ExecutionModule` implementation
must satisfy to be dispatched by `DeterministicExecutionEngine`. It exists
so that adding new domain logic never requires trusting a new module by
inspection — trust is established by passing the compliance harness
(`test_module_contract_compliance.py`), not by review alone.

The extension rule inherited directly from ARCHITECTURE_FREEZE_v1.5.md §3:

> No component reconstructs another component's hash.

Every rule below is a specific application of that one rule, or of the
audit and determinism guarantees already frozen in that document.

## Interface

```python
class ExecutionModule(Protocol):
    @property
    def module_id(self) -> str: ...

    def execute(
        self,
        frame: CoreExecutionFrame,
        envelope: KernelStateEnvelope,
    ) -> ExecutionResult: ...
```

### Required inputs

- `frame: CoreExecutionFrame` — the kernel's single-payload frame
  (`execution_kernel_contract.py`). Already integrity-verified by the engine
  before `execute()` is called; a module never needs to re-verify
  `frame.provenance_hash`.
- `envelope: KernelStateEnvelope` — the kernel's state snapshot immediately
  prior to this frame's execution. Frozen; read-only by construction.

### Required output

- `ExecutionResult` (`execution_module_contract.py`), constructed via its
  normal `__post_init__` path — never hand-assembled to bypass its
  shape/dtype/finiteness/consistency checks.

## Required Guarantees

Every module must:

1. **Be deterministic.** Identical `(frame, envelope)` input must produce an
   `ExecutionResult` with an identical `module_hash` on every call, on every
   machine. No module may read wall-clock time, random state, or any
   external I/O into a value that ends up hashed.

2. **Produce finite outputs.** `output_payload` must contain no `NaN` or
   `Inf` values. This is already enforced structurally by
   `ExecutionResult.__post_init__` — a module cannot construct a
   non-finite `ExecutionResult` even if it tries. A compliant module should
   never rely on that backstop catching a bug; it should guard against
   non-finite intermediate values itself (see the near-zero-norm guard in
   `PhoenixAExecutionModule` as a reference pattern).

3. **Preserve sequence ordering.** A module never reorders, buffers, or
   defers frames across calls. Each `execute()` call is a pure function of
   the single frame and envelope it receives — sequencing is the engine's
   and ordering barrier's responsibility, not the module's.

4. **Not mutate kernel state.** A module must not attempt to modify
   `envelope` (`KernelStateEnvelope` is frozen; an attempted assignment
   raises `FrozenInstanceError` by construction) or hold a persistent
   reference to kernel-owned mutable state between calls.

5. **Not calculate another component's hash.** A module may *read* any
   hash passed to it (`frame.provenance_hash`, `envelope.state_hash`) but
   must never independently recompute one. The only hash a module is
   responsible for producing is its own output fingerprint, and that
   happens automatically via `ExecutionResult.module_hash` — a module
   never assigns or overrides `module_hash` directly.

6. **Not bypass audit emission.** A module has no mechanism to prevent or
   alter the engine's emission of an `ExecutionAuditRecord` for its own
   invocation — this is enforced by the engine, not the module, but a
   compliant module must never attempt to catch and suppress the engine's
   post-execution audit step (e.g. by raising an exception type designed
   to unwind past it).

## Known Boundary

Per ARCHITECTURE_FREEZE_v1.5.md §5: if a module raises an unhandled
exception instead of returning `ExecutionResult(success=False, ...)`, no
audit record is currently emitted for that frame. A compliant module
**should** prefer returning a graceful failure result over raising, both
because it's easier to reason about and because it keeps that frame inside
the audit trail. Modules are not currently required to guarantee they never
raise — that would need engine-side handling this document does not yet
specify — but graceful failure is the preferred, audited path.

## Compliance

A module is considered compliant only when it passes every test in
`test_module_contract_compliance.py`, parameterized against that module.
Passing this specification by inspection is not sufficient — the harness
is the actual gate.

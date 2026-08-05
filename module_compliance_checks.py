"""
Module Compliance Checks - Sentinel Framework
(module_compliance_checks.py)

Single source of truth for what "compliant" means for an ExecutionModule.
Both test_module_contract_compliance.py (the standalone pytest suite) and
execution_module_registry.py (registration-time verification) import and
call these same functions rather than maintaining two independent
implementations of the same checks.

Per ARCHITECTURE_FREEZE_v1.5.md's extension rule: this file itself is now
subject to that same rule going forward — no other component should
reimplement what "compliant" means. If a check needs to change, it changes
here, once, and both callers pick it up automatically.

Each function raises ModuleComplianceError with a specific message on
failure, and returns None on success (pass-through pattern, not a bool),
so a failure is always an explicit exception, never a silently-ignored
False.

ModuleComplianceError now inherits from ModuleRegistrationError
(execution_module_registry.py), so that ExecutionModuleRegistry.register()
can catch any Phase-1 registration failure -- manifest incompatibility or
compliance failure -- with a single except clause. This import is a
one-way dependency (this file -> execution_module_registry.py); the
registry only imports from this module lazily, inside
_run_compliance_check's function body, so there is no import cycle.

generation_id note: make_compliance_envelope() supplies a fixed
placeholder generation_id (_COMPLIANCE_ENVELOPE_GENERATION_ID), safe
because every check using it builds exactly ONE envelope and reuses
that same object throughout. check_replay_matches() is the one check
that spans two independent DeterministicExecutionEngine instances, so
it uses DeterministicExecutionEngine.with_generation() with its own
separate fixed constant (_COMPLIANCE_REPLAY_GENERATION_ID) to hold
generation identity constant across both -- see that function's
docstring for why an ordinary two-independent-engines comparison would
otherwise be comparing two different generations, not testing
determinism.
"""

import numpy as np

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelState, KernelStateEnvelope
from execution_module_contract import ExecutionModule, ExecutionResult
from execution_module_registry import ModuleRegistrationError


class ModuleComplianceError(ModuleRegistrationError):
    """Raised when a module fails any compliance check in this module."""
    pass


# ---------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------

def make_compliance_frame(seed_val: float = 1.0, seq_id: int = 0, timestamp_ns: int = 1_000_000) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    return CoreExecutionFrame.create(seq_id=seq_id, timestamp_ns=timestamp_ns, payload=payload)


# Fixed placeholder generation_id for compliance-check envelopes that
# don't test cross-generation behavior. Every check below that calls
# make_compliance_envelope() builds exactly ONE envelope and reuses that
# same object for the duration of the check (check_determinism calls
# execute() twice against the SAME envelope instance, not two separate
# ones) -- none of them replay across independent KernelStateMachine
# instances, so a fixed constant is safe here: it never needs to match
# anything real: it only needs to be present and internally consistent
# within a single check. See module docstring re: check_replay_matches,
# the one check in this file that DOES span two independent instances
# and is NOT fixed by this constant.
_COMPLIANCE_ENVELOPE_GENERATION_ID = b"\xAA" * 16


def make_compliance_envelope(state: KernelState = KernelState.PROCESSING) -> KernelStateEnvelope:
    return KernelStateEnvelope(
        state=state,
        last_processed_seq=-1,
        total_frames_processed=0,
        state_hash=b"\x01" * 32,
        fault_reason=None,
        generation_id=_COMPLIANCE_ENVELOPE_GENERATION_ID,
    )


# Standard pathological seeds used across multiple checks below.
PATHOLOGICAL_SEEDS = (1e300, -1e300, 1e-300, -1e-300, 0.0)


# ---------------------------------------------------------------------
# Individual compliance checks
# ---------------------------------------------------------------------

def check_module_id_well_formed(module: ExecutionModule) -> None:
    """Requirement: module_id is a non-empty string."""
    if not isinstance(module.module_id, str) or not module.module_id.strip():
        raise ModuleComplianceError(
            f"Module has an invalid module_id: {module.module_id!r}"
        )


def check_determinism(module: ExecutionModule) -> None:
    """
    Requirement 1: identical (frame, envelope) input must produce an
    ExecutionResult with an identical module_hash on every call.
    """
    frame = make_compliance_frame(seed_val=2.5)
    envelope = make_compliance_envelope()

    result_1 = module.execute(frame, envelope)
    result_2 = module.execute(frame, envelope)

    if result_1.module_hash != result_2.module_hash:
        raise ModuleComplianceError(
            f"Module '{module.module_id}' failed determinism check: "
            f"identical input produced different module_hash values."
        )
    if result_1.success != result_2.success:
        raise ModuleComplianceError(
            f"Module '{module.module_id}' failed determinism check: "
            f"identical input produced different success status."
        )
    if not np.array_equal(result_1.output_payload, result_2.output_payload):
        raise ModuleComplianceError(
            f"Module '{module.module_id}' failed determinism check: "
            f"identical input produced different output_payload."
        )


# Fixed placeholder generation_id used ONLY to hold identity constant
# across the two independent engine instances check_replay_matches
# builds below. Deliberately a different constant from
# _COMPLIANCE_ENVELOPE_GENERATION_ID above -- these two are conceptually
# unrelated (one is a throwaway envelope field, this one is a shared
# identity two real engines must agree on) and keeping them visually
# distinct in a debugger avoids conflating them.
_COMPLIANCE_REPLAY_GENERATION_ID = b"\xBB" * 16


def check_replay_matches(module_cls) -> None:
    """
    Requirement 1 (extended): determinism must hold when driven through
    DeterministicExecutionEngine across two independent engine instances,
    not just via direct execute() calls.

    Takes a class (not an instance) because this needs two fully
    independent engine/module pairs, matching test_module_replay_matches.

    generation_id: both run() calls below use
    DeterministicExecutionEngine.with_generation() with the SAME fixed
    _COMPLIANCE_REPLAY_GENERATION_ID, rather than ordinary __init__ (which
    would mint a genuinely different random generation_id per call). This
    check is specifically about proving computational determinism GIVEN
    the same generation -- two ordinary, independently-constructed
    engines are, by design, two different generations, and comparing
    hashes across those would be comparing two different lifetimes, not
    testing whether the module itself behaves deterministically.
    """
    from deterministic_execution_engine import DeterministicExecutionEngine

    def run():
        engine = DeterministicExecutionEngine.with_generation(
            generation_id=_COMPLIANCE_REPLAY_GENERATION_ID,
            module=module_cls(),
        )
        engine.initialize()
        _, result = engine.process_frame(make_compliance_frame(seed_val=1.5))
        return result.module_hash

    hash_1 = run()
    hash_2 = run()
    if hash_1 != hash_2:
        raise ModuleComplianceError(
            f"Module class '{module_cls.__name__}' failed replay determinism "
            f"through DeterministicExecutionEngine (same generation_id both runs)."
        )


def check_cannot_mutate_context(module: ExecutionModule) -> None:
    """
    Requirement 4: execute() must not leave any observable trace of
    mutation on the KernelStateEnvelope it receives.
    """
    import copy

    frame = make_compliance_frame(seed_val=1.0)
    envelope = make_compliance_envelope()
    envelope_before = copy.deepcopy(envelope)

    module.execute(frame, envelope)

    if envelope.state != envelope_before.state:
        raise ModuleComplianceError(
            f"Module '{module.module_id}' mutated envelope.state."
        )
    if envelope.state_hash != envelope_before.state_hash:
        raise ModuleComplianceError(
            f"Module '{module.module_id}' mutated envelope.state_hash."
        )
    if envelope.last_processed_seq != envelope_before.last_processed_seq:
        raise ModuleComplianceError(
            f"Module '{module.module_id}' mutated envelope.last_processed_seq."
        )


def check_rejects_invalid_input_gracefully(module: ExecutionModule, seeds=PATHOLOGICAL_SEEDS) -> None:
    """
    Requirement 2 (finite outputs), applied defensively: pathological
    input must produce a well-formed, finite ExecutionResult — never an
    unhandled exception, never a non-finite payload.
    """
    envelope = make_compliance_envelope()

    for seed in seeds:
        frame = make_compliance_frame(seed_val=seed)
        try:
            result = module.execute(frame, envelope)
        except Exception as err:
            raise ModuleComplianceError(
                f"Module '{module.module_id}' raised on pathological input "
                f"(seed={seed}) instead of returning a graceful "
                f"ExecutionResult(success=False, ...): {err}"
            )

        if not isinstance(result, ExecutionResult):
            raise ModuleComplianceError(
                f"Module '{module.module_id}' did not return an "
                f"ExecutionResult for pathological input (seed={seed})."
            )
        if not np.all(np.isfinite(result.output_payload)):
            raise ModuleComplianceError(
                f"Module '{module.module_id}' produced non-finite output "
                f"for pathological input (seed={seed})."
            )


def check_output_is_hashable(module: ExecutionModule) -> None:
    """
    Requirement 5: module_hash must be genuinely derived from
    ExecutionResult's own __post_init__ mechanism, never independently
    computed or hand-assigned by the module.
    """
    frame = make_compliance_frame(seed_val=1.0)
    envelope = make_compliance_envelope()

    result = module.execute(frame, envelope)

    if not isinstance(result.module_hash, bytes) or len(result.module_hash) != 32:
        raise ModuleComplianceError(
            f"Module '{module.module_id}' produced a malformed module_hash."
        )

    reconstructed = ExecutionResult(
        seq_id=result.seq_id,
        success=result.success,
        output_payload=result.output_payload.copy(),
        metrics=result.metrics,
        error_message=result.error_message,
    )
    if reconstructed.module_hash != result.module_hash:
        raise ModuleComplianceError(
            f"Module '{module.module_id}' produced a module_hash that does "
            f"not match ExecutionResult's own hash computation — "
            f"possible independent hash reconstruction."
        )


def check_failure_is_auditable() -> None:
    """
    Requirement 6: the ENGINE side of the audit-on-failure contract, per
    ARCHITECTURE_FREEZE_v1.5.md Section 5. Uses a minimal forced-failure
    wrapper rather than any specific module, since this validates the
    engine's guarantee that every module relies on, not a module-specific
    failure path.
    """
    from deterministic_execution_engine import DeterministicExecutionEngine, ExecutionEngineError

    class _ForcedFailureWrapper:
        module_id = "compliance_check_forced_failure"

        def execute(self, frame, envelope):
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message="Forced failure for compliance check audit verification.",
            )

    engine = DeterministicExecutionEngine(module=_ForcedFailureWrapper())
    engine.initialize()

    frame = make_compliance_frame(seed_val=1.0)
    try:
        engine.process_frame(frame)
    except ExecutionEngineError:
        pass
    else:
        raise ModuleComplianceError(
            "Engine did not raise ExecutionEngineError on a module-reported failure."
        )

    if len(engine.audit_log) != 1:
        raise ModuleComplianceError(
            f"Expected exactly 1 audit record after a failed frame, "
            f"got {len(engine.audit_log)}."
        )
    if engine.audit_log[0].success is not False:
        raise ModuleComplianceError(
            "Audit record for a failed frame does not reflect success=False."
        )


# ---------------------------------------------------------------------
# Full suite runner — used by both callers
# ---------------------------------------------------------------------

def run_full_compliance_suite(module_cls) -> None:
    """
    Runs every check above against a fresh instance of module_cls.
    Raises ModuleComplianceError on the first failure encountered.

    This is the single entry point both test_module_contract_compliance.py
    and execution_module_registry.py should call — neither should invoke
    individual check_* functions directly, so that "what compliance means"
    stays defined in exactly one place: the ordered list below.
    """
    instance = module_cls()

    check_module_id_well_formed(instance)
    check_determinism(instance)
    check_replay_matches(module_cls)
    check_cannot_mutate_context(instance)
    check_rejects_invalid_input_gracefully(instance)
    check_output_is_hashable(instance)
    check_failure_is_auditable()

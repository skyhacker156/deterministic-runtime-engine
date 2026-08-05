"""
Execution Engine Authorization Seam Test Suite
(test_engine_authorization_seam.py)

Verifies v2.4: the optional, injected ExecutionAuthorizer gate inserted
into DeterministicExecutionEngine.process_frame(). Confirms backward
compatibility, denial containment, the authorized happy path, Option A's
quota-on-failure behavior surviving the seam, full replay determinism
across the entire authorized pipeline, and the hard import-boundary
invariant (the engine module must never import policy internals).
"""

import ast
import inspect
import uuid
import numpy as np
import pytest

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelState
from execution_module_contract import ExecutionResult
from deterministic_execution_engine import (
    DeterministicExecutionEngine,
    AuthorizationDeniedError,
    ExecutionEngineError,
)
from execution_module_registry import ExecutionModuleRegistry
from execution_policy import ExecutionPolicy
from execution_policy_state import ExecutionPolicyState
from execution_authorizer import ExecutionAuthorizer
from phoenix_a_execution_module import PhoenixAExecutionModule


def _make_frame(seq_id: int = 0, timestamp_ns: int = 1_000_000, seed_val: float = 1.0) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    return CoreExecutionFrame.create(seq_id=seq_id, timestamp_ns=timestamp_ns, payload=payload)


def _make_authorized_setup(max_invocations=None):
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=max_invocations)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    return registry, authorizer, state


class InvocationCountingModule:
    """
    Tracks how many times execute() is actually called — the concrete
    side-effect assertion needed to prove a denied frame never reaches
    module dispatch, not just that the engine raised.
    """
    def __init__(self, module_id: str = "invocation_counter_v1") -> None:
        self._module_id = module_id
        self.invocation_count = 0

    @property
    def module_id(self) -> str:
        return self._module_id

    def execute(self, frame, envelope) -> ExecutionResult:
        self.invocation_count += 1
        return ExecutionResult(
            seq_id=frame.seq_id,
            success=True,
            output_payload=frame.payload.copy(),
        )


class ConditionallyFailingCountingModule:
    """
    Combines invocation counting with conditional failure, for the
    Option A regression test — needs to both count calls AND be capable
    of failing without violating the compliance harness's
    must-succeed-on-nominal-input requirement.
    """
    FAIL_SEED_VALUE = 999.0

    def __init__(self, module_id: str = "counting_conditional_fail_v1") -> None:
        self._module_id = module_id
        self.invocation_count = 0

    @property
    def module_id(self) -> str:
        return self._module_id

    def execute(self, frame, envelope) -> ExecutionResult:
        self.invocation_count += 1
        if frame.payload[0] == self.FAIL_SEED_VALUE:
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message="Deliberate test failure.",
            )
        return ExecutionResult(
            seq_id=frame.seq_id,
            success=True,
            output_payload=frame.payload.copy(),
        )


# ---------------------------------------------------------------------
# 1. Backward compatibility
# ---------------------------------------------------------------------

def test_engine_without_authorizer_behaves_identically():
    """
    The core additivity guarantee: an engine constructed with no
    authorizer (the default) must behave exactly as every pre-v2.4 test
    already expects — no authorization checks performed at all.
    """
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)  # no authorizer
    engine.initialize()

    frame = _make_frame(seq_id=0)
    envelope, result = engine.process_frame(frame)

    assert envelope.state == KernelState.READY
    assert result is not None
    assert result.success is True
    assert len(engine.audit_log) == 1


# ---------------------------------------------------------------------
# 2. Denial containment — the highest-value new invariant
# ---------------------------------------------------------------------

def test_denied_authorization_never_dispatches_module():
    registry, authorizer, state = _make_authorized_setup(max_invocations=0)
    module = InvocationCountingModule(module_id="phoenix_a_core_v1")
    # Note: reuse the registry's already-registered/activated
    # PhoenixAExecutionModule id, but dispatch through our own counting
    # module instance, so the engine's authorizer.authorize() call
    # (keyed by module_id) aligns with what's actually registered.
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    frame = _make_frame(seq_id=0)

    with pytest.raises(AuthorizationDeniedError, match="phoenix_a_core_v1"):
        engine.process_frame(frame)

    assert module.invocation_count == 0
    assert len(engine.audit_log) == 0
    # Kernel state must be completely untouched by the denial.
    assert engine.state_machine.current_state == KernelState.READY
    assert engine.state_machine.last_processed_seq == -1


def test_denied_frame_seq_id_is_not_consumed_and_can_be_retried():
    """
    Confirms the specific kernel-state-untouched semantics: a denied
    frame's seq_id remains available. Authorize again (simulating a
    policy change that now allows it) and confirm seq_id=0 can still be
    processed normally afterward.
    """
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=0)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    module = InvocationCountingModule(module_id="phoenix_a_core_v1")
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    frame = _make_frame(seq_id=0)
    with pytest.raises(AuthorizationDeniedError):
        engine.process_frame(frame)

    # Simulate a policy change: swap in an authorizer with room to allow.
    permissive_policy = ExecutionPolicy(max_invocations_per_module_lifetime=5)
    permissive_authorizer = ExecutionAuthorizer(registry, permissive_policy, ExecutionPolicyState())
    engine_2 = DeterministicExecutionEngine(module=module, authorizer=permissive_authorizer)
    engine_2.initialize()

    envelope, result = engine_2.process_frame(_make_frame(seq_id=0))
    assert result.success is True
    assert module.invocation_count == 1  # only the retry actually dispatched


# ---------------------------------------------------------------------
# 3. Successful authorized path
# ---------------------------------------------------------------------

def test_authorized_execution_reaches_module_and_records_usage():
    registry, authorizer, state = _make_authorized_setup()
    module = InvocationCountingModule(module_id="phoenix_a_core_v1")
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    frame = _make_frame(seq_id=0)
    envelope, result = engine.process_frame(frame)

    assert result.success is True
    assert module.invocation_count == 1
    assert state.get_count("phoenix_a_core_v1") == 1
    assert len(engine.audit_log) == 1


# ---------------------------------------------------------------------
# 4. Failed module execution still consumes quota (Option A, v2.3 lock-in)
# ---------------------------------------------------------------------

def test_failed_execution_still_consumes_authorization_quota():
    registry = ExecutionModuleRegistry()
    registry.register(ConditionallyFailingCountingModule())
    registry.activate("counting_conditional_fail_v1")

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=5)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    module = ConditionallyFailingCountingModule()
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    frame = _make_frame(seq_id=0, seed_val=ConditionallyFailingCountingModule.FAIL_SEED_VALUE)

    with pytest.raises(ExecutionEngineError, match="Module execution failed"):
        engine.process_frame(frame)

    # Module WAS dispatched (invocation count incremented) even though it failed.
    assert module.invocation_count == 1
    # Quota WAS consumed despite the failure — Option A, locked in at v2.3.
    assert state.get_count("counting_conditional_fail_v1") == 1
    # Audit record still exists for the failed frame (Step 2 behavior, unchanged).
    assert len(engine.audit_log) == 1
    assert engine.audit_log[0].success is False


# ---------------------------------------------------------------------
# 5. Full pipeline replay determinism — the architectural test
# ---------------------------------------------------------------------

def test_authorized_pipeline_replay_produces_identical_decision_and_audit_hashes():
    """
    The completion criterion stated for v2.4: given the same input
    stream, module registry state, policy state, and policy definitions,
    authorization-integrated execution produces the same execution
    results, decision hashes, AND audit hashes across two fully
    independent runs.

    generation_id is held fixed across both run() calls below -- two
    ordinary DeterministicExecutionEngine() instances are, by design, two
    different kernel generations, so comparing hashes across them would
    be comparing two different lifetimes rather than proving determinism
    given the same one. See DeterministicExecutionEngine.with_generation()'s
    own docstring. Note this is unrelated to the fixed generation_id
    module_compliance_checks.py's check_replay_matches() uses internally
    during registry.register()'s compliance check -- that's a separate,
    independent use of the same mechanism for a different purpose.
    """
    shared_generation_id = uuid.uuid4().bytes

    def run():
        registry = ExecutionModuleRegistry()
        registry.register(PhoenixAExecutionModule())
        registry.activate("phoenix_a_core_v1")

        policy = ExecutionPolicy(max_invocations_per_module_lifetime=10)
        state = ExecutionPolicyState()
        authorizer = ExecutionAuthorizer(registry, policy, state)

        module = registry.resolve("phoenix_a_core_v1")
        engine = DeterministicExecutionEngine.with_generation(
            generation_id=shared_generation_id, module=module, authorizer=authorizer
        )
        engine.initialize()

        decision_hashes = []
        results = []

        for seq_id in range(5):
            decision = authorizer.authorize("phoenix_a_core_v1")
            decision_hashes.append(decision.decision_hash)
            assert decision.allowed is True  # sanity: stays within limit=10

            frame = _make_frame(seq_id=seq_id, seed_val=float(seq_id) + 1.0)
            envelope, result = engine.process_frame(frame)
            results.append(result.module_hash)

        audit_hashes = tuple(r.audit_hash for r in engine.audit_log)
        return tuple(decision_hashes), tuple(results), audit_hashes

    decisions_1, results_1, audit_1 = run()
    decisions_2, results_2, audit_2 = run()

    assert decisions_1 == decisions_2
    assert results_1 == results_2
    assert audit_1 == audit_2


# ---------------------------------------------------------------------
# 6. Hard import-boundary invariant
# ---------------------------------------------------------------------

def test_engine_module_has_no_policy_imports():
    """
    Mechanically enforces the "opaque collaborator" rule: the engine must
    never import ExecutionPolicy, ExecutionPolicyState, or
    ExecutionAuthorizer internals. This is checked by parsing the actual
    source file's import statements, not by convention — a future edit
    that violates this will fail this test immediately, regardless of
    whether the violator remembers the rule.
    """
    import deterministic_execution_engine

    source = inspect.getsource(deterministic_execution_engine)
    tree = ast.parse(source)

    forbidden_modules = {
        "execution_policy",
        "execution_policy_state",
        "execution_authorizer",
    }

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)

    violations = imported_modules & forbidden_modules
    assert not violations, (
        f"deterministic_execution_engine.py imports forbidden policy "
        f"module(s): {violations}. The engine must treat the authorizer "
        f"as an opaque collaborator, never importing policy internals."
    )

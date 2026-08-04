"""
Execution Authorization Integration Test Suite
(test_execution_authorization_integration.py)

Bridges ExecutionAuthorizer to actual module dispatch WITHOUT modifying
DeterministicExecutionEngine. Proves the authorize() -> dispatch ->
record_execution() flow is coherent on its own, before any engine wiring.

Quota accounting policy (resolved): Option A — authorized executions
consume budget regardless of module outcome. record_execution() is called
once dispatch occurs, whether the module reports success or failure.

Design note discovered while building this suite: the compliance harness
(module_compliance_checks.py) requires every registered module to succeed
on nominal input during check_determinism/check_replay_matches. An
unconditionally-failing module can never pass registration. This means
"a failing module," in this system, can only mean "fails under specific
runtime conditions" — never "fails on every call." ConditionallyFailingModule
below reflects that constraint: it succeeds on nominal compliance-check
input and only fails when given a specific marker payload value.
"""

import pytest

from execution_authorizer import ExecutionAuthorizer, RecordExecutionError
from execution_policy import ExecutionPolicy
from execution_policy_state import ExecutionPolicyState
from execution_module_registry import ExecutionModuleRegistry
from execution_kernel_contract import CoreExecutionFrame
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule


def _make_authorized_setup(max_invocations=None):
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=max_invocations)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    return registry, authorizer, state


def _make_frame(seq_id=0, seed_val=1.0):
    import numpy as np
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    return CoreExecutionFrame.create(seq_id=seq_id, timestamp_ns=1_000_000, payload=payload)


class ConditionallyFailingModule:
    """
    Succeeds on nominal input (required to pass registration compliance)
    but deliberately fails when given a frame whose payload matches
    FAIL_SEED_VALUE — used to test Option A's "failure still consumes
    quota" behavior without violating the compliance harness's
    "must be able to succeed" requirement.
    """
    FAIL_SEED_VALUE = 999.0

    @property
    def module_id(self) -> str:
        return "conditionally_fails_v1"

    def execute(self, frame, envelope):
        import numpy as np
        from execution_module_contract import ExecutionResult

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


def authorize_dispatch_record(registry, authorizer, module_id, frame):
    """
    The bridge under test: authorize -> (if allowed) dispatch via a
    standalone engine -> record_execution regardless of module outcome.
    Returns (decision, result_or_none).
    """
    decision = authorizer.authorize(module_id)
    if not decision.allowed:
        return decision, None

    module = registry.resolve(module_id)
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()

    result = None
    try:
        _, result = engine.process_frame(frame)
    except Exception:
        # A failed ExecutionResult currently causes the engine to raise
        # ExecutionEngineError rather than return a failed result — see
        # deterministic_execution_engine.py's process_frame(). Dispatch
        # still occurred, so quota is still consumed (Option A).
        pass
    finally:
        authorizer.record_execution(decision)

    return decision, result


def test_active_module_unlimited_policy_authorization_succeeds():
    registry, authorizer, state = _make_authorized_setup(max_invocations=None)
    decision = authorizer.authorize("phoenix_a_core_v1")
    assert decision.allowed is True


def test_active_module_exhausted_policy_authorization_fails():
    registry, authorizer, state = _make_authorized_setup(max_invocations=1)
    frame = _make_frame(seq_id=0)

    decision_1, _ = authorize_dispatch_record(registry, authorizer, "phoenix_a_core_v1", frame)
    assert decision_1.allowed is True

    decision_2 = authorizer.authorize("phoenix_a_core_v1")
    assert decision_2.allowed is False
    assert decision_2.reason == "DENIED_RATE_LIMIT"


def test_allowed_decision_execution_proceeds():
    registry, authorizer, state = _make_authorized_setup()
    frame = _make_frame(seq_id=0)

    decision, result = authorize_dispatch_record(registry, authorizer, "phoenix_a_core_v1", frame)

    assert decision.allowed is True
    assert result is not None
    assert result.success is True


def test_denied_decision_never_reaches_dispatch():
    registry, authorizer, state = _make_authorized_setup(max_invocations=0)
    frame = _make_frame(seq_id=0)

    decision, result = authorize_dispatch_record(registry, authorizer, "phoenix_a_core_v1", frame)

    assert decision.allowed is False
    assert result is None
    assert state.get_count("phoenix_a_core_v1") == 0


def test_successful_execution_increments_quota():
    registry, authorizer, state = _make_authorized_setup()
    frame = _make_frame(seq_id=0)

    authorize_dispatch_record(registry, authorizer, "phoenix_a_core_v1", frame)

    assert state.get_count("phoenix_a_core_v1") == 1


def test_failed_module_execution_still_increments_quota():
    """
    Option A's core guarantee: a module that fails after being authorized
    and dispatched still consumes budget.
    """
    registry = ExecutionModuleRegistry()
    registry.register(ConditionallyFailingModule())
    registry.activate("conditionally_fails_v1")

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=5)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    frame = _make_frame(seq_id=0, seed_val=ConditionallyFailingModule.FAIL_SEED_VALUE)
    decision, result = authorize_dispatch_record(registry, authorizer, "conditionally_fails_v1", frame)

    assert decision.allowed is True
    assert state.get_count("conditionally_fails_v1") == 1


def test_repeated_failures_eventually_exhaust_quota():
    """
    Confirms Option A's protective property: a module that fails on every
    dispatched call is still subject to the rate limit, because failures
    consume budget the same as successes.
    """
    registry = ExecutionModuleRegistry()
    registry.register(ConditionallyFailingModule())
    registry.activate("conditionally_fails_v1")

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=3)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    for seq_id in range(3):
        frame = _make_frame(seq_id=seq_id, seed_val=ConditionallyFailingModule.FAIL_SEED_VALUE)
        decision, _ = authorize_dispatch_record(registry, authorizer, "conditionally_fails_v1", frame)
        assert decision.allowed is True

    final_decision = authorizer.authorize("conditionally_fails_v1")
    assert final_decision.allowed is False
    assert final_decision.reason == "DENIED_RATE_LIMIT"
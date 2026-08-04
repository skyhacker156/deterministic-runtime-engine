"""
Execution Authorizer Test Suite
(test_execution_authorizer.py)
"""

import pytest

from execution_authorizer import (
    ExecutionAuthorizer,
    ExecutionPolicyDecision,
    RecordExecutionError,
)
from execution_policy import ExecutionPolicy
from execution_policy_state import ExecutionPolicyState
from execution_module_registry import ExecutionModuleRegistry, ModuleNotFoundError, ModuleNotActiveError
from module_lifecycle import ModuleState
from phoenix_a_execution_module import PhoenixAExecutionModule


def _make_active_registry():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")
    return registry


def test_inactive_module_raises_not_active():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    authorizer = ExecutionAuthorizer(registry, ExecutionPolicy(), ExecutionPolicyState())

    with pytest.raises(ModuleNotActiveError):
        authorizer.authorize("phoenix_a_core_v1")


def test_unregistered_module_raises_not_found():
    registry = ExecutionModuleRegistry()
    authorizer = ExecutionAuthorizer(registry, ExecutionPolicy(), ExecutionPolicyState())

    with pytest.raises(ModuleNotFoundError):
        authorizer.authorize("does_not_exist")


def test_active_module_no_limit_is_allowed():
    registry = _make_active_registry()
    authorizer = ExecutionAuthorizer(registry, ExecutionPolicy(), ExecutionPolicyState())

    decision = authorizer.authorize("phoenix_a_core_v1")

    assert decision.allowed is True
    assert decision.reason == "ALLOWED"
    assert decision.observed_lifecycle_state == ModuleState.ACTIVE


# ---------------------------------------------------------------------
# The core correction: authorize() must not mutate state
# ---------------------------------------------------------------------

def test_authorize_does_not_increment_state():
    """The actual invariant this pass exists to enforce: calling
    authorize() any number of times, without recording execution, must
    never move the counter."""
    registry = _make_active_registry()
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, ExecutionPolicy(), state)

    authorizer.authorize("phoenix_a_core_v1")
    authorizer.authorize("phoenix_a_core_v1")
    authorizer.authorize("phoenix_a_core_v1")

    assert state.get_count("phoenix_a_core_v1") == 0


def test_record_execution_increments_state():
    registry = _make_active_registry()
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, ExecutionPolicy(), state)

    decision = authorizer.authorize("phoenix_a_core_v1")
    new_count = authorizer.record_execution(decision)

    assert new_count == 1
    assert state.get_count("phoenix_a_core_v1") == 1


def test_record_execution_on_denied_decision_raises():
    registry = _make_active_registry()
    policy = ExecutionPolicy(max_invocations_per_module_lifetime=0)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    decision = authorizer.authorize("phoenix_a_core_v1")
    assert decision.allowed is False

    with pytest.raises(RecordExecutionError, match="denied decision"):
        authorizer.record_execution(decision)

    # Confirm the failed record_execution() call didn't mutate state either.
    assert state.get_count("phoenix_a_core_v1") == 0


def test_module_denied_once_limit_reached_via_explicit_recording():
    registry = _make_active_registry()
    policy = ExecutionPolicy(max_invocations_per_module_lifetime=2)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    d1 = authorizer.authorize("phoenix_a_core_v1")
    authorizer.record_execution(d1)

    d2 = authorizer.authorize("phoenix_a_core_v1")
    authorizer.record_execution(d2)

    d3 = authorizer.authorize("phoenix_a_core_v1")  # should now be denied
    assert d3.allowed is False
    assert d3.reason == "DENIED_RATE_LIMIT"
    assert state.get_count("phoenix_a_core_v1") == 2


# ---------------------------------------------------------------------
# decision_hash determinism (unchanged logic, still worth confirming
# after the authorize()/record_execution() split)
# ---------------------------------------------------------------------

def test_identical_decision_inputs_produce_identical_decision_hash():
    registry = _make_active_registry()
    policy = ExecutionPolicy()
    capabilities = registry.capabilities("phoenix_a_core_v1")
    lifecycle_state = registry.lifecycle_state("phoenix_a_core_v1")

    decision_1 = ExecutionPolicyDecision(
        module_id="phoenix_a_core_v1", allowed=True, reason="ALLOWED",
        observed_lifecycle_state=lifecycle_state, policy_hash=policy.policy_hash,
        capability_snapshot_hash=capabilities.capability_hash,
        observed_invocation_count=1, max_allowed_invocations=None,
    )
    decision_2 = ExecutionPolicyDecision(
        module_id="phoenix_a_core_v1", allowed=True, reason="ALLOWED",
        observed_lifecycle_state=lifecycle_state, policy_hash=policy.policy_hash,
        capability_snapshot_hash=capabilities.capability_hash,
        observed_invocation_count=99, max_allowed_invocations=None,
    )

    assert decision_1.decision_hash == decision_2.decision_hash


def test_different_allowed_status_changes_hash():
    registry = _make_active_registry()
    policy = ExecutionPolicy()
    capabilities = registry.capabilities("phoenix_a_core_v1")
    lifecycle_state = registry.lifecycle_state("phoenix_a_core_v1")

    kwargs = dict(
        module_id="phoenix_a_core_v1", observed_lifecycle_state=lifecycle_state,
        policy_hash=policy.policy_hash, capability_snapshot_hash=capabilities.capability_hash,
        observed_invocation_count=0, max_allowed_invocations=None,
    )
    allowed_decision = ExecutionPolicyDecision(allowed=True, reason="ALLOWED", **kwargs)
    denied_decision = ExecutionPolicyDecision(allowed=False, reason="DENIED_RATE_LIMIT", **kwargs)

    assert allowed_decision.decision_hash != denied_decision.decision_hash


def test_decision_hash_is_well_formed():
    registry = _make_active_registry()
    decision = ExecutionAuthorizer(
        registry, ExecutionPolicy(), ExecutionPolicyState()
    ).authorize("phoenix_a_core_v1")

    assert isinstance(decision.decision_hash, bytes)
    assert len(decision.decision_hash) == 32


def test_independent_modules_have_independent_authorization():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")

    from example_execution_module import ExampleExecutionModule
    registry.register(ExampleExecutionModule())
    registry.activate("example_doubler_v1")

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=1)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry, policy, state)

    d1 = authorizer.authorize("phoenix_a_core_v1")
    authorizer.record_execution(d1)

    d2 = authorizer.authorize("phoenix_a_core_v1")  # denied, limit=1 reached
    d3 = authorizer.authorize("example_doubler_v1")  # allowed, independent count

    assert d1.allowed is True
    assert d2.allowed is False
    assert d3.allowed is True
"""
Engine Policy Decision Emission - Integration Test
(test_engine_policy_decision_emission.py)

First integration test proving the live wiring introduced in
deterministic_execution_engine.py v2.8: PolicyDecisionRecord is
constructed from the SAME ExecutionPolicyDecision object that produces
DecisionRecord, at the same call site, not from a second authorize()
call or a reconstruction from fields.

The bridge assertion -- policy_record.policy_decision.decision_hash ==
decision_record.decision_hash -- is the proof that actually matters.
sequence_id and generation_id equality alone would only show the two
records were constructed at the same moment; matching decision_hash is
what proves they trace to the same underlying authorizer decision.
"""

import numpy as np
import pytest

from execution_kernel_contract import CoreExecutionFrame
from deterministic_execution_engine import (
    DeterministicExecutionEngine,
    AuthorizationDeniedError,
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

    module = registry.resolve("phoenix_a_core_v1")
    return registry, authorizer, module


def test_engine_emits_policy_decision_record_from_authorizer_result():
    """
    The core bridge proof. policy_decision_log[0] and decision_log[0]
    must correspond on all three: sequence_id, generation_id, and,
    critically, decision_hash -- that last one is what actually proves
    "same decision," not just "same moment."
    """
    registry, authorizer, module = _make_authorized_setup()
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    engine.process_frame(_make_frame(seq_id=0))

    assert len(engine.decision_log) == 1
    assert len(engine.policy_decision_log) == 1

    decision_record = engine.decision_log[0]
    policy_record = engine.policy_decision_log[0]

    assert policy_record.sequence_id == decision_record.sequence_id
    assert policy_record.generation_id == decision_record.generation_id
    assert policy_record.policy_decision.decision_hash == decision_record.decision_hash


def test_policy_decision_record_matches_across_multiple_frames():
    """
    Same bridge proof, checked pairwise across several frames -- proves
    correspondence isn't an artifact of only ever having one record in
    each log.
    """
    registry, authorizer, module = _make_authorized_setup(max_invocations=10)
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    for seq_id in range(5):
        engine.process_frame(_make_frame(seq_id=seq_id, seed_val=float(seq_id) + 1.0))

    assert len(engine.decision_log) == 5
    assert len(engine.policy_decision_log) == 5

    for decision_record, policy_record in zip(engine.decision_log, engine.policy_decision_log):
        assert policy_record.sequence_id == decision_record.sequence_id
        assert policy_record.generation_id == decision_record.generation_id
        assert policy_record.policy_decision.decision_hash == decision_record.decision_hash


def test_denied_attempt_still_produces_policy_decision_record():
    """
    Mirrors DecisionRecord's own invariant
    (test_denied_attempt_produces_decision_record_with_no_audit_record
    in test_decision_record_invariants.py): a denial is still a real
    policy decision worth recording, even though it will have no
    corresponding ExecutionAuditRecord since dispatch never happens.
    PolicyDecisionRecord must be populated at the same point
    DecisionRecord is -- before the AuthorizationDeniedError raise --
    not skipped on denial.
    """
    registry, authorizer, module = _make_authorized_setup(max_invocations=0)
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    with pytest.raises(AuthorizationDeniedError):
        engine.process_frame(_make_frame(seq_id=0))

    assert len(engine.decision_log) == 1
    assert len(engine.policy_decision_log) == 1
    assert len(engine.audit_log) == 0  # denial never reaches dispatch

    decision_record = engine.decision_log[0]
    policy_record = engine.policy_decision_log[0]

    assert policy_record.policy_decision.allowed is False
    assert decision_record.allowed is False
    assert policy_record.policy_decision.decision_hash == decision_record.decision_hash


def test_no_authorizer_produces_no_policy_decision_records():
    """
    Backward-compatibility mirror of
    test_no_authorizer_produces_no_decision_records: an engine with no
    authorizer attached must not populate policy_decision_log at all,
    same as decision_log.
    """
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)  # no authorizer
    engine.initialize()

    engine.process_frame(_make_frame(seq_id=0))

    assert engine.policy_decision_log == ()
    assert engine.decision_log == ()
    assert len(engine.audit_log) == 1  # audit still happens, unaffected

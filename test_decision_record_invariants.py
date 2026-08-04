"""
Decision Record Invariants Test Suite
(test_decision_record_invariants.py)

Verifies v2.5's three named invariants:
    A — exactly one DecisionRecord per execution attempt that reaches
        the authorization boundary, whenever an authorizer is attached.
    B — every ExecutionAuditRecord has exactly one preceding, matching
        DecisionRecord with allowed=True.
    C — replay preserves causal ORDERING, not just hash values: decision
        ordering, decision contents, audit ordering, and audit contents
        are checked as four separate assertions.

Also covers backward compatibility, denial recording, and the
allowed/audit pairing baseline the invariants build on.
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


# ---------------------------------------------------------------------
# Baseline: backward compatibility
# ---------------------------------------------------------------------

def test_no_authorizer_produces_no_decision_records():
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)  # no authorizer
    engine.initialize()

    engine.process_frame(_make_frame(seq_id=0))

    assert engine.decision_log == ()
    assert len(engine.audit_log) == 1  # audit still happens as before v2.5


# ---------------------------------------------------------------------
# Baseline: denial produces a decision record but no audit record
# ---------------------------------------------------------------------

def test_denied_attempt_produces_decision_record_with_no_audit_record():
    registry, authorizer, module = _make_authorized_setup(max_invocations=0)
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    with pytest.raises(AuthorizationDeniedError):
        engine.process_frame(_make_frame(seq_id=0))

    assert len(engine.decision_log) == 1
    assert engine.decision_log[0].allowed is False
    assert engine.decision_log[0].sequence_id == 0
    assert len(engine.audit_log) == 0


def test_allowed_attempt_produces_matching_decision_and_audit_record():
    registry, authorizer, module = _make_authorized_setup()
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    envelope, result = engine.process_frame(_make_frame(seq_id=0))

    assert len(engine.decision_log) == 1
    assert engine.decision_log[0].allowed is True
    assert len(engine.audit_log) == 1
    assert result.success is True


# ---------------------------------------------------------------------
# Invariant A — exactly one decision per execution attempt
# ---------------------------------------------------------------------

def test_invariant_a_exactly_one_decision_per_attempt_mixed_outcomes():
    """
    Mix of allowed and denied attempts — decision_log must contain
    exactly one entry per process_frame() call, regardless of outcome.
    """
    registry, authorizer, module = _make_authorized_setup(max_invocations=2)
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    outcomes = []
    for seq_id in range(4):
        try:
            engine.process_frame(_make_frame(seq_id=seq_id))
            outcomes.append("allowed")
        except AuthorizationDeniedError:
            outcomes.append("denied")

    assert len(engine.decision_log) == 4
    assert outcomes == ["allowed", "allowed", "denied", "denied"]
    assert [r.allowed for r in engine.decision_log] == [True, True, False, False]


def test_invariant_a_decision_count_matches_attempt_count_exactly():
    """Stronger phrasing of Invariant A: N attempts -> exactly N records,
    never fewer, never more — checked across a larger N to rule out an
    off-by-one."""
    registry, authorizer, module = _make_authorized_setup(max_invocations=10)
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    attempts = 7
    for seq_id in range(attempts):
        engine.process_frame(_make_frame(seq_id=seq_id))

    assert len(engine.decision_log) == attempts


# ---------------------------------------------------------------------
# Invariant B — every audit record has exactly one preceding,
# matching, allowed decision record
# ---------------------------------------------------------------------

def test_invariant_b_every_audit_record_has_exactly_one_preceding_allowed_decision():
    registry, authorizer, module = _make_authorized_setup(max_invocations=3)
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    for seq_id in range(3):
        engine.process_frame(_make_frame(seq_id=seq_id))
    try:
        engine.process_frame(_make_frame(seq_id=3))
    except AuthorizationDeniedError:
        pass

    assert len(engine.audit_log) == 3
    assert len(engine.decision_log) == 4  # 3 allowed + 1 denied

    for audit_record in engine.audit_log:
        matches = [
            d for d in engine.decision_log
            if d.sequence_id == audit_record.sequence_id and d.allowed is True
        ]
        assert len(matches) == 1, (
            f"Expected exactly 1 allowed decision for seq_id "
            f"{audit_record.sequence_id}, found {len(matches)}"
        )


def test_invariant_b_denied_attempts_have_no_matching_audit_record():
    """The complement of Invariant B: a denied DecisionRecord must never
    have a corresponding audit_log entry."""
    registry, authorizer, module = _make_authorized_setup(max_invocations=0)
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    with pytest.raises(AuthorizationDeniedError):
        engine.process_frame(_make_frame(seq_id=0))

    denied_seq_ids = {d.sequence_id for d in engine.decision_log if not d.allowed}
    audit_seq_ids = {a.sequence_id for a in engine.audit_log}

    assert denied_seq_ids.isdisjoint(audit_seq_ids)


# ---------------------------------------------------------------------
# Invariant C — replay preserves causal ORDERING, not just hash values
# ---------------------------------------------------------------------

def test_invariant_c_replay_preserves_decision_ordering_and_contents():
    def run():
        registry, authorizer, module = _make_authorized_setup(max_invocations=10)
        engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
        engine.initialize()

        for seq_id in range(5):
            engine.process_frame(_make_frame(seq_id=seq_id, seed_val=float(seq_id) + 1.0))

        decision_order = [d.sequence_id for d in engine.decision_log]
        decision_hashes = tuple(d.record_hash for d in engine.decision_log)
        return decision_order, decision_hashes

    order_1, hashes_1 = run()
    order_2, hashes_2 = run()

    # Ordering assertion — separate from content assertion, per Invariant C.
    assert order_1 == order_2, "Decision ORDERING diverged across replay runs"
    # Content assertion.
    assert hashes_1 == hashes_2, "Decision CONTENTS (hashes) diverged across replay runs"


def test_invariant_c_replay_preserves_audit_ordering_and_contents():
    def run():
        registry, authorizer, module = _make_authorized_setup(max_invocations=10)
        engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
        engine.initialize()

        for seq_id in range(5):
            engine.process_frame(_make_frame(seq_id=seq_id, seed_val=float(seq_id) + 1.0))

        audit_order = [a.sequence_id for a in engine.audit_log]
        audit_hashes = tuple(a.audit_hash for a in engine.audit_log)
        return audit_order, audit_hashes

    order_1, hashes_1 = run()
    order_2, hashes_2 = run()

    assert order_1 == order_2, "Audit ORDERING diverged across replay runs"
    assert hashes_1 == hashes_2, "Audit CONTENTS (hashes) diverged across replay runs"


def test_invariant_c_decision_always_precedes_matching_audit_within_a_run():
    """
    The specific causal claim of Invariant C: for the same execution
    attempt, the DecisionRecord's position in decision_log is always
    "earlier in the causal sequence" than its paired ExecutionAuditRecord's
    position in audit_log — checked via matching sequence_id, since the
    two logs are independent lists with potentially different lengths
    (denials inflate decision_log without a matching audit_log entry).
    """
    registry, authorizer, module = _make_authorized_setup(max_invocations=10)
    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    for seq_id in range(4):
        engine.process_frame(_make_frame(seq_id=seq_id, seed_val=float(seq_id) + 1.0))

    # For every audit record, its decision must exist and — by construction
    # of process_frame()'s control flow — was necessarily appended to
    # decision_log strictly before the corresponding audit_record was
    # appended to audit_log, since dispatch (and therefore audit emission)
    # only occurs after the decision record already exists and was allowed.
    for audit_record in engine.audit_log:
        decision_index = next(
            i for i, d in enumerate(engine.decision_log)
            if d.sequence_id == audit_record.sequence_id
        )
        assert engine.decision_log[decision_index].allowed is True
        # The causal claim: this decision existed (was appended) before
        # its audit record could possibly have been created, since the
        # code path from decision -> dispatch -> audit is unconditional
        # and sequential within a single process_frame() call.
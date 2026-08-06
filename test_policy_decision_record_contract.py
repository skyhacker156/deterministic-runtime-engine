"""
Policy Decision Record - Contract Tests
(test_policy_decision_record_contract.py)

Direct structural mirror of test_execution_audit.py's shape: basic
construction/validation first, then determinism (same inputs -> same
hash), then sensitivity (changed inputs -> changed hash). Targets
PolicyDecisionRecord's own construction-time behavior only -- JSON
round-trip and tampering-via-disk live in
test_policy_decision_record_persistence.py.
"""

import hashlib
import pytest

from module_lifecycle import ModuleState
from execution_authorizer import ExecutionPolicyDecision
from policy_decision_record_contract import (
    PolicyDecisionRecord,
    PolicyDecisionRecordValidationError,
)


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


# Fixed placeholder generation_id for records built in this file. This
# file tests PolicyDecisionRecord's own construction/validation/hash
# behavior, not generation identity, so a single fixed constant shared
# by every record in every test is fine here.
_GEN_ID = b"\x88" * 16


def make_policy_decision(
    module_id="phoenix_a_core_v1",
    allowed=True,
    reason="ALLOWED",
    observed_lifecycle_state=ModuleState.ACTIVE,
    policy_hash_seed=b"policy",
    capability_hash_seed=b"capabilities",
    observed_invocation_count=0,
    max_allowed_invocations=None,
):
    return ExecutionPolicyDecision(
        module_id=module_id,
        allowed=allowed,
        reason=reason,
        observed_lifecycle_state=observed_lifecycle_state,
        policy_hash=_hash32(policy_hash_seed),
        capability_snapshot_hash=_hash32(capability_hash_seed),
        observed_invocation_count=observed_invocation_count,
        max_allowed_invocations=max_allowed_invocations,
    )


def make_policy_decision_record(
    sequence_id=0,
    generation_id=_GEN_ID,
    policy_decision=None,
):
    if policy_decision is None:
        policy_decision = make_policy_decision()
    return PolicyDecisionRecord(
        sequence_id=sequence_id,
        generation_id=generation_id,
        policy_decision=policy_decision,
    )


# ---------------------------------------------------------------------
# 1. Construction invariants
# ---------------------------------------------------------------------

def test_valid_policy_decision_record_constructs():
    record = make_policy_decision_record()
    assert record.sequence_id == 0
    assert record.generation_id == _GEN_ID
    assert isinstance(record.policy_decision, ExecutionPolicyDecision)
    assert len(record.entry_hash) == 32


def test_negative_sequence_id_rejected():
    with pytest.raises(PolicyDecisionRecordValidationError, match="sequence_id"):
        make_policy_decision_record(sequence_id=-1)


def test_zero_sequence_id_accepted():
    """
    Guards against a lazy `if not self.sequence_id` validation bug that
    would wrongly reject 0 -- frame sequencing legitimately starts at 0
    (see execution_kernel_state.py's record_frame_execution()), so 0
    must be a valid sequence_id, not merely "falsy and therefore
    rejected."
    """
    record = make_policy_decision_record(sequence_id=0)
    assert record.sequence_id == 0


def test_invalid_generation_id_type_rejected():
    with pytest.raises(PolicyDecisionRecordValidationError, match="generation_id"):
        make_policy_decision_record(generation_id="not bytes")


def test_invalid_generation_id_length_rejected():
    with pytest.raises(PolicyDecisionRecordValidationError, match="generation_id"):
        make_policy_decision_record(generation_id=b"\x01" * 8)  # too short


def test_missing_policy_decision_rejected():
    """
    Constructs PolicyDecisionRecord directly rather than through
    make_policy_decision_record() -- that helper treats
    policy_decision=None as "no override given" and silently
    substitutes a valid decision (convenience behavior every other
    test in this file relies on), which would defeat this specific
    test by never actually passing None through to the real
    constructor.
    """
    with pytest.raises(PolicyDecisionRecordValidationError, match="policy_decision"):
        PolicyDecisionRecord(
            sequence_id=0,
            generation_id=_GEN_ID,
            policy_decision=None,
        )


def test_policy_decision_as_plain_dict_rejected():
    """
    SHALL 5-style check (same principle as
    test_cold_boot_reconstruction.py's real-class-instances tests):
    policy_decision must be a genuine ExecutionPolicyDecision instance,
    not a dict shaped like one. A dict has no decision_hash derived by
    ExecutionPolicyDecision's own __post_init__, so entry_hash's
    correctness would be unverifiable if this were allowed.
    """
    fake_decision = {
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": _hash32(b"fake"),
    }
    with pytest.raises(PolicyDecisionRecordValidationError, match="policy_decision"):
        PolicyDecisionRecord(
            sequence_id=0,
            generation_id=_GEN_ID,
            policy_decision=fake_decision,
        )


# ---------------------------------------------------------------------
# 2. Inner object provenance -- the wrapper must not alter inner identity
# ---------------------------------------------------------------------

def test_policy_decision_record_preserves_inner_decision_hash():
    """
    The core provenance claim: wrapping an ExecutionPolicyDecision in a
    PolicyDecisionRecord must not change, recompute, or reinterpret its
    decision_hash. The wrapper only adds sequence_id/generation_id
    context around an unmodified inner object.
    """
    decision = make_policy_decision()
    record = make_policy_decision_record(policy_decision=decision)

    assert record.policy_decision.decision_hash == decision.decision_hash
    assert record.policy_decision is decision  # same object, not a copy


def test_policy_decision_record_preserves_all_inner_fields():
    decision = make_policy_decision(
        module_id="phoenix_a_core_v1",
        allowed=False,
        reason="DENIED_RATE_LIMIT",
        observed_invocation_count=7,
        max_allowed_invocations=10,
    )
    record = make_policy_decision_record(policy_decision=decision)

    assert record.policy_decision.module_id == "phoenix_a_core_v1"
    assert record.policy_decision.allowed is False
    assert record.policy_decision.reason == "DENIED_RATE_LIMIT"
    assert record.policy_decision.observed_invocation_count == 7
    assert record.policy_decision.max_allowed_invocations == 10


# ---------------------------------------------------------------------
# 3. Outer hash binding -- entry_hash determinism and sensitivity
# ---------------------------------------------------------------------

def test_identical_inputs_produce_identical_entry_hash():
    """
    Determinism check using two SEPARATELY-constructed but
    field-identical ExecutionPolicyDecision instances (not the same
    object twice) -- proves entry_hash depends on decision_hash's
    VALUE, not on object identity.
    """
    decision_1 = make_policy_decision(module_id="phoenix_a_core_v1")
    decision_2 = make_policy_decision(module_id="phoenix_a_core_v1")
    assert decision_1.decision_hash == decision_2.decision_hash  # sanity

    record_1 = make_policy_decision_record(sequence_id=5, policy_decision=decision_1)
    record_2 = make_policy_decision_record(sequence_id=5, policy_decision=decision_2)

    assert record_1.entry_hash == record_2.entry_hash


def test_changed_sequence_id_changes_entry_hash():
    decision = make_policy_decision()
    record_1 = make_policy_decision_record(sequence_id=1, policy_decision=decision)
    record_2 = make_policy_decision_record(sequence_id=2, policy_decision=decision)

    assert record_1.entry_hash != record_2.entry_hash


def test_changed_generation_id_changes_entry_hash():
    decision = make_policy_decision()
    record_1 = make_policy_decision_record(
        generation_id=b"\x88" * 16, policy_decision=decision
    )
    record_2 = make_policy_decision_record(
        generation_id=b"\x99" * 16, policy_decision=decision
    )

    assert record_1.entry_hash != record_2.entry_hash


def test_changed_inner_decision_changes_entry_hash():
    """
    entry_hash must be sensitive to the embedded decision's identity
    (via decision_hash), not just to sequence_id/generation_id -- a
    wrapper that ignored its own payload would defeat the point of
    embedding the real object.
    """
    decision_a = make_policy_decision(module_id="phoenix_a_core_v1")
    decision_b = make_policy_decision(module_id="phoenix_b_core_v1")
    assert decision_a.decision_hash != decision_b.decision_hash  # sanity

    record_a = make_policy_decision_record(policy_decision=decision_a)
    record_b = make_policy_decision_record(policy_decision=decision_b)

    assert record_a.entry_hash != record_b.entry_hash

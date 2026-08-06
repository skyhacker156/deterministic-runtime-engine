"""
Policy Decision Record - Persistence Round-Trip Test
(test_policy_decision_record_persistence.py)

Same scope as the other three persistence test files: does this record
survive a real disk round-trip with every hash intact? No envelope, no
crash recovery, no versioning.

TWO HASH LAYERS, checked independently -- see
policy_decision_record_persistence.py's own docstring:
  - decision_hash, inside the embedded ExecutionPolicyDecision, derived
    from module_id/allowed/reason/observed_lifecycle_state/policy_hash/
    capability_snapshot_hash.
  - entry_hash, one layer up, derived from sequence_id/generation_id/
    decision_hash (the inner hash, referenced opaquely).

NEITHER hash is ever written to the persisted JSON -- both are fully
derived and always recomputed on reconstruction, same convention as
DecisionRecord.record_hash and ExecutionAuditRecord.audit_hash
elsewhere in this codebase. This means the "tampered field disagrees
with a stored hash" shape used by the OTHER persistence tests in this
codebase for OPAQUE fields (e.g. DecisionRecord.decision_hash, which
IS stored, since it's externally-supplied) does not apply to either
hash here -- there is no stored hash for a tampered field to disagree
with, because neither hash is ever stored. The tampering tests below
instead prove the same underlying property (a field isn't decorative)
via the only mechanism this schema actually offers: tamper a field,
reconstruct, and confirm the RECOMPUTED hash changed.
"""

import hashlib
import json
import tempfile
import os

import pytest

from module_lifecycle import ModuleState
from execution_authorizer import ExecutionPolicyDecision
from policy_decision_record_contract import PolicyDecisionRecord
from policy_decision_record_persistence import (
    policy_decision_record_to_json,
    policy_decision_record_from_json,
)


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


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


def make_policy_decision_record(sequence_id=0, generation_id=_GEN_ID, policy_decision=None):
    if policy_decision is None:
        policy_decision = make_policy_decision()
    return PolicyDecisionRecord(
        sequence_id=sequence_id,
        generation_id=generation_id,
        policy_decision=policy_decision,
    )


# ---------------------------------------------------------------------
# 1. Round trip -- both hash layers checked independently
# ---------------------------------------------------------------------

def test_round_trip_preserves_both_hash_layers():
    original = make_policy_decision_record()
    restored = policy_decision_record_from_json(policy_decision_record_to_json(original))

    assert restored.policy_decision.decision_hash == original.policy_decision.decision_hash
    assert restored.entry_hash == original.entry_hash


def test_round_trip_preserves_all_fields():
    decision = make_policy_decision(
        module_id="phoenix_a_core_v1",
        allowed=False,
        reason="DENIED_RATE_LIMIT",
        observed_invocation_count=4,
        max_allowed_invocations=10,
    )
    original = make_policy_decision_record(sequence_id=42, policy_decision=decision)
    restored = policy_decision_record_from_json(policy_decision_record_to_json(original))

    assert restored.sequence_id == original.sequence_id
    assert restored.generation_id == original.generation_id
    assert restored.policy_decision.module_id == original.policy_decision.module_id
    assert restored.policy_decision.allowed == original.policy_decision.allowed
    assert restored.policy_decision.reason == original.policy_decision.reason
    assert restored.policy_decision.observed_lifecycle_state == original.policy_decision.observed_lifecycle_state
    assert restored.policy_decision.observed_invocation_count == original.policy_decision.observed_invocation_count
    assert restored.policy_decision.max_allowed_invocations == original.policy_decision.max_allowed_invocations


def test_round_trip_through_actual_disk_file():
    original = make_policy_decision_record(sequence_id=7)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "policy_decision_record.json")

        with open(path, "w", encoding="utf-8") as f:
            f.write(policy_decision_record_to_json(original))

        with open(path, "r", encoding="utf-8") as f:
            restored = policy_decision_record_from_json(f.read())

    assert restored.entry_hash == original.entry_hash
    assert restored.policy_decision.decision_hash == original.policy_decision.decision_hash
    assert restored.sequence_id == original.sequence_id


def test_denied_decision_round_trip():
    """Explicit denied-path check, mirroring the other three persistence
    files' allowed/denied pairing -- denied decisions carry a different
    reason string, worth confirming that isn't lost."""
    decision = make_policy_decision(allowed=False, reason="DENIED_RATE_LIMIT")
    original = make_policy_decision_record(policy_decision=decision)
    restored = policy_decision_record_from_json(policy_decision_record_to_json(original))

    assert restored.policy_decision.allowed is False
    assert restored.policy_decision.reason == "DENIED_RATE_LIMIT"
    assert restored.entry_hash == original.entry_hash


# ---------------------------------------------------------------------
# 2. Inner-field tampering -- proves the embedded decision isn't
#    decorative: a tampered field changes the RECOMPUTED decision_hash,
#    which propagates to entry_hash
# ---------------------------------------------------------------------

def test_tampering_with_inner_allowed_field_changes_both_hashes():
    original = make_policy_decision_record()
    payload = json.loads(policy_decision_record_to_json(original))

    payload["policy_decision"]["allowed"] = not payload["policy_decision"]["allowed"]
    tampered = policy_decision_record_from_json(json.dumps(payload))

    assert tampered.policy_decision.decision_hash != original.policy_decision.decision_hash
    assert tampered.entry_hash != original.entry_hash


def test_tampering_with_inner_module_id_changes_both_hashes():
    original = make_policy_decision_record()
    payload = json.loads(policy_decision_record_to_json(original))

    payload["policy_decision"]["module_id"] = "phoenix_b_core_v1"
    tampered = policy_decision_record_from_json(json.dumps(payload))

    assert tampered.policy_decision.decision_hash != original.policy_decision.decision_hash
    assert tampered.entry_hash != original.entry_hash


def test_tampering_with_inner_reason_changes_both_hashes():
    original = make_policy_decision_record()
    payload = json.loads(policy_decision_record_to_json(original))

    payload["policy_decision"]["reason"] = "TAMPERED"
    tampered = policy_decision_record_from_json(json.dumps(payload))

    assert tampered.policy_decision.decision_hash != original.policy_decision.decision_hash
    assert tampered.entry_hash != original.entry_hash


# ---------------------------------------------------------------------
# 3. Outer-field tampering -- proves the wrapper actually binds
#    execution context, and that the two hash layers are genuinely
#    independent (an outer tamper must NOT disturb the inner hash)
# ---------------------------------------------------------------------

def test_tampering_with_sequence_id_changes_entry_hash_only():
    original = make_policy_decision_record(sequence_id=10)
    payload = json.loads(policy_decision_record_to_json(original))

    payload["sequence_id"] = 11
    tampered = policy_decision_record_from_json(json.dumps(payload))

    assert tampered.entry_hash != original.entry_hash
    # Isolation check: sequence_id was never an input to decision_hash,
    # so the inner hash must be completely unaffected by this tamper.
    assert tampered.policy_decision.decision_hash == original.policy_decision.decision_hash


def test_tampering_with_generation_id_changes_entry_hash_only():
    original = make_policy_decision_record(generation_id=b"\x88" * 16)
    payload = json.loads(policy_decision_record_to_json(original))

    payload["generation_id"] = (b"\x99" * 16).hex()
    tampered = policy_decision_record_from_json(json.dumps(payload))

    assert tampered.entry_hash != original.entry_hash
    assert tampered.policy_decision.decision_hash == original.policy_decision.decision_hash


# ---------------------------------------------------------------------
# 4. Bad data rejection
# ---------------------------------------------------------------------

def test_malformed_json_raises():
    with pytest.raises((json.JSONDecodeError, KeyError)):
        policy_decision_record_from_json("{not valid json")


def test_missing_required_field_raises():
    incomplete = json.dumps({"sequence_id": 0})
    with pytest.raises(KeyError):
        policy_decision_record_from_json(incomplete)


def test_missing_nested_policy_decision_field_raises():
    original = make_policy_decision_record()
    payload = json.loads(policy_decision_record_to_json(original))
    del payload["policy_decision"]["module_id"]

    with pytest.raises(KeyError):
        policy_decision_record_from_json(json.dumps(payload))


def test_unknown_lifecycle_state_name_raises():
    """
    observed_lifecycle_state is stored as ModuleState's .name string
    and reconstructed via ModuleState[name] -- an unrecognized name
    (corruption, or a future ModuleState rename) must fail loudly, not
    silently default to some state.
    """
    original = make_policy_decision_record()
    payload = json.loads(policy_decision_record_to_json(original))
    payload["policy_decision"]["observed_lifecycle_state"] = "NOT_A_REAL_STATE"

    with pytest.raises(KeyError):
        policy_decision_record_from_json(json.dumps(payload))

"""
Decision Record - Persistence Round-Trip Test
(test_decision_record_persistence.py)

Same scope as test_registration_audit_persistence.py: does this one
record type survive a real disk round-trip with its hashes intact?
No envelope, no crash recovery, no versioning -- see
decision_record_persistence.py's docstring for why those stay out of
scope until every record type has answered this question independently.

This file checks TWO properties per record, not one -- see
decision_record_persistence.py's docstring for why decision_hash
(opaque, must survive byte-for-byte) and record_hash (derived, must
recompute identically) are different failure modes and neither implies
the other.
"""

import hashlib
import json
import tempfile
import os

import pytest
from hypothesis import given, strategies as st

from decision_record_contract import DecisionRecord, DecisionRecordValidationError
from decision_record_persistence import decision_record_to_json, decision_record_from_json


st_sequence_id = st.integers(min_value=0, max_value=2**63 - 1)
st_module_id = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")
st_hash_seed = st.binary(min_size=1, max_size=32)


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


def make_decision_record(sequence_id=0, module_id="phoenix_a_core_v1",
                          allowed=True, decision_hash_seed=b"seed"):
    return DecisionRecord(
        sequence_id=sequence_id,
        module_id=module_id,
        allowed=allowed,
        decision_hash=_hash32(decision_hash_seed),
    )


# ---------------------------------------------------------------------
# 1. Allowed / denied round trip -- both hash properties checked
# ---------------------------------------------------------------------

def test_allowed_decision_round_trip_preserves_both_hashes():
    original = make_decision_record(allowed=True)
    restored = decision_record_from_json(decision_record_to_json(original))

    # decision_hash: opaque, must survive byte-for-byte
    assert restored.decision_hash == original.decision_hash
    # record_hash: derived, must recompute to the same value
    assert restored.record_hash == original.record_hash


def test_denied_decision_round_trip_preserves_both_hashes():
    original = make_decision_record(allowed=False)
    restored = decision_record_from_json(decision_record_to_json(original))

    assert restored.decision_hash == original.decision_hash
    assert restored.record_hash == original.record_hash


# ---------------------------------------------------------------------
# 2. All fields preserved, not just the hashes
# ---------------------------------------------------------------------

def test_round_trip_preserves_all_fields():
    original = make_decision_record(
        sequence_id=42,
        module_id="phoenix_a_core_v1",
        allowed=False,
        decision_hash_seed=b"policy denial: quota exhausted",
    )
    restored = decision_record_from_json(decision_record_to_json(original))

    assert restored.sequence_id == original.sequence_id
    assert restored.module_id == original.module_id
    assert restored.allowed == original.allowed
    assert restored.decision_hash == original.decision_hash
    assert restored.record_hash == original.record_hash


# ---------------------------------------------------------------------
# 3. Actual disk round trip
# ---------------------------------------------------------------------

def test_round_trip_through_actual_disk_file():
    original = make_decision_record(allowed=True, decision_hash_seed=b"disk test")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "decision_record.json")

        with open(path, "w", encoding="utf-8") as f:
            f.write(decision_record_to_json(original))

        with open(path, "r", encoding="utf-8") as f:
            restored = decision_record_from_json(f.read())

    assert restored.decision_hash == original.decision_hash
    assert restored.record_hash == original.record_hash
    assert restored.sequence_id == original.sequence_id


# ---------------------------------------------------------------------
# 4. Fuzz: both allowed and denied, across many sequence_id/module_id/
#    decision_hash combinations
# ---------------------------------------------------------------------

@given(
    sequence_id=st_sequence_id,
    module_id=st_module_id,
    hash_seed=st_hash_seed,
)
def test_fuzz_allowed_decisions_round_trip(sequence_id, module_id, hash_seed):
    original = DecisionRecord(
        sequence_id=sequence_id,
        module_id=module_id,
        allowed=True,
        decision_hash=_hash32(hash_seed),
    )
    restored = decision_record_from_json(decision_record_to_json(original))
    assert restored.decision_hash == original.decision_hash
    assert restored.record_hash == original.record_hash


@given(
    sequence_id=st_sequence_id,
    module_id=st_module_id,
    hash_seed=st_hash_seed,
)
def test_fuzz_denied_decisions_round_trip(sequence_id, module_id, hash_seed):
    original = DecisionRecord(
        sequence_id=sequence_id,
        module_id=module_id,
        allowed=False,
        decision_hash=_hash32(hash_seed),
    )
    restored = decision_record_from_json(decision_record_to_json(original))
    assert restored.decision_hash == original.decision_hash
    assert restored.record_hash == original.record_hash


# ---------------------------------------------------------------------
# 5. Sensitivity: reconstructed record_hash actually changes if a field
#    is tampered with post-serialization -- proves record_hash isn't
#    silently being read from storage rather than recomputed
# ---------------------------------------------------------------------

def test_tampering_with_serialized_module_id_changes_record_hash():
    """
    If this test failed, it would mean record_hash is somehow NOT being
    recomputed from the real fields on reconstruction -- e.g. a bug
    where a stored hash is being trusted instead of recomputed. This
    directly exercises that decision_record_from_json() has no path to
    fake a hash match.
    """
    original = make_decision_record(module_id="phoenix_a_core_v1")
    json_str = decision_record_to_json(original)

    payload = json.loads(json_str)
    payload["module_id"] = "phoenix_b_core_v1"  # tamper
    tampered_json = json.dumps(payload)

    tampered = decision_record_from_json(tampered_json)
    assert tampered.record_hash != original.record_hash


def test_tampering_with_serialized_decision_hash_changes_record_hash():
    original = make_decision_record(decision_hash_seed=b"original")
    json_str = decision_record_to_json(original)

    payload = json.loads(json_str)
    payload["decision_hash"] = _hash32(b"tampered").hex()
    tampered_json = json.dumps(payload)

    tampered = decision_record_from_json(tampered_json)
    assert tampered.decision_hash != original.decision_hash
    assert tampered.record_hash != original.record_hash


# ---------------------------------------------------------------------
# 6. Bad data rejection
# ---------------------------------------------------------------------

def test_malformed_json_raises():
    with pytest.raises((json.JSONDecodeError, KeyError)):
        decision_record_from_json("{not valid json")


def test_missing_required_field_raises():
    incomplete = json.dumps({"sequence_id": 0, "module_id": "x"})
    with pytest.raises(KeyError):
        decision_record_from_json(incomplete)


def test_malformed_decision_hash_hex_raises():
    """
    decision_hash must decode to exactly 32 bytes -- DecisionRecord's
    own __post_init__ enforces this (DecisionRecordValidationError).
    A corrupted hex string that's too short should be caught there,
    not silently accepted as a shorter-than-expected hash.
    """
    payload = {
        "sequence_id": 0,
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": "deadbeef",  # 4 bytes, not 32
    }
    with pytest.raises(DecisionRecordValidationError):
        decision_record_from_json(json.dumps(payload))

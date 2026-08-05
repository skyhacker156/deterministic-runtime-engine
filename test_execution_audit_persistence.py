"""
Execution Audit Record - Persistence Round-Trip Test
(test_execution_audit_persistence.py)

Third and last of the three original in-memory logs to get this same
narrow question answered: does the record survive a real disk
round-trip with every hash intact?

This record has three independent opaque hash fields to check
(input_hash, prior_state_hash, output_hash) plus one derived hash
(audit_hash) -- more surface area than either ModuleRegistrationAttemptRecord
(one opaque optional hash) or DecisionRecord (one opaque hash). See
execution_audit_persistence.py's docstring for why each is checked
independently rather than assuming one hash matching implies the others
do too.
"""

import hashlib
import json
import tempfile
import os

import pytest
from hypothesis import given, strategies as st

from execution_audit_contract import ExecutionAuditRecord
from execution_audit_persistence import audit_record_to_json, audit_record_from_json


st_sequence_id = st.integers(min_value=0, max_value=2**63 - 1)
st_module_id = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")
st_hash_seed = st.binary(min_size=1, max_size=32)
st_timestamp_ns = st.integers(min_value=0, max_value=2**64 - 1)
st_valid_error_message = st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != "")


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


# Fixed placeholder generation_id for records built in this file. This
# file tests JSON round-trip persistence, not generation identity, so a
# single fixed constant shared by every record in every test is fine
# here.
_GEN_ID = b"\x55" * 16


def make_audit_record(sequence_id=0, input_seed=b"in", prior_seed=b"prior",
                       output_seed=b"out", module_id="phoenix_a_core_v1",
                       success=True, frame_timestamp_ns=1000, error_message=None):
    return ExecutionAuditRecord(
        sequence_id=sequence_id,
        input_hash=_hash32(input_seed),
        prior_state_hash=_hash32(prior_seed),
        output_hash=_hash32(output_seed),
        module_id=module_id,
        success=success,
        frame_timestamp_ns=frame_timestamp_ns,
        error_message=error_message,
        generation_id=_GEN_ID,
    )


# ---------------------------------------------------------------------
# 1. Success / failure round trip -- all four hashes checked
# ---------------------------------------------------------------------

def test_success_record_round_trip_preserves_all_hashes():
    original = make_audit_record(success=True, error_message=None)
    restored = audit_record_from_json(audit_record_to_json(original))

    assert restored.input_hash == original.input_hash
    assert restored.prior_state_hash == original.prior_state_hash
    assert restored.output_hash == original.output_hash
    assert restored.audit_hash == original.audit_hash


def test_failure_record_round_trip_preserves_all_hashes():
    original = make_audit_record(success=False, error_message="module raised ValueError")
    restored = audit_record_from_json(audit_record_to_json(original))

    assert restored.input_hash == original.input_hash
    assert restored.prior_state_hash == original.prior_state_hash
    assert restored.output_hash == original.output_hash
    assert restored.audit_hash == original.audit_hash
    assert restored.error_message == original.error_message


# ---------------------------------------------------------------------
# 2. All fields preserved, not just the hashes
# ---------------------------------------------------------------------

def test_round_trip_preserves_all_fields():
    original = make_audit_record(
        sequence_id=99,
        module_id="phoenix_a_core_v1",
        success=False,
        frame_timestamp_ns=123456789,
        error_message="numerical instability detected",
    )
    restored = audit_record_from_json(audit_record_to_json(original))

    assert restored.sequence_id == original.sequence_id
    assert restored.module_id == original.module_id
    assert restored.success == original.success
    assert restored.frame_timestamp_ns == original.frame_timestamp_ns
    assert restored.error_message == original.error_message
    assert restored.input_hash == original.input_hash
    assert restored.prior_state_hash == original.prior_state_hash
    assert restored.output_hash == original.output_hash
    assert restored.audit_hash == original.audit_hash


# ---------------------------------------------------------------------
# 3. Actual disk round trip
# ---------------------------------------------------------------------

def test_round_trip_through_actual_disk_file():
    original = make_audit_record(success=True, error_message=None)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "audit_record.json")

        with open(path, "w", encoding="utf-8") as f:
            f.write(audit_record_to_json(original))

        with open(path, "r", encoding="utf-8") as f:
            restored = audit_record_from_json(f.read())

    assert restored.input_hash == original.input_hash
    assert restored.prior_state_hash == original.prior_state_hash
    assert restored.output_hash == original.output_hash
    assert restored.audit_hash == original.audit_hash


# ---------------------------------------------------------------------
# 4. Fuzz
# ---------------------------------------------------------------------

@given(
    sequence_id=st_sequence_id,
    input_seed=st_hash_seed,
    prior_seed=st_hash_seed,
    output_seed=st_hash_seed,
    module_id=st_module_id,
    frame_timestamp_ns=st_timestamp_ns,
)
def test_fuzz_success_records_round_trip(
    sequence_id, input_seed, prior_seed, output_seed, module_id, frame_timestamp_ns
):
    original = ExecutionAuditRecord(
        sequence_id=sequence_id,
        input_hash=_hash32(input_seed),
        prior_state_hash=_hash32(prior_seed),
        output_hash=_hash32(output_seed),
        module_id=module_id,
        success=True,
        frame_timestamp_ns=frame_timestamp_ns,
        error_message=None,
        generation_id=_GEN_ID,
    )
    restored = audit_record_from_json(audit_record_to_json(original))
    assert restored.input_hash == original.input_hash
    assert restored.prior_state_hash == original.prior_state_hash
    assert restored.output_hash == original.output_hash
    assert restored.audit_hash == original.audit_hash


@given(
    sequence_id=st_sequence_id,
    input_seed=st_hash_seed,
    prior_seed=st_hash_seed,
    output_seed=st_hash_seed,
    module_id=st_module_id,
    frame_timestamp_ns=st_timestamp_ns,
    error_message=st_valid_error_message,
)
def test_fuzz_failure_records_round_trip(
    sequence_id, input_seed, prior_seed, output_seed, module_id,
    frame_timestamp_ns, error_message
):
    original = ExecutionAuditRecord(
        sequence_id=sequence_id,
        input_hash=_hash32(input_seed),
        prior_state_hash=_hash32(prior_seed),
        output_hash=_hash32(output_seed),
        module_id=module_id,
        success=False,
        frame_timestamp_ns=frame_timestamp_ns,
        error_message=error_message,
        generation_id=_GEN_ID,
    )
    restored = audit_record_from_json(audit_record_to_json(original))
    assert restored.input_hash == original.input_hash
    assert restored.prior_state_hash == original.prior_state_hash
    assert restored.output_hash == original.output_hash
    assert restored.audit_hash == original.audit_hash
    assert restored.error_message == original.error_message


# ---------------------------------------------------------------------
# 5. Sensitivity: tampering with any one of the three opaque hashes
#    after serialization changes audit_hash on reconstruction -- proves
#    audit_hash is genuinely recomputed, not trusted from storage
# ---------------------------------------------------------------------

def test_tampering_with_input_hash_changes_audit_hash():
    original = make_audit_record()
    payload = json.loads(audit_record_to_json(original))
    payload["input_hash"] = _hash32(b"tampered").hex()
    tampered = audit_record_from_json(json.dumps(payload))
    assert tampered.audit_hash != original.audit_hash


def test_tampering_with_prior_state_hash_changes_audit_hash():
    original = make_audit_record()
    payload = json.loads(audit_record_to_json(original))
    payload["prior_state_hash"] = _hash32(b"tampered").hex()
    tampered = audit_record_from_json(json.dumps(payload))
    assert tampered.audit_hash != original.audit_hash


def test_tampering_with_output_hash_changes_audit_hash():
    original = make_audit_record()
    payload = json.loads(audit_record_to_json(original))
    payload["output_hash"] = _hash32(b"tampered").hex()
    tampered = audit_record_from_json(json.dumps(payload))
    assert tampered.audit_hash != original.audit_hash


def test_tampering_with_module_id_changes_audit_hash():
    original = make_audit_record(module_id="phoenix_a_core_v1")
    payload = json.loads(audit_record_to_json(original))
    payload["module_id"] = "phoenix_b_core_v1"
    tampered = audit_record_from_json(json.dumps(payload))
    assert tampered.audit_hash != original.audit_hash


# ---------------------------------------------------------------------
# 6. Bad data rejection
# ---------------------------------------------------------------------

def test_malformed_json_raises():
    with pytest.raises((json.JSONDecodeError, KeyError)):
        audit_record_from_json("{not valid json")


def test_missing_required_field_raises():
    incomplete = json.dumps({"sequence_id": 0, "module_id": "x"})
    with pytest.raises(KeyError):
        audit_record_from_json(incomplete)


def test_malformed_hash_hex_raises():
    """
    Each of the three hash fields must decode to exactly 32 bytes --
    ExecutionAuditRecord.__post_init__ enforces this with a bare
    ValueError (no custom exception class here, unlike DecisionRecord).
    """
    original = make_audit_record()
    payload = json.loads(audit_record_to_json(original))
    payload["output_hash"] = "deadbeef"  # 4 bytes, not 32
    with pytest.raises(ValueError):
        audit_record_from_json(json.dumps(payload))


def test_success_with_error_message_rejected_on_reconstruction():
    """
    Mirrors the contract's own consistency rule: success=True with a
    non-None error_message must be rejected, including on the
    reconstruction path -- not just at direct construction time.
    """
    payload = {
        "sequence_id": 0,
        "input_hash": _hash32(b"a").hex(),
        "prior_state_hash": _hash32(b"b").hex(),
        "output_hash": _hash32(b"c").hex(),
        "module_id": "phoenix_a_core_v1",
        "success": True,
        "frame_timestamp_ns": 1000,
        "error_message": "should not be here",
        "generation_id": _GEN_ID.hex(),
    }
    with pytest.raises(ValueError):
        audit_record_from_json(json.dumps(payload))


def test_failure_without_error_message_rejected_on_reconstruction():
    payload = {
        "sequence_id": 0,
        "input_hash": _hash32(b"a").hex(),
        "prior_state_hash": _hash32(b"b").hex(),
        "output_hash": _hash32(b"c").hex(),
        "module_id": "phoenix_a_core_v1",
        "success": False,
        "frame_timestamp_ns": 1000,
        "error_message": None,
        "generation_id": _GEN_ID.hex(),
    }
    with pytest.raises(ValueError):
        audit_record_from_json(json.dumps(payload))

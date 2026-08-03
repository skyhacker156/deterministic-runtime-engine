"""
Fuzzing Test Suite - Execution Audit Contract
(test_execution_audit.py)
"""

import hashlib
import pytest
from hypothesis import given, strategies as st

from execution_audit_contract import ExecutionAuditRecord


def _hash32(seed: bytes) -> bytes:
    """Deterministic 32-byte digest helper for generating valid test hashes."""
    return hashlib.sha256(seed).digest()


st_seq_id = st.integers(min_value=0, max_value=2**63 - 1)
st_hash_seed = st.binary(min_size=1, max_size=32)
st_module_id = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")
st_timestamp_ns = st.integers(min_value=0, max_value=2**64 - 1)
st_valid_error_message = st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != "")


def make_record(seed_input=b"a", seed_prior=b"b", seed_output=b"c",
                 seq_id=0, module_id="phoenix_a", success=True,
                 frame_timestamp_ns=1000, error_message=None):
    return ExecutionAuditRecord(
        sequence_id=seq_id,
        input_hash=_hash32(seed_input),
        prior_state_hash=_hash32(seed_prior),
        output_hash=_hash32(seed_output),
        module_id=module_id,
        success=success,
        frame_timestamp_ns=frame_timestamp_ns,
        error_message=error_message,
    )


# ---------------------------------------------------------------------
# 1. Basic construction / structural validation
# ---------------------------------------------------------------------

def test_valid_success_record_constructs():
    rec = make_record(success=True, error_message=None)
    assert rec.success is True
    assert len(rec.audit_hash) == 32


def test_valid_failure_record_requires_error_message():
    rec = make_record(success=False, error_message="module blew up")
    assert rec.success is False
    assert rec.error_message == "module blew up"


def test_failure_without_error_message_rejected():
    with pytest.raises(ValueError, match="error_message must be provided"):
        make_record(success=False, error_message=None)


def test_success_with_error_message_rejected():
    with pytest.raises(ValueError, match="error_message must be None"):
        make_record(success=True, error_message="should not be here")


def test_malformed_hash_field_rejected():
    with pytest.raises(ValueError, match="must be a 32-byte SHA-256 digest"):
        ExecutionAuditRecord(
            sequence_id=0,
            input_hash=b"too_short",
            prior_state_hash=_hash32(b"b"),
            output_hash=_hash32(b"c"),
            module_id="phoenix_a",
            success=True,
            frame_timestamp_ns=1000,
        )


def test_empty_module_id_rejected():
    with pytest.raises(ValueError, match="module_id must be"):
        make_record(module_id="")


# ---------------------------------------------------------------------
# 2. Determinism: identical inputs -> identical audit_hash
# ---------------------------------------------------------------------

@given(
    seq_id=st_seq_id,
    seed_input=st_hash_seed,
    seed_prior=st_hash_seed,
    seed_output=st_hash_seed,
    module_id=st_module_id,
    frame_timestamp_ns=st_timestamp_ns,
)
def test_fuzz_identical_inputs_produce_identical_audit_hash(
    seq_id, seed_input, seed_prior, seed_output, module_id, frame_timestamp_ns
):
    rec1 = make_record(
        seed_input=seed_input, seed_prior=seed_prior, seed_output=seed_output,
        seq_id=seq_id, module_id=module_id, frame_timestamp_ns=frame_timestamp_ns,
        success=True, error_message=None,
    )
    rec2 = make_record(
        seed_input=seed_input, seed_prior=seed_prior, seed_output=seed_output,
        seq_id=seq_id, module_id=module_id, frame_timestamp_ns=frame_timestamp_ns,
        success=True, error_message=None,
    )
    assert rec1.audit_hash == rec2.audit_hash


# ---------------------------------------------------------------------
# 3. Sensitivity: changing any real field changes the hash
# ---------------------------------------------------------------------

def test_fuzz_changed_sequence_id_changes_hash():
    rec1 = make_record(seq_id=1)
    rec2 = make_record(seq_id=2)
    assert rec1.audit_hash != rec2.audit_hash


def test_fuzz_changed_input_hash_changes_hash():
    rec1 = make_record(seed_input=b"a")
    rec2 = make_record(seed_input=b"z")
    assert rec1.audit_hash != rec2.audit_hash


def test_fuzz_changed_prior_state_hash_changes_hash():
    rec1 = make_record(seed_prior=b"a")
    rec2 = make_record(seed_prior=b"z")
    assert rec1.audit_hash != rec2.audit_hash


def test_fuzz_changed_output_hash_changes_hash():
    rec1 = make_record(seed_output=b"a")
    rec2 = make_record(seed_output=b"z")
    assert rec1.audit_hash != rec2.audit_hash


def test_fuzz_changed_module_id_changes_hash():
    rec1 = make_record(module_id="phoenix_a")
    rec2 = make_record(module_id="phoenix_b")
    assert rec1.audit_hash != rec2.audit_hash


def test_fuzz_changed_success_status_changes_hash():
    rec1 = make_record(success=True, error_message=None)
    rec2 = make_record(success=False, error_message="failed")
    assert rec1.audit_hash != rec2.audit_hash


def test_fuzz_changed_timestamp_changes_hash():
    rec1 = make_record(frame_timestamp_ns=1000)
    rec2 = make_record(frame_timestamp_ns=2000)
    assert rec1.audit_hash != rec2.audit_hash


@given(msg1=st_valid_error_message, msg2=st_valid_error_message)
def test_fuzz_different_error_messages_change_hash(msg1, msg2):
    if msg1 == msg2:
        return  # not a meaningful case for this property
    rec1 = make_record(success=False, error_message=msg1)
    rec2 = make_record(success=False, error_message=msg2)
    assert rec1.audit_hash != rec2.audit_hash


# ---------------------------------------------------------------------
# 4. from_execution() correctly derives fields from ExecutionResult,
#    never restates them independently
# ---------------------------------------------------------------------

def test_from_execution_derives_fields_from_result():
    import numpy as np
    from execution_module_contract import ExecutionResult

    payload = np.zeros(256, dtype=np.float64)
    result = ExecutionResult(
        seq_id=5,
        success=True,
        output_payload=payload,
        metrics={"signal_energy": 1.0},
        error_message=None,
    )

    rec = ExecutionAuditRecord.from_execution(
        sequence_id=5,
        input_hash=_hash32(b"frame"),
        prior_state_hash=_hash32(b"prior"),
        frame_timestamp_ns=1_000_000,
        module_id="phoenix_a",
        result=result,
    )

    assert rec.success == result.success
    assert rec.output_hash == result.module_hash
    assert rec.error_message == result.error_message
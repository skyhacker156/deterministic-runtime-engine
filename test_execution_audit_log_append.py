"""
Execution Audit Record - Append-Only Log Tests
(test_execution_audit_log_append.py)

Direct structural mirror of test_registration_audit_log_append.py and
test_decision_record_log_append.py. Same narrow question: many
ExecutionAuditRecords appended sequentially to one file -- read back in
order, with all three opaque hashes plus the derived audit_hash intact.
No crash safety, no concurrent writers.
"""

import hashlib
import os
import tempfile

import pytest
from hypothesis import given, strategies as st, settings

from execution_audit_contract import ExecutionAuditRecord
from execution_audit_log import (
    append_audit_record,
    read_all_audit_records,
    log_exists,
    AuditLogCorruptionError,
)


st_sequence_id = st.integers(min_value=0, max_value=2**63 - 1)


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


# Fixed placeholder generation_id for records built by make_record()
# below. This file tests append/read-back log mechanics, not generation
# identity, so a single fixed constant shared by every record in every
# test is fine here.
_GEN_ID = b"\x66" * 16


def make_record(sequence_id=0, module_id="phoenix_a_core_v1", success=True,
                 error_message=None, input_seed=b"in", prior_seed=b"prior",
                 output_seed=b"out"):
    return ExecutionAuditRecord(
        sequence_id=sequence_id,
        input_hash=_hash32(input_seed),
        prior_state_hash=_hash32(prior_seed),
        output_hash=_hash32(output_seed),
        module_id=module_id,
        success=success,
        frame_timestamp_ns=1000,
        error_message=error_message,
        generation_id=_GEN_ID,
    )


@pytest.fixture
def temp_log_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "audit.jsonl")


# ---------------------------------------------------------------------
# 1. Single record: append then read back
# ---------------------------------------------------------------------

def test_append_single_record_then_read_back(temp_log_path):
    record = make_record(success=True)
    append_audit_record(temp_log_path, record)

    results = read_all_audit_records(temp_log_path)

    assert len(results) == 1
    assert results[0].audit_hash == record.audit_hash
    assert results[0].input_hash == record.input_hash
    assert results[0].prior_state_hash == record.prior_state_hash
    assert results[0].output_hash == record.output_hash


# ---------------------------------------------------------------------
# 2. Multiple records: order and all hashes preserved
# ---------------------------------------------------------------------

def test_append_multiple_records_preserves_order():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "log.jsonl")

        r1 = make_record(sequence_id=1, success=False, error_message="frame 1 failed",
                          output_seed=b"out1")
        r2 = make_record(sequence_id=2, success=True, output_seed=b"out2")
        r3 = make_record(sequence_id=3, success=False, error_message="frame 3 failed",
                          output_seed=b"out3")

        append_audit_record(path, r1)
        append_audit_record(path, r2)
        append_audit_record(path, r3)

        results = read_all_audit_records(path)

    assert len(results) == 3
    assert [r.audit_hash for r in results] == [r1.audit_hash, r2.audit_hash, r3.audit_hash]
    assert results[0].success is False
    assert results[1].success is True
    assert results[2].sequence_id == 3


def test_append_preserves_all_hashes_across_many_records(temp_log_path):
    originals = [
        make_record(
            sequence_id=i,
            success=(i % 2 == 0),
            error_message=None if i % 2 == 0 else f"failure {i}",
            output_seed=f"out_{i}".encode(),
        )
        for i in range(20)
    ]
    for r in originals:
        append_audit_record(temp_log_path, r)

    results = read_all_audit_records(temp_log_path)

    assert len(results) == 20
    for original, restored in zip(originals, results):
        assert restored.audit_hash == original.audit_hash
        assert restored.input_hash == original.input_hash
        assert restored.prior_state_hash == original.prior_state_hash
        assert restored.output_hash == original.output_hash
        assert restored.error_message == original.error_message


# ---------------------------------------------------------------------
# 3. Reopen-and-append
# ---------------------------------------------------------------------

def test_appending_across_separate_calls_preserves_prior_records(temp_log_path):
    first_batch = [make_record(sequence_id=i, output_seed=f"a_{i}".encode())
                    for i in range(3)]
    for r in first_batch:
        append_audit_record(temp_log_path, r)

    second_batch = [
        make_record(sequence_id=i + 100, success=False,
                    error_message="denied downstream", output_seed=f"b_{i}".encode())
        for i in range(2)
    ]
    for r in second_batch:
        append_audit_record(temp_log_path, r)

    results = read_all_audit_records(temp_log_path)

    assert len(results) == 5
    all_originals = first_batch + second_batch
    assert [r.audit_hash for r in results] == [r.audit_hash for r in all_originals]


# ---------------------------------------------------------------------
# 4. Empty / nonexistent file handling
# ---------------------------------------------------------------------

def test_read_empty_file_returns_empty_list(temp_log_path):
    open(temp_log_path, "w", encoding="utf-8").close()
    assert read_all_audit_records(temp_log_path) == []


def test_read_nonexistent_file_raises_file_not_found(temp_log_path):
    with pytest.raises(FileNotFoundError):
        read_all_audit_records(temp_log_path)


def test_log_exists_false_before_first_append(temp_log_path):
    assert log_exists(temp_log_path) is False


def test_log_exists_true_after_first_append(temp_log_path):
    append_audit_record(temp_log_path, make_record())
    assert log_exists(temp_log_path) is True


# ---------------------------------------------------------------------
# 5. Corruption handling
# ---------------------------------------------------------------------

def test_corrupt_middle_line_raises_with_line_number(temp_log_path):
    append_audit_record(temp_log_path, make_record(sequence_id=1, output_seed=b"a"))
    append_audit_record(temp_log_path, make_record(sequence_id=2, output_seed=b"b"))

    with open(temp_log_path, "a", encoding="utf-8") as f:
        f.write("{not valid json\n")

    with pytest.raises(AuditLogCorruptionError, match="Line 3"):
        read_all_audit_records(temp_log_path)


def test_blank_lines_are_skipped_not_treated_as_corruption(temp_log_path):
    append_audit_record(temp_log_path, make_record(sequence_id=1, output_seed=b"a"))

    with open(temp_log_path, "a", encoding="utf-8") as f:
        f.write("\n")

    append_audit_record(temp_log_path, make_record(sequence_id=2, output_seed=b"b"))

    results = read_all_audit_records(temp_log_path)
    assert len(results) == 2


# ---------------------------------------------------------------------
# 6. Fuzz
# ---------------------------------------------------------------------

@settings(deadline=None)
@given(sequence_ids=st.lists(st_sequence_id, min_size=1, max_size=15))
def test_fuzz_sequential_appends_preserve_order(sequence_ids):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "fuzz_log.jsonl")

        originals = [
            make_record(sequence_id=sid, output_seed=str(i).encode())
            for i, sid in enumerate(sequence_ids)
        ]
        for r in originals:
            append_audit_record(path, r)

        results = read_all_audit_records(path)

    assert len(results) == len(originals)
    assert [r.audit_hash for r in results] == [r.audit_hash for r in originals]

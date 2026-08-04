"""
Decision Record - Append-Only Log Tests
(test_decision_record_log_append.py)

Direct structural mirror of test_registration_audit_log_append.py.
Same narrow question: many DecisionRecords appended sequentially to one
file -- read back in the same order, with both decision_hash (opaque)
and record_hash (derived) intact, including across separate
open/append/close cycles. No crash safety, no concurrent writers.
"""

import hashlib
import os
import tempfile

import pytest
from hypothesis import given, strategies as st, settings

from decision_record_contract import DecisionRecord
from decision_record_log import (
    append_decision_record,
    read_all_decision_records,
    log_exists,
    DecisionLogCorruptionError,
)


st_module_id = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")
st_sequence_id = st.integers(min_value=0, max_value=2**63 - 1)


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


def make_record(sequence_id=0, module_id="phoenix_a_core_v1", allowed=True,
                 decision_hash_seed=b"seed"):
    return DecisionRecord(
        sequence_id=sequence_id,
        module_id=module_id,
        allowed=allowed,
        decision_hash=_hash32(decision_hash_seed),
    )


@pytest.fixture
def temp_log_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "decisions.jsonl")


# ---------------------------------------------------------------------
# 1. Single record: append then read back
# ---------------------------------------------------------------------

def test_append_single_record_then_read_back(temp_log_path):
    record = make_record(allowed=True)
    append_decision_record(temp_log_path, record)

    results = read_all_decision_records(temp_log_path)

    assert len(results) == 1
    assert results[0].decision_hash == record.decision_hash
    assert results[0].record_hash == record.record_hash


# ---------------------------------------------------------------------
# 2. Multiple records: order and both hashes preserved
# ---------------------------------------------------------------------

def test_append_multiple_records_preserves_order():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "log.jsonl")

        r1 = make_record(sequence_id=1, allowed=False, decision_hash_seed=b"denied1")
        r2 = make_record(sequence_id=2, allowed=True, decision_hash_seed=b"allowed1")
        r3 = make_record(sequence_id=3, allowed=False, decision_hash_seed=b"denied2")

        append_decision_record(path, r1)
        append_decision_record(path, r2)
        append_decision_record(path, r3)

        results = read_all_decision_records(path)

    assert len(results) == 3
    assert [r.record_hash for r in results] == [r1.record_hash, r2.record_hash, r3.record_hash]
    assert results[0].allowed is False
    assert results[1].allowed is True
    assert results[2].sequence_id == 3


def test_append_preserves_both_hashes_across_many_records(temp_log_path):
    originals = [
        make_record(sequence_id=i, allowed=(i % 2 == 0), decision_hash_seed=f"seed_{i}".encode())
        for i in range(20)
    ]
    for r in originals:
        append_decision_record(temp_log_path, r)

    results = read_all_decision_records(temp_log_path)

    assert len(results) == 20
    for original, restored in zip(originals, results):
        assert restored.decision_hash == original.decision_hash
        assert restored.record_hash == original.record_hash
        assert restored.sequence_id == original.sequence_id


# ---------------------------------------------------------------------
# 3. Reopen-and-append
# ---------------------------------------------------------------------

def test_appending_across_separate_calls_preserves_prior_records(temp_log_path):
    first_batch = [make_record(sequence_id=i, allowed=True) for i in range(3)]
    for r in first_batch:
        append_decision_record(temp_log_path, r)

    second_batch = [make_record(sequence_id=i + 100, allowed=False,
                                 decision_hash_seed=b"denied") for i in range(2)]
    for r in second_batch:
        append_decision_record(temp_log_path, r)

    results = read_all_decision_records(temp_log_path)

    assert len(results) == 5
    all_originals = first_batch + second_batch
    assert [r.record_hash for r in results] == [r.record_hash for r in all_originals]


# ---------------------------------------------------------------------
# 4. Empty / nonexistent file handling
# ---------------------------------------------------------------------

def test_read_empty_file_returns_empty_list(temp_log_path):
    open(temp_log_path, "w", encoding="utf-8").close()
    assert read_all_decision_records(temp_log_path) == []


def test_read_nonexistent_file_raises_file_not_found(temp_log_path):
    with pytest.raises(FileNotFoundError):
        read_all_decision_records(temp_log_path)


def test_log_exists_false_before_first_append(temp_log_path):
    assert log_exists(temp_log_path) is False


def test_log_exists_true_after_first_append(temp_log_path):
    append_decision_record(temp_log_path, make_record())
    assert log_exists(temp_log_path) is True


# ---------------------------------------------------------------------
# 5. Corruption handling
# ---------------------------------------------------------------------

def test_corrupt_middle_line_raises_with_line_number(temp_log_path):
    append_decision_record(temp_log_path, make_record(sequence_id=1))
    append_decision_record(temp_log_path, make_record(sequence_id=2))

    with open(temp_log_path, "a", encoding="utf-8") as f:
        f.write("{not valid json\n")

    with pytest.raises(DecisionLogCorruptionError, match="Line 3"):
        read_all_decision_records(temp_log_path)


def test_blank_lines_are_skipped_not_treated_as_corruption(temp_log_path):
    append_decision_record(temp_log_path, make_record(sequence_id=1))

    with open(temp_log_path, "a", encoding="utf-8") as f:
        f.write("\n")

    append_decision_record(temp_log_path, make_record(sequence_id=2))

    results = read_all_decision_records(temp_log_path)
    assert len(results) == 2


# ---------------------------------------------------------------------
# 6. Fuzz
# ---------------------------------------------------------------------

@settings(deadline=None)
@given(sequence_ids=st.lists(st_sequence_id, min_size=1, max_size=15))
def test_fuzz_sequential_appends_preserve_order(sequence_ids):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "fuzz_log.jsonl")

        originals = [make_record(sequence_id=sid, decision_hash_seed=str(i).encode())
                     for i, sid in enumerate(sequence_ids)]
        for r in originals:
            append_decision_record(path, r)

        results = read_all_decision_records(path)

    assert len(results) == len(originals)
    assert [r.record_hash for r in results] == [r.record_hash for r in originals]

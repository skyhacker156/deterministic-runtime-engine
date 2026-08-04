"""
Module Registration Audit - Append-Only Log Tests
(test_registration_audit_log_append.py)

Answers one narrow question beyond the single-record round-trip already
proven in test_registration_audit_persistence.py: if many records are
appended sequentially to one file, are they all read back, in the same
order, with every hash intact -- including across separate process-like
open/append/close cycles, not just one continuous write.

Explicitly NOT covered here (see module_registration_audit_log.py's
docstring): crash safety mid-write, concurrent writers, atomic append
guarantees. Those are real questions but strictly harder than this one,
and not worth designing until this narrower question is answered.
"""

import os
import tempfile

import pytest
from hypothesis import given, strategies as st, settings

from module_registration_audit import ModuleRegistrationAttemptRecord
from module_registration_audit_log import (
    append_record,
    read_all_records,
    log_exists,
    RegistrationLogCorruptionError,
)


st_module_id = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")


def make_record(module_id="phoenix_a_core_v1", attempted_at_ns=1000,
                 success=True, reason=None):
    return ModuleRegistrationAttemptRecord(
        module_id=module_id,
        attempted_at_ns=attempted_at_ns,
        success=success,
        reason=reason,
    )


@pytest.fixture
def temp_log_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "registration_attempts.jsonl")


# ---------------------------------------------------------------------
# 1. Single record: append then read back
# ---------------------------------------------------------------------

def test_append_single_record_then_read_back(temp_log_path):
    record = make_record(success=True)
    append_record(temp_log_path, record)

    results = read_all_records(temp_log_path)

    assert len(results) == 1
    assert results[0].attempt_hash == record.attempt_hash
    assert results[0].module_id == record.module_id


# ---------------------------------------------------------------------
# 2. Multiple records: order and hash integrity preserved
# ---------------------------------------------------------------------

def test_append_multiple_records_preserves_order():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "log.jsonl")

        r1 = make_record(module_id="module_a", success=False, reason="manifest mismatch")
        r2 = make_record(module_id="module_a", success=True)
        r3 = make_record(module_id="module_b", success=False, reason="compliance failure")

        append_record(path, r1)
        append_record(path, r2)
        append_record(path, r3)

        results = read_all_records(path)

    assert len(results) == 3
    assert [r.attempt_hash for r in results] == [r1.attempt_hash, r2.attempt_hash, r3.attempt_hash]
    assert results[0].success is False
    assert results[1].success is True
    assert results[2].module_id == "module_b"


def test_append_preserves_all_hashes_across_many_records(temp_log_path):
    originals = [
        make_record(module_id=f"module_{i}", attempted_at_ns=i, success=(i % 2 == 0),
                    reason=None if i % 2 == 0 else f"failure reason {i}")
        for i in range(20)
    ]
    for r in originals:
        append_record(temp_log_path, r)

    results = read_all_records(temp_log_path)

    assert len(results) == 20
    for original, restored in zip(originals, results):
        assert restored.attempt_hash == original.attempt_hash
        assert restored.module_id == original.module_id
        assert restored.success == original.success
        assert restored.reason == original.reason


# ---------------------------------------------------------------------
# 3. Reopen-and-append: separate append calls (simulating separate
#    process lifetimes) don't clobber prior content
# ---------------------------------------------------------------------

def test_appending_across_separate_calls_preserves_prior_records(temp_log_path):
    first_batch = [make_record(module_id="module_a") for _ in range(3)]
    for r in first_batch:
        append_record(temp_log_path, r)

    # Simulates "process restarts, log file already exists, more
    # attempts happen" -- a fresh append_record call, no prior state
    # held in memory, same path.
    second_batch = [make_record(module_id="module_b", success=False, reason="denied")
                     for _ in range(2)]
    for r in second_batch:
        append_record(temp_log_path, r)

    results = read_all_records(temp_log_path)

    assert len(results) == 5
    all_originals = first_batch + second_batch
    assert [r.attempt_hash for r in results] == [r.attempt_hash for r in all_originals]


# ---------------------------------------------------------------------
# 4. Empty / nonexistent file handling
# ---------------------------------------------------------------------

def test_read_empty_file_returns_empty_list(temp_log_path):
    # Create an empty file without appending anything to it.
    open(temp_log_path, "w", encoding="utf-8").close()

    results = read_all_records(temp_log_path)
    assert results == []


def test_read_nonexistent_file_raises_file_not_found(temp_log_path):
    # temp_log_path's directory exists but the file itself was never created.
    with pytest.raises(FileNotFoundError):
        read_all_records(temp_log_path)


def test_log_exists_false_before_first_append(temp_log_path):
    assert log_exists(temp_log_path) is False


def test_log_exists_true_after_first_append(temp_log_path):
    append_record(temp_log_path, make_record())
    assert log_exists(temp_log_path) is True


# ---------------------------------------------------------------------
# 5. Corruption: a bad line is rejected loudly, with a locatable line
#    number, rather than silently skipped
# ---------------------------------------------------------------------

def test_corrupt_middle_line_raises_with_line_number(temp_log_path):
    r1 = make_record(module_id="module_a")
    r2 = make_record(module_id="module_b")
    append_record(temp_log_path, r1)
    append_record(temp_log_path, r2)

    # Manually corrupt by appending a malformed line directly, bypassing
    # append_record (simulates on-disk corruption, not an API misuse).
    with open(temp_log_path, "a", encoding="utf-8") as f:
        f.write("{not valid json\n")

    with pytest.raises(RegistrationLogCorruptionError, match="Line 3"):
        read_all_records(temp_log_path)


def test_blank_lines_are_skipped_not_treated_as_corruption(temp_log_path):
    r1 = make_record(module_id="module_a")
    append_record(temp_log_path, r1)

    # Inject a blank line -- should be tolerated, not raise.
    with open(temp_log_path, "a", encoding="utf-8") as f:
        f.write("\n")

    r2 = make_record(module_id="module_b")
    append_record(temp_log_path, r2)

    results = read_all_records(temp_log_path)
    assert len(results) == 2


# ---------------------------------------------------------------------
# 6. Fuzz: many sequential appends, order preserved
# ---------------------------------------------------------------------

@settings(deadline=None)
@given(module_ids=st.lists(st_module_id, min_size=1, max_size=15))
def test_fuzz_sequential_appends_preserve_order(module_ids):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "fuzz_log.jsonl")

        originals = [make_record(module_id=mid, attempted_at_ns=i)
                     for i, mid in enumerate(module_ids)]
        for r in originals:
            append_record(path, r)

        results = read_all_records(path)

    assert len(results) == len(originals)
    assert [r.attempt_hash for r in results] == [r.attempt_hash for r in originals]

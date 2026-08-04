"""
Registration Audit - Persistence Round-Trip Test
(test_registration_audit_persistence.py)

The single question this file answers: if a ModuleRegistrationAttemptRecord
is serialized to disk and read back, does its attempt_hash recompute to
the SAME value?

This is deliberately the first and only persistence question asked.
No crash recovery, no partial writes, no envelope format, no schema
versioning -- see module_registration_audit_persistence.py's docstring
for why those are out of scope until this is answered.

If every test here passes, the deterministic-hashing discipline already
proven in-memory (test_module_registration_audit.py) survives a real
disk round-trip, and persistence work can proceed on top of that
confidence. If any test here fails, that failure is far cheaper to
diagnose now, on one record type in isolation, than after an envelope
abstraction and three parallel durable stores have been built on top
of an unverified assumption.
"""

import json
import tempfile
import os

import pytest
from hypothesis import given, strategies as st

from module_registration_audit import ModuleRegistrationAttemptRecord
from module_registration_audit_persistence import record_to_json, record_from_json


st_module_id = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")
st_timestamp_ns = st.integers(min_value=0, max_value=2**64 - 1)
st_valid_reason = st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != "")


def make_record(module_id="phoenix_a_core_v1", attempted_at_ns=1000,
                 success=True, reason=None, manifest_hash=None):
    return ModuleRegistrationAttemptRecord(
        module_id=module_id,
        attempted_at_ns=attempted_at_ns,
        success=success,
        reason=reason,
        manifest_hash=manifest_hash,
    )


# ---------------------------------------------------------------------
# 1. In-memory round-trip (serialize/deserialize, no actual disk I/O)
# ---------------------------------------------------------------------

def test_success_record_round_trip_preserves_hash():
    original = make_record(success=True, reason=None)
    restored = record_from_json(record_to_json(original))
    assert restored.attempt_hash == original.attempt_hash


def test_failure_record_round_trip_preserves_hash():
    original = make_record(success=False, reason="manifest incompatible")
    restored = record_from_json(record_to_json(original))
    assert restored.attempt_hash == original.attempt_hash


def test_record_with_manifest_hash_round_trip_preserves_hash():
    import hashlib
    manifest_hash = hashlib.sha256(b"some manifest content").digest()
    original = make_record(success=True, manifest_hash=manifest_hash)
    restored = record_from_json(record_to_json(original))
    assert restored.attempt_hash == original.attempt_hash
    assert restored.manifest_hash == original.manifest_hash


def test_round_trip_preserves_all_fields_not_just_hash():
    """
    The hash matching isn't sufficient on its own -- it's possible in
    principle for two different field combinations to hash the same
    (a genuine collision, astronomically unlikely, but this test
    doesn't rely on hash equality implying field equality; it checks
    both independently).
    """
    original = make_record(
        module_id="phoenix_a_core_v1",
        attempted_at_ns=123456789,
        success=False,
        reason="compliance check failed: determinism",
    )
    restored = record_from_json(record_to_json(original))

    assert restored.module_id == original.module_id
    assert restored.attempted_at_ns == original.attempted_at_ns
    assert restored.success == original.success
    assert restored.reason == original.reason
    assert restored.manifest_hash == original.manifest_hash
    assert restored.attempt_hash == original.attempt_hash


# ---------------------------------------------------------------------
# 2. Actual disk round-trip (not just in-memory string serialization)
# ---------------------------------------------------------------------

def test_round_trip_through_actual_disk_file():
    """
    Writes to a real temp file and reads it back, rather than just
    passing a string in memory -- proves the encoding survives an
    actual filesystem write/read, not just a Python string round-trip.
    """
    original = make_record(success=False, reason="duplicate module_id")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "attempt_record.json")

        with open(path, "w", encoding="utf-8") as f:
            f.write(record_to_json(original))

        with open(path, "r", encoding="utf-8") as f:
            restored = record_from_json(f.read())

    assert restored.attempt_hash == original.attempt_hash
    assert restored.module_id == original.module_id
    assert restored.reason == original.reason


# ---------------------------------------------------------------------
# 3. Fuzz: round-trip holds across many field combinations, not just
#    the hand-picked examples above
# ---------------------------------------------------------------------

@given(
    module_id=st_module_id,
    attempted_at_ns=st_timestamp_ns,
)
def test_fuzz_success_records_round_trip(module_id, attempted_at_ns):
    original = make_record(module_id=module_id, attempted_at_ns=attempted_at_ns,
                            success=True, reason=None)
    restored = record_from_json(record_to_json(original))
    assert restored.attempt_hash == original.attempt_hash


@given(
    module_id=st_module_id,
    attempted_at_ns=st_timestamp_ns,
    reason=st_valid_reason,
)
def test_fuzz_failure_records_round_trip(module_id, attempted_at_ns, reason):
    original = make_record(module_id=module_id, attempted_at_ns=attempted_at_ns,
                            success=False, reason=reason)
    restored = record_from_json(record_to_json(original))
    assert restored.attempt_hash == original.attempt_hash


# ---------------------------------------------------------------------
# 4. Negative case: corrupted JSON should fail loudly, not silently
#    produce a wrong-but-valid record
# ---------------------------------------------------------------------

def test_malformed_json_raises_rather_than_silently_succeeding():
    with pytest.raises((json.JSONDecodeError, KeyError)):
        record_from_json("{not valid json")


def test_missing_required_field_raises():
    incomplete = json.dumps({"module_id": "x", "success": True})
    with pytest.raises(KeyError):
        record_from_json(incomplete)
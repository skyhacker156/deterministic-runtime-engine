"""
Fuzzing Test Suite - Module Registration Attempt Audit
(test_module_registration_audit.py)
"""

import pytest
from hypothesis import given, strategies as st

from module_registration_audit import (
    ModuleRegistrationAttemptRecord,
    ModuleRegistrationAttemptError,
)


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
# 1. Basic construction / structural validation
# ---------------------------------------------------------------------

def test_valid_success_record_constructs():
    rec = make_record(success=True, reason=None)
    assert rec.success is True
    assert rec.reason is None
    assert len(rec.attempt_hash) == 32


def test_valid_failure_record_requires_reason():
    rec = make_record(success=False, reason="manifest incompatible")
    assert rec.success is False
    assert rec.reason == "manifest incompatible"


def test_failure_without_reason_rejected():
    with pytest.raises(ModuleRegistrationAttemptError, match="reason must be provided"):
        make_record(success=False, reason=None)


def test_failure_with_whitespace_only_reason_rejected():
    with pytest.raises(ModuleRegistrationAttemptError, match="reason must be provided"):
        make_record(success=False, reason="   ")


def test_success_with_reason_rejected():
    with pytest.raises(ModuleRegistrationAttemptError, match="reason must be None"):
        make_record(success=True, reason="should not be here")


def test_empty_module_id_rejected():
    with pytest.raises(ModuleRegistrationAttemptError, match="module_id must be"):
        make_record(module_id="")


def test_whitespace_only_module_id_rejected():
    with pytest.raises(ModuleRegistrationAttemptError, match="module_id must be"):
        make_record(module_id="   ")


def test_negative_timestamp_rejected():
    with pytest.raises(ModuleRegistrationAttemptError, match="attempted_at_ns"):
        make_record(attempted_at_ns=-1)


def test_malformed_manifest_hash_rejected():
    with pytest.raises(ModuleRegistrationAttemptError, match="manifest_hash"):
        make_record(success=True, manifest_hash=b"too_short")


def test_manifest_hash_none_is_valid():
    rec = make_record(success=True, manifest_hash=None)
    assert rec.manifest_hash is None


def test_manifest_hash_correct_length_is_valid():
    import hashlib
    valid_hash = hashlib.sha256(b"some manifest").digest()
    rec = make_record(success=True, manifest_hash=valid_hash)
    assert rec.manifest_hash == valid_hash


# ---------------------------------------------------------------------
# 2. Determinism: identical inputs -> identical attempt_hash
# ---------------------------------------------------------------------

@given(
    module_id=st_module_id,
    attempted_at_ns=st_timestamp_ns,
)
def test_fuzz_identical_success_inputs_produce_identical_attempt_hash(
    module_id, attempted_at_ns
):
    rec1 = make_record(module_id=module_id, attempted_at_ns=attempted_at_ns,
                        success=True, reason=None)
    rec2 = make_record(module_id=module_id, attempted_at_ns=attempted_at_ns,
                        success=True, reason=None)
    assert rec1.attempt_hash == rec2.attempt_hash


@given(
    module_id=st_module_id,
    attempted_at_ns=st_timestamp_ns,
    reason=st_valid_reason,
)
def test_fuzz_identical_failure_inputs_produce_identical_attempt_hash(
    module_id, attempted_at_ns, reason
):
    rec1 = make_record(module_id=module_id, attempted_at_ns=attempted_at_ns,
                        success=False, reason=reason)
    rec2 = make_record(module_id=module_id, attempted_at_ns=attempted_at_ns,
                        success=False, reason=reason)
    assert rec1.attempt_hash == rec2.attempt_hash


# ---------------------------------------------------------------------
# 3. Sensitivity: changing any real field changes the hash
# ---------------------------------------------------------------------

def test_fuzz_changed_module_id_changes_hash():
    rec1 = make_record(module_id="phoenix_a_core_v1")
    rec2 = make_record(module_id="phoenix_b_core_v1")
    assert rec1.attempt_hash != rec2.attempt_hash


def test_fuzz_changed_timestamp_changes_hash():
    rec1 = make_record(attempted_at_ns=1000)
    rec2 = make_record(attempted_at_ns=2000)
    assert rec1.attempt_hash != rec2.attempt_hash


def test_fuzz_changed_success_status_changes_hash():
    rec1 = make_record(success=True, reason=None)
    rec2 = make_record(success=False, reason="failed")
    assert rec1.attempt_hash != rec2.attempt_hash


@given(reason1=st_valid_reason, reason2=st_valid_reason)
def test_fuzz_different_reasons_change_hash(reason1, reason2):
    if reason1 == reason2:
        return  # not a meaningful case for this property
    rec1 = make_record(success=False, reason=reason1)
    rec2 = make_record(success=False, reason=reason2)
    assert rec1.attempt_hash != rec2.attempt_hash


def test_manifest_hash_presence_changes_hash():
    import hashlib
    valid_hash = hashlib.sha256(b"some manifest").digest()
    rec1 = make_record(success=True, manifest_hash=None)
    rec2 = make_record(success=True, manifest_hash=valid_hash)
    assert rec1.attempt_hash != rec2.attempt_hash


def test_different_manifest_hashes_change_hash():
    import hashlib
    hash1 = hashlib.sha256(b"manifest a").digest()
    hash2 = hashlib.sha256(b"manifest b").digest()
    rec1 = make_record(success=True, manifest_hash=hash1)
    rec2 = make_record(success=True, manifest_hash=hash2)
    assert rec1.attempt_hash != rec2.attempt_hash


# ---------------------------------------------------------------------
# 4. reason=None vs reason="" cannot collide with the sentinel byte
#    (regression guard for the hashing scheme's explicit tagging)
# ---------------------------------------------------------------------

def test_none_reason_and_empty_string_reason_are_not_conflatable():
    # "" is rejected outright as a failure reason (whitespace-only),
    # so this test documents that guarantee rather than comparing hashes
    # of two constructible records.
    with pytest.raises(ModuleRegistrationAttemptError):
        make_record(success=False, reason="")
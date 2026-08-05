"""
Causal History Verifier - Tests
(test_causal_history_verifier.py)

Two categories of test:

1. Happy path: build a small, realistic set of records across all
   three logs representing a real registration -> decision -> audit
   sequence, verify the report passes with the right counts.

2. One deliberate failure per check: construct data that specifically
   violates each of the three checks and confirm the verifier catches
   it -- proving each check actually fires, not just that it passes on
   clean input. A verifier that never fails on bad data is not proven,
   only exercised.
"""

import hashlib
import os
import tempfile

import pytest

from module_registration_audit import ModuleRegistrationAttemptRecord
from module_registration_audit_log import append_record as append_registration_record
from decision_record_contract import DecisionRecord
from decision_record_log import append_decision_record
from execution_audit_contract import ExecutionAuditRecord
from execution_audit_log import append_audit_record
from causal_history_verifier import verify_causal_history


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


# Fixed placeholder generation_id for records built by the helpers below.
# This file is testing causal linkage (decision->audit->registration),
# not generation identity, so a single fixed constant shared by every
# record in every test is fine -- none of these tests compare across
# independent kernel generations.
_GEN_ID = b"\x11" * 16


@pytest.fixture
def three_log_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield {
            "registration": os.path.join(tmpdir, "registration.jsonl"),
            "decision": os.path.join(tmpdir, "decision.jsonl"),
            "audit": os.path.join(tmpdir, "audit.jsonl"),
        }


def _make_registration(module_id, success=True, reason=None):
    return ModuleRegistrationAttemptRecord(
        module_id=module_id,
        attempted_at_ns=1000,
        success=success,
        reason=reason,
    )


def _make_decision(sequence_id, module_id, allowed=True, hash_seed=b"d"):
    return DecisionRecord(
        sequence_id=sequence_id,
        module_id=module_id,
        allowed=allowed,
        decision_hash=_hash32(hash_seed),
        generation_id=_GEN_ID,
    )


def _make_audit(sequence_id, module_id, success=True, error_message=None,
                 output_seed=b"o"):
    return ExecutionAuditRecord(
        sequence_id=sequence_id,
        input_hash=_hash32(b"in"),
        prior_state_hash=_hash32(b"prior"),
        output_hash=_hash32(output_seed),
        module_id=module_id,
        success=success,
        frame_timestamp_ns=1000,
        error_message=error_message,
        generation_id=_GEN_ID,
    )


# ---------------------------------------------------------------------
# 1. Happy path: a real registration -> decision -> audit sequence
# ---------------------------------------------------------------------

def test_clean_causal_history_passes_with_correct_counts(three_log_paths):
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )

    append_decision_record(
        three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1", allowed=True)
    )
    append_audit_record(
        three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1", success=True)
    )

    append_decision_record(
        three_log_paths["decision"], _make_decision(2, "phoenix_a_core_v1", allowed=True)
    )
    append_audit_record(
        three_log_paths["audit"], _make_audit(2, "phoenix_a_core_v1", success=True)
    )

    # A denied attempt: decision exists, no audit record -- this is
    # CORRECT behavior (denied decisions never dispatch), not a failure.
    append_decision_record(
        three_log_paths["decision"], _make_decision(3, "phoenix_a_core_v1", allowed=False)
    )

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is True
    assert report.failures == []
    assert report.registration_record_count == 1
    assert report.decision_record_count == 3
    assert report.audit_record_count == 2


# ---------------------------------------------------------------------
# 2. Failure injection: Check 1 (decision ancestry)
# ---------------------------------------------------------------------

def test_audit_record_with_no_decision_at_all_is_caught(three_log_paths):
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_audit_record(
        three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1", success=True)
    )
    open(three_log_paths["decision"], "w", encoding="utf-8").close()

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any("no corresponding allowed DecisionRecord" in f for f in report.failures)


def test_audit_record_matching_only_a_denied_decision_is_caught(three_log_paths):
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1", allowed=False)
    )
    append_audit_record(
        three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1", success=True)
    )

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any("it was DENIED" in f for f in report.failures)


# ---------------------------------------------------------------------
# 3. Failure injection: Check 2 (sequence ordering)
# ---------------------------------------------------------------------

def test_out_of_order_sequence_ids_within_a_module_are_caught(three_log_paths):
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(5, "phoenix_a_core_v1", allowed=True)
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(2, "phoenix_a_core_v1", allowed=True)
    )
    open(three_log_paths["audit"], "w", encoding="utf-8").close()

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any("out of causal order" in f for f in report.failures)


def test_ordering_check_is_independent_per_module(three_log_paths):
    """
    Two different modules interleaved in append order should NOT be
    flagged -- ordering is checked per module_id, not globally across
    the whole log.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("module_a")
    )
    append_registration_record(
        three_log_paths["registration"], _make_registration("module_b")
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(1, "module_a", allowed=True)
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(1, "module_b", allowed=True)
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(2, "module_a", allowed=True)
    )
    open(three_log_paths["audit"], "w", encoding="utf-8").close()

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is True


# ---------------------------------------------------------------------
# 4. Failure injection: Check 3 (module identity cross-reference)
# ---------------------------------------------------------------------

def test_module_id_with_no_registration_record_is_caught(three_log_paths):
    open(three_log_paths["registration"], "w", encoding="utf-8").close()

    append_decision_record(
        three_log_paths["decision"], _make_decision(1, "ghost_module", allowed=True)
    )
    append_audit_record(
        three_log_paths["audit"], _make_audit(1, "ghost_module", success=True)
    )

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any("no successful registration attempt" in f for f in report.failures)


def test_module_id_with_only_failed_registration_is_caught(three_log_paths):
    """
    A module_id whose ONLY registration record is a failed attempt
    still fails this check -- a failed attempt does not establish that
    the module legitimately exists.
    """
    append_registration_record(
        three_log_paths["registration"],
        _make_registration("phoenix_a_core_v1", success=False, reason="manifest mismatch"),
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1", allowed=True)
    )
    append_audit_record(
        three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1", success=True)
    )

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any("no successful registration attempt" in f for f in report.failures)


# ---------------------------------------------------------------------
# 5. Missing log files propagate as real errors, not silent zero-results
# ---------------------------------------------------------------------

def test_missing_log_file_raises_file_not_found(three_log_paths):
    with pytest.raises(FileNotFoundError):
        verify_causal_history(
            three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
        )

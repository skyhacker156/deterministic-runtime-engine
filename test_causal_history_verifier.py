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

Check 4 (policy decision provenance) tests added separately below,
following the same two-category shape: a happy path proving the check
passes on genuinely correlated records, then one test per distinct
failure mode Check 4 is meant to catch -- including the swapped-content
case, which is the one that actually demonstrates the join's value
(two individually valid records, only caught by cross-referencing them
against each other).
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
from module_lifecycle import ModuleState
from execution_authorizer import ExecutionPolicyDecision
from policy_decision_record_contract import PolicyDecisionRecord
from policy_decision_record_log import append_policy_decision_record
from causal_history_verifier import verify_causal_history


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


# Fixed placeholder generation_id shared by every record in every test
# in this file, EXCEPT test_policy_decision_generation_mismatch_is_caught,
# which deliberately uses two different values.
_GEN_ID = b"\x11" * 16
_GEN_ID_OTHER = b"\x22" * 16


@pytest.fixture
def three_log_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield {
            "registration": os.path.join(tmpdir, "registration.jsonl"),
            "decision": os.path.join(tmpdir, "decision.jsonl"),
            "audit": os.path.join(tmpdir, "audit.jsonl"),
            "policy_decision": os.path.join(tmpdir, "policy_decision.jsonl"),
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


def _make_policy_decision(module_id, allowed=True, policy_hash_seed=b"policy",
                           capability_hash_seed=b"capabilities"):
    return ExecutionPolicyDecision(
        module_id=module_id,
        allowed=allowed,
        reason="ALLOWED" if allowed else "DENIED_RATE_LIMIT",
        observed_lifecycle_state=ModuleState.ACTIVE,
        policy_hash=_hash32(policy_hash_seed),
        capability_snapshot_hash=_hash32(capability_hash_seed),
        observed_invocation_count=0,
        max_allowed_invocations=None,
    )


def _make_correlated_decision_and_policy_record(
    sequence_id, module_id, allowed=True, generation_id=_GEN_ID,
    policy_hash_seed=b"policy", capability_hash_seed=b"capabilities",
):
    """
    Builds a DecisionRecord and a PolicyDecisionRecord from the SAME
    ExecutionPolicyDecision, mirroring exactly what
    DeterministicExecutionEngine.process_frame() does in production
    (v2.8) -- the two records' decision_hash values are genuinely equal
    by construction here, not coincidentally matched.
    """
    policy_decision = _make_policy_decision(
        module_id, allowed=allowed,
        policy_hash_seed=policy_hash_seed, capability_hash_seed=capability_hash_seed,
    )
    decision_record = DecisionRecord(
        sequence_id=sequence_id,
        module_id=module_id,
        allowed=allowed,
        decision_hash=policy_decision.decision_hash,
        generation_id=generation_id,
    )
    policy_record = PolicyDecisionRecord(
        sequence_id=sequence_id,
        generation_id=generation_id,
        policy_decision=policy_decision,
    )
    return decision_record, policy_record


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
    assert report.policy_decision_record_count is None  # Check 4 did not run


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


# ---------------------------------------------------------------------
# 6. Check 4 -- happy path
# ---------------------------------------------------------------------

def test_clean_history_with_correlated_policy_decisions_passes(three_log_paths):
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )

    decision_1, policy_1 = _make_correlated_decision_and_policy_record(1, "phoenix_a_core_v1")
    decision_2, policy_2 = _make_correlated_decision_and_policy_record(2, "phoenix_a_core_v1")

    append_decision_record(three_log_paths["decision"], decision_1)
    append_policy_decision_record(three_log_paths["policy_decision"], policy_1)
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    append_decision_record(three_log_paths["decision"], decision_2)
    append_policy_decision_record(three_log_paths["policy_decision"], policy_2)
    append_audit_record(three_log_paths["audit"], _make_audit(2, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is True
    assert report.failures == []
    assert report.policy_decision_record_count == 2  # Check 4 DID run


def test_policy_decision_log_omitted_skips_check_4_entirely(three_log_paths):
    """
    Backward compatibility: a history that would FAIL Check 4 (no
    policy decision records exist at all) must still PASS overall when
    the caller doesn't supply policy_decision_log_path -- Check 4 must
    not run at all, not run-and-be-lenient.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1", allowed=True)
    )
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is True
    assert report.policy_decision_record_count is None


# ---------------------------------------------------------------------
# 7. Check 4 -- failure injection
# ---------------------------------------------------------------------

def test_missing_policy_decision_record_is_caught(three_log_paths):
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )

    decision, policy_record = _make_correlated_decision_and_policy_record(1, "phoenix_a_core_v1")
    append_decision_record(three_log_paths["decision"], decision)
    # Deliberately NOT appended: append_policy_decision_record(...)
    open(three_log_paths["policy_decision"], "w", encoding="utf-8").close()
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is False
    assert any(
        "no corresponding PolicyDecisionRecord at all" in f for f in report.failures
    )


def test_policy_decision_generation_mismatch_is_caught(three_log_paths):
    """
    Same sequence_id, but the persisted PolicyDecisionRecord's
    generation_id differs from the DecisionRecord's. Proves the join
    is not accidentally matching across what would be a reset
    boundary -- and that the verifier gives a SPECIFIC "generation
    mismatch" message, not just a generic "not found."
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )

    policy_decision = _make_policy_decision("phoenix_a_core_v1")
    decision = DecisionRecord(
        sequence_id=5, module_id="phoenix_a_core_v1", allowed=True,
        decision_hash=policy_decision.decision_hash, generation_id=_GEN_ID,
    )
    policy_record = PolicyDecisionRecord(
        sequence_id=5, generation_id=_GEN_ID_OTHER, policy_decision=policy_decision,
    )

    append_decision_record(three_log_paths["decision"], decision)
    append_policy_decision_record(three_log_paths["policy_decision"], policy_record)
    append_audit_record(three_log_paths["audit"], _make_audit(5, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is False
    assert any("generation mismatch" in f for f in report.failures)


def test_policy_decision_hash_mismatch_is_caught(three_log_paths):
    """
    Same (sequence_id, generation_id), but the persisted
    PolicyDecisionRecord's underlying decision_hash does not match the
    DecisionRecord's decision_hash -- a real provenance failure, not
    just a missing record.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )

    real_policy_decision = _make_policy_decision("phoenix_a_core_v1", policy_hash_seed=b"real")
    wrong_policy_decision = _make_policy_decision("phoenix_a_core_v1", policy_hash_seed=b"wrong")
    assert real_policy_decision.decision_hash != wrong_policy_decision.decision_hash  # sanity

    decision = DecisionRecord(
        sequence_id=1, module_id="phoenix_a_core_v1", allowed=True,
        decision_hash=real_policy_decision.decision_hash, generation_id=_GEN_ID,
    )
    # Persisted policy record claims the same (sequence_id, generation_id)
    # but wraps a DIFFERENT ExecutionPolicyDecision.
    policy_record = PolicyDecisionRecord(
        sequence_id=1, generation_id=_GEN_ID, policy_decision=wrong_policy_decision,
    )

    append_decision_record(three_log_paths["decision"], decision)
    append_policy_decision_record(three_log_paths["policy_decision"], policy_record)
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is False
    assert any("provenance mismatch" in f for f in report.failures)


def test_swapped_valid_policy_decision_records_are_caught(three_log_paths):
    """
    The subtle, valuable case: TWO records that are each individually
    completely valid (real ExecutionPolicyDecision, real DecisionRecord,
    both parse and reconstruct without error) but whose CONTENT was
    swapped between two different sequence_ids. Neither record is
    malformed. Only cross-referencing decision_hash against the
    correctly-keyed policy record catches this -- proving Check 4 does
    real correlation work, not just presence/shape checking.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )

    decision_10, policy_10 = _make_correlated_decision_and_policy_record(
        10, "phoenix_a_core_v1", policy_hash_seed=b"attempt_10"
    )
    decision_11, policy_11 = _make_correlated_decision_and_policy_record(
        11, "phoenix_a_core_v1", policy_hash_seed=b"attempt_11"
    )
    assert decision_10.decision_hash != decision_11.decision_hash  # sanity

    # Persist the DecisionRecords at their correct sequence_ids...
    append_decision_record(three_log_paths["decision"], decision_10)
    append_decision_record(three_log_paths["decision"], decision_11)

    # ...but persist the PolicyDecisionRecords SWAPPED: policy_11's
    # content under sequence_id=10, and vice versa. Each is still a
    # perfectly well-formed PolicyDecisionRecord on its own.
    swapped_policy_10 = PolicyDecisionRecord(
        sequence_id=10, generation_id=_GEN_ID, policy_decision=policy_11.policy_decision,
    )
    swapped_policy_11 = PolicyDecisionRecord(
        sequence_id=11, generation_id=_GEN_ID, policy_decision=policy_10.policy_decision,
    )
    append_policy_decision_record(three_log_paths["policy_decision"], swapped_policy_10)
    append_policy_decision_record(three_log_paths["policy_decision"], swapped_policy_11)

    append_audit_record(three_log_paths["audit"], _make_audit(10, "phoenix_a_core_v1"))
    append_audit_record(three_log_paths["audit"], _make_audit(11, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is False
    provenance_failures = [f for f in report.failures if "provenance mismatch" in f]
    # Both swapped records should be caught -- sequence_id=10's decision
    # doesn't match what's now sitting at policy sequence_id=10, and
    # likewise for 11.
    assert len(provenance_failures) == 2

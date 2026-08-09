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


def test_decision_and_audit_sharing_sequence_and_module_but_different_generation_is_caught(three_log_paths):
    """
    PROVENANCE_GRAPH_MODEL.md's headline finding, closed. Before this
    fix, Check 1 joined purely on (sequence_id, module_id) -- a
    DecisionRecord from one kernel generation and an
    ExecutionAuditRecord from a DIFFERENT generation, sharing that
    same key, would have been incorrectly treated as causally linked.
    This is plausible in practice, not just in theory: sequence_id
    resets to 0 after every administrative reset, and the same
    module_id commonly persists across a reset. This test constructs
    exactly that scenario and confirms it is now caught, with a
    diagnostic message distinguishing "generation mismatch" from
    "no decision at all" -- mirroring Check 4's existing pattern for
    the same kind of distinction.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(
        three_log_paths["decision"],
        DecisionRecord(
            sequence_id=5, module_id="phoenix_a_core_v1", allowed=True,
            decision_hash=_hash32(b"gen_a_decision"), generation_id=_GEN_ID,
        ),
    )
    append_audit_record(
        three_log_paths["audit"],
        ExecutionAuditRecord(
            sequence_id=5, input_hash=_hash32(b"in"), prior_state_hash=_hash32(b"prior"),
            output_hash=_hash32(b"out"), module_id="phoenix_a_core_v1", success=True,
            frame_timestamp_ns=1000, error_message=None, generation_id=_GEN_ID_OTHER,
        ),
    )

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any(
        "DIFFERENT generation_id" in f and "Generation mismatch" in f
        for f in report.failures
    )
    # Confirms this is diagnosed as a generation mismatch specifically,
    # not collapsed into the generic "no decision at all" message.
    assert not any(
        "no corresponding allowed DecisionRecord in the decision log at all" in f
        for f in report.failures
    )


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
    the whole log. Matching audit records included for every decision
    -- this test is about Check 2's independence, not Check 6's
    decision/audit completeness, so it must stay clean under Check 6
    to actually isolate what it's testing.
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
    append_audit_record(three_log_paths["audit"], _make_audit(1, "module_a"))
    append_audit_record(three_log_paths["audit"], _make_audit(1, "module_b"))
    append_audit_record(three_log_paths["audit"], _make_audit(2, "module_a"))

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


# ---------------------------------------------------------------------
# 8. Check 5 -- policy decision orphan detection (PG-001 adversarial finding)
# ---------------------------------------------------------------------

def test_orphan_policy_decision_record_with_no_matching_decision_is_caught(three_log_paths):
    """
    The PG-001 adversarial finding, closed. A PolicyDecisionRecord is
    fabricated for a module that was NEVER registered, at a
    (sequence_id, generation_id) where no real DecisionRecord was ever
    made -- nothing appended to the registration, decision, or audit
    logs at all. Before Check 5 existed, this passed
    verify_causal_history() cleanly: Checks 1-3 never inspect
    policy_decision_records, and Check 4 only ever walks FROM
    decision_records (of which there are none here), so it had nothing
    to compare against either. This is the "provenance gap" attack
    class named during adversarial review of PROVENANCE_GRAPH_MODEL.md:
    a valid-looking artifact introduced but never connected into the
    verification graph.
    """
    open(three_log_paths["registration"], "w", encoding="utf-8").close()
    open(three_log_paths["decision"], "w", encoding="utf-8").close()
    open(three_log_paths["audit"], "w", encoding="utf-8").close()

    orphan_policy_decision = _make_policy_decision("never_registered_module")
    orphan_policy_record = PolicyDecisionRecord(
        sequence_id=99, generation_id=_GEN_ID, policy_decision=orphan_policy_decision,
    )
    append_policy_decision_record(three_log_paths["policy_decision"], orphan_policy_record)

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is False
    assert any("Policy decision orphan" in f for f in report.failures)
    assert any("has no corresponding DecisionRecord at all" in f for f in report.failures)


def test_orphan_check_does_not_false_positive_on_correlated_records(three_log_paths):
    """
    Sanity check: Check 5 must not flag a genuinely correlated
    PolicyDecisionRecord as an orphan just because it exists. Reuses
    the same correlated-pair helper the Check 4 clean-path test
    already depends on.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    decision, policy_record = _make_correlated_decision_and_policy_record(1, "phoenix_a_core_v1")
    append_decision_record(three_log_paths["decision"], decision)
    append_policy_decision_record(three_log_paths["policy_decision"], policy_record)
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is True
    assert not any("orphan" in f.lower() for f in report.failures)

# ---------------------------------------------------------------------
# 8b. Check 5 -- identity, not just key co-occurrence (second PG-001
#     finding, 2026-08-08: distinct from the true-orphan attack above)
# ---------------------------------------------------------------------

def test_orphan_check_rejects_a_different_modules_decision_at_the_same_key(three_log_paths):
    """
    PG-001's second finding (2026-08-08), found via calibration attack
    against the provenance graph model itself, distinct from the
    MB-004 campaign. Check 5's original version confirmed only that
    SOME DecisionRecord existed at (sequence_id, generation_id) -- it
    never confirmed that DecisionRecord was actually the one this
    PolicyDecisionRecord's policy_decision describes. Confirmed via
    direct construction and execution before this fix: a genuine
    DecisionRecord for one module and a genuine PolicyDecisionRecord
    for a COMPLETELY DIFFERENT module, sharing only (sequence_id,
    generation_id), previously passed Check 5 with zero failures --
    despite different modules and different decision_hash values.
    Check 4 (the reverse direction) already defended against exactly
    this via decision_hash equality; Check 5 had no equivalent
    condition until this fix.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("module_A")
    )
    append_registration_record(
        three_log_paths["registration"], _make_registration("module_B")
    )

    # A real, valid DecisionRecord for module_B.
    decision_for_module_b = DecisionRecord(
        sequence_id=5,
        module_id="module_B",
        allowed=True,
        decision_hash=_hash32(b"unrelated_decision_for_B"),
        generation_id=_GEN_ID,
    )
    append_decision_record(three_log_paths["decision"], decision_for_module_b)
    append_audit_record(three_log_paths["audit"], _make_audit(5, "module_B"))

    # A real, valid PolicyDecisionRecord for module_A -- a completely
    # different module -- sharing only (sequence_id=5, generation_id).
    policy_decision_for_module_a = _make_policy_decision("module_A")
    policy_record_for_module_a = PolicyDecisionRecord(
        sequence_id=5, generation_id=_GEN_ID, policy_decision=policy_decision_for_module_a,
    )
    append_policy_decision_record(three_log_paths["policy_decision"], policy_record_for_module_a)

    # sanity: these two records really do disagree
    assert decision_for_module_b.module_id != policy_decision_for_module_a.module_id
    assert decision_for_module_b.decision_hash != policy_decision_for_module_a.decision_hash

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is False
    assert any(
        "does not correspond to any real decision at this key" in f
        for f in report.failures
    )


def test_orphan_check_still_passes_clean_on_genuinely_correlated_pair_after_identity_fix(three_log_paths):
    """
    Regression guard for the identity fix above: a genuinely correlated
    pair (same module, matching decision_hash, via the established
    _make_correlated_decision_and_policy_record() helper) must still
    pass clean -- the identity fix must not turn every real, legitimate
    pair into a false positive.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    decision, policy_record = _make_correlated_decision_and_policy_record(1, "phoenix_a_core_v1")
    append_decision_record(three_log_paths["decision"], decision)
    append_policy_decision_record(three_log_paths["policy_decision"], policy_record)
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.passed is True


# ---------------------------------------------------------------------
# 9. Check 6 -- decision execution completeness (reverse of Check 1)
# ---------------------------------------------------------------------

def test_mid_stream_decision_with_no_audit_is_caught(three_log_paths):
    """
    The core Check 6 attack, traced directly from
    deterministic_execution_engine.py's process_frame(): an allowed
    decision at sequence_id=1 has NO matching audit record, but a
    LATER decision (sequence_id=2) DOES have one -- proof execution
    continued past sequence_id=1, so its missing audit cannot be a
    legitimate trailing crash. Must be caught.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(three_log_paths["decision"], _make_decision(0, "phoenix_a_core_v1"))
    append_decision_record(three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1"))
    append_decision_record(three_log_paths["decision"], _make_decision(2, "phoenix_a_core_v1"))
    append_audit_record(three_log_paths["audit"], _make_audit(0, "phoenix_a_core_v1"))
    # sequence_id=1's audit deliberately never appended.
    append_audit_record(three_log_paths["audit"], _make_audit(2, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any(
        "Decision execution completeness" in f and "sequence_id=1" in f
        for f in report.failures
    )


def test_trailing_decision_with_no_audit_is_not_flagged(three_log_paths):
    """
    The deliberate exemption: the LAST allowed decision for a module
    has no audit record -- the legitimate "execution crashed, nothing
    came after" case, mirroring kernel_state_replay.py's own
    fully_verified property's treatment of a trailing fault. Must NOT
    be flagged.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(three_log_paths["decision"], _make_decision(0, "phoenix_a_core_v1"))
    append_decision_record(three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1"))
    append_decision_record(three_log_paths["decision"], _make_decision(2, "phoenix_a_core_v1"))
    append_audit_record(three_log_paths["audit"], _make_audit(0, "phoenix_a_core_v1"))
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))
    # sequence_id=2 is the LAST allowed decision and has no audit --
    # exempted, not a violation.

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is True
    assert not any("Decision execution completeness" in f for f in report.failures)


def test_trailing_exemption_is_scoped_per_generation_not_globally(three_log_paths):
    """
    The specific bug this fix was designed to avoid reintroducing:
    generation A's trailing decision (sequence_id=1, no audit -- a
    legitimate crash at the end of generation A) must stay exempted
    even though generation B, numerically overlapping on sequence_id,
    has LATER decisions with audits. Grouping by module_id alone
    (ignoring generation_id) would wrongly treat generation B's
    sequence_id=1/2 as "proof processing continued past generation A's
    sequence_id=1" -- they are unrelated kernel lifetimes. Confirms
    the (module_id, generation_id) scoping actually holds.
    """
    _GEN_B = b"\xBB" * 16

    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    # Generation A: decision 0 (with audit), decision 1 (trailing, no audit).
    append_decision_record(three_log_paths["decision"], _make_decision(0, "phoenix_a_core_v1"))
    append_decision_record(three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1"))
    append_audit_record(three_log_paths["audit"], _make_audit(0, "phoenix_a_core_v1"))

    # Generation B: fresh sequence numbering, decisions 0/1/2, all with audits.
    for seq_id in range(3):
        append_decision_record(
            three_log_paths["decision"],
            DecisionRecord(
                sequence_id=seq_id, module_id="phoenix_a_core_v1", allowed=True,
                decision_hash=_hash32(f"gen_b_{seq_id}".encode()), generation_id=_GEN_B,
            ),
        )
        append_audit_record(
            three_log_paths["audit"],
            ExecutionAuditRecord(
                sequence_id=seq_id, input_hash=_hash32(b"in"), prior_state_hash=_hash32(b"prior"),
                output_hash=_hash32(f"out_{seq_id}".encode()), module_id="phoenix_a_core_v1",
                success=True, frame_timestamp_ns=1000 + seq_id, generation_id=_GEN_B,
                error_message=None,
            ),
        )

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is True
    assert not any("Decision execution completeness" in f for f in report.failures)


def test_single_allowed_decision_no_audit_is_trivially_exempted(three_log_paths):
    """Sanity check: a single allowed decision with no audit is
    automatically its own "last" -- must never be flagged alone."""
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(three_log_paths["decision"], _make_decision(0, "phoenix_a_core_v1"))
    open(three_log_paths["audit"], "w", encoding="utf-8").close()

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is True
    assert not any("Decision execution completeness" in f for f in report.failures)


# ---------------------------------------------------------------------
# 10. Check 2 -- generation-scoped sequence ordering (found by accident
#     while testing Check 6, fixed with the same priority as Check 1)
# ---------------------------------------------------------------------

def test_sequence_numbering_resetting_across_a_real_generation_boundary_is_not_flagged(three_log_paths):
    """
    The exact false positive found by accident this session: a real,
    entirely legitimate multi-generation history for the SAME
    module_id -- sequence_id numerically resets to 0 in the new
    generation, exactly as it does after every real administrative
    reset (test_administrative_reset_clears_sequence_counters). Before
    the generation_id join-key fix, Check 2 would unconditionally flag
    this as "out of causal order" on every single reset, for any
    module, with no adversarial input required at all. Isolated here
    from Check 6 entirely (decisions and audits both fully paired) so
    this test targets Check 2 specifically.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )

    # Generation A: sequence_id 0, 1.
    append_decision_record(three_log_paths["decision"], _make_decision(0, "phoenix_a_core_v1"))
    append_decision_record(three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1"))
    append_audit_record(three_log_paths["audit"], _make_audit(0, "phoenix_a_core_v1"))
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    # Generation B: fresh sequence numbering, 0, 1 again -- the exact
    # pattern a real reset produces.
    _GEN_B = b"\xBB" * 16
    for seq_id in range(2):
        append_decision_record(
            three_log_paths["decision"],
            DecisionRecord(
                sequence_id=seq_id, module_id="phoenix_a_core_v1", allowed=True,
                decision_hash=_hash32(f"gen_b_{seq_id}".encode()), generation_id=_GEN_B,
            ),
        )
        append_audit_record(
            three_log_paths["audit"],
            ExecutionAuditRecord(
                sequence_id=seq_id, input_hash=_hash32(b"in"), prior_state_hash=_hash32(b"prior"),
                output_hash=_hash32(f"out_{seq_id}".encode()), module_id="phoenix_a_core_v1",
                success=True, frame_timestamp_ns=1000 + seq_id, generation_id=_GEN_B,
                error_message=None,
            ),
        )

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is True
    assert not any("Sequence ordering" in f for f in report.failures)


def test_genuine_out_of_order_within_one_generation_is_still_caught(three_log_paths):
    """
    Sanity check: the generation_id fix must not weaken Check 2's core
    purpose. A real out-of-order sequence WITHIN one generation must
    still be caught.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(three_log_paths["decision"], _make_decision(2, "phoenix_a_core_v1"))
    append_decision_record(three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1"))
    open(three_log_paths["audit"], "w", encoding="utf-8").close()

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any("Sequence ordering" in f and "out of causal order" in f for f in report.failures)


# ---------------------------------------------------------------------
# 11. Check 7 -- no contradictory decisions (CH-001 Omission finding)
# ---------------------------------------------------------------------

def test_contradictory_allowed_and_denied_decisions_at_same_key_are_caught(three_log_paths):
    """
    The CH-001 Omission finding: a (sequence_id, module_id,
    generation_id) key with BOTH an allowed and a denied
    DecisionRecord. Before Check 7 existed, Check 1's matching logic
    would silently accept any audit at this key -- the denial evidence
    disappearing from consideration the instant an allowed decision
    also existed there. This is exactly what a fabricated "laundering"
    attack would look like: append a fake allowed decision alongside a
    genuine denial. No audit records needed at all -- this check
    validates decision_records' own internal consistency directly.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(5, "phoenix_a_core_v1", allowed=False)
    )
    append_decision_record(
        three_log_paths["decision"],
        _make_decision(5, "phoenix_a_core_v1", allowed=True, hash_seed=b"fabricated"),
    )
    open(three_log_paths["audit"], "w", encoding="utf-8").close()

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is False
    assert any(
        "Contradictory decisions" in f and "sequence_id=5" in f
        for f in report.failures
    )


def test_no_false_positive_when_denied_and_allowed_decisions_are_at_different_keys(three_log_paths):
    """
    Sanity check: Check 7 must not flag ordinary, legitimate decision
    history where a denial and a later allowance simply happen for the
    same module at DIFFERENT sequence_ids -- only an exact key
    collision is contradictory.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1", allowed=False)
    )
    append_decision_record(
        three_log_paths["decision"], _make_decision(2, "phoenix_a_core_v1", allowed=True)
    )
    append_audit_record(three_log_paths["audit"], _make_audit(2, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.passed is True
    assert not any("Contradictory decisions" in f for f in report.failures)


# ---------------------------------------------------------------------
# 12. checks_run (closes the CH-004/CH-006 Omission finding)
# ---------------------------------------------------------------------

def test_checks_run_lists_all_six_always_run_checks_when_policy_log_omitted(three_log_paths):
    """
    Without policy_decision_log_path, checks_run must contain exactly
    the six checks that always execute -- and NOT the two optional
    ones, since they genuinely did not run.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    append_decision_record(three_log_paths["decision"], _make_decision(1, "phoenix_a_core_v1"))
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert report.checks_run == frozenset({
        "decision_ancestry",
        "decision_execution_completeness",
        "no_contradictory_decisions",
        "sequence_ordering_decision_log",
        "sequence_ordering_audit_log",
        "module_identity_cross_reference",
    })


def test_checks_run_includes_both_optional_checks_when_policy_log_supplied(three_log_paths):
    """
    With policy_decision_log_path supplied, checks_run must contain
    all eight checks, including the two optional ones -- this is the
    concrete signal a caller checking only .passed would have missed.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("phoenix_a_core_v1")
    )
    decision, policy_record = _make_correlated_decision_and_policy_record(1, "phoenix_a_core_v1")
    append_decision_record(three_log_paths["decision"], decision)
    append_policy_decision_record(three_log_paths["policy_decision"], policy_record)
    append_audit_record(three_log_paths["audit"], _make_audit(1, "phoenix_a_core_v1"))

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
        policy_decision_log_path=three_log_paths["policy_decision"],
    )

    assert report.checks_run == frozenset({
        "decision_ancestry",
        "decision_execution_completeness",
        "no_contradictory_decisions",
        "sequence_ordering_decision_log",
        "sequence_ordering_audit_log",
        "module_identity_cross_reference",
        "policy_decision_provenance",
        "policy_decision_orphans",
    })

def test_ambiguous_max_sequence_id_denies_the_trailing_exemption_to_both(three_log_paths):
    """
    Finding #1, CH-007's own seven-family campaign (2026-08-09), Duplication
    family. The trailing-crash exemption previously compared each decision's
    own sequence_id against the group's maximum value only -- it never asked
    whether that maximum was uniquely held. Two allowed decisions sharing
    the maximum sequence_id -- one genuinely missing its audit, one an
    arbitrary duplicate at the same value -- both received the exemption,
    since both satisfied "sequence_id == max" identically. Confirmed by
    direct construction and execution before this fix: this exact scenario
    produced zero failures across the entire pipeline, not just this check.

    Fixed: the exemption now requires the maximum sequence_id to be
    uniquely occupied by exactly one allowed decision. When two or more
    decisions share it, none are exempt -- each is checked individually
    against the audit log like any other decision.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("module_A")
    )

    decision_a = _make_decision(sequence_id=1, module_id="module_A", hash_seed=b"a")
    decision_b_incomplete = _make_decision(
        sequence_id=2, module_id="module_A", hash_seed=b"b_incomplete"
    )
    decision_b_twin = _make_decision(
        sequence_id=2, module_id="module_A", hash_seed=b"b_twin"
    )
    append_decision_record(three_log_paths["decision"], decision_a)
    append_decision_record(three_log_paths["decision"], decision_b_incomplete)
    append_decision_record(three_log_paths["decision"], decision_b_twin)

    append_audit_record(
        three_log_paths["audit"], _make_audit(sequence_id=1, module_id="module_A")
    )

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
    )

    assert report.passed is False
    matching_failures = [
        f for f in report.failures
        if "sequence_id=2" in f and "shares its sequence_id with" in f
    ]
    assert len(matching_failures) == 2

def test_denied_decision_at_later_sequence_id_counts_as_evidence_of_continuation(three_log_paths):
    """
    Finding #2, CH-007's own seven-family campaign (2026-08-09), Omission
    family. The original grouping filtered to `if d.allowed` before "last"
    was ever computed -- a DENIED decision at a later sequence_id (real
    evidence the engine reached that later frame's authorization step,
    which requires the earlier frame to have already resolved) was
    invisible to the exemption logic entirely. Confirmed by direct
    construction and execution before this fix: a single allowed decision
    with no audit, followed only by a denied decision at the next
    sequence_id, passed with zero failures across the whole pipeline.

    Fixed: "evidence of continuation" is now computed over ALL decisions
    at a (module_id, generation_id), not just allowed ones. A denied
    decision never itself needs an audit and is never flagged -- but its
    existence at a later position now correctly denies the trailing
    exemption to an earlier, genuinely incomplete allowed decision.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("module_A")
    )

    decision_incomplete = _make_decision(
        sequence_id=1, module_id="module_A", allowed=True, hash_seed=b"a"
    )
    decision_denied = _make_decision(
        sequence_id=2, module_id="module_A", allowed=False, hash_seed=b"b"
    )
    append_decision_record(three_log_paths["decision"], decision_incomplete)
    append_decision_record(three_log_paths["decision"], decision_denied)
    # three_log_paths only yields path strings -- the audit file must
    # still exist (even empty) for read_all_audit_records() to open it.
    open(three_log_paths["audit"], "w").close()

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
    )

    assert report.passed is False
    assert any(
        "sequence_id=1" in f and "LATER decisions exist" in f
        for f in report.failures
    )


def test_denied_decision_before_a_genuine_trailing_crash_is_not_a_false_positive(three_log_paths):
    """
    Regression guard for Finding #2's fix: a denied decision at an
    EARLIER position than a genuinely-last, unaudited allowed decision
    must not cause a false positive -- only a LATER decision (of any
    kind) counts as evidence of continuation.
    """
    append_registration_record(
        three_log_paths["registration"], _make_registration("module_A")
    )

    decision_denied_early = _make_decision(
        sequence_id=1, module_id="module_A", allowed=False, hash_seed=b"a"
    )
    decision_trailing_crash = _make_decision(
        sequence_id=2, module_id="module_A", allowed=True, hash_seed=b"b"
    )
    append_decision_record(three_log_paths["decision"], decision_denied_early)
    append_decision_record(three_log_paths["decision"], decision_trailing_crash)
    open(three_log_paths["audit"], "w").close()

    report = verify_causal_history(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
    )

    assert report.passed is True

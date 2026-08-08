"""
Historical Verification - Tests
(test_historical_verification.py)

Two categories: the four real outcomes for both record types (via
verify_decision_record_line / verify_execution_audit_record_line), and
the structural-guard tests proving HistoricalVerificationResult itself
refuses to be constructed with a recognition/verification combination
that would violate the "recognition is not verification" contract --
these are the tests that actually matter here, since they prove the
guard is enforced by the type itself, not merely followed by the two
verify_* functions that happen to use it correctly today.
"""

import pytest

from historical_verification import (
    VerificationOutcome,
    HistoricalVerificationResult,
    verify_decision_record_line,
    verify_execution_audit_record_line,
)


# ---------------------------------------------------------------------
# DecisionRecord -- four outcomes
# ---------------------------------------------------------------------

def test_current_schema_decision_record_passes():
    payload = {
        "sequence_id": 1,
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": "aa" * 32,
        "generation_id": "bb" * 16,
    }
    result = verify_decision_record_line(payload)

    assert result.outcome == VerificationOutcome.PASS
    assert result.schema_family is None
    assert result.record_type == "DecisionRecord"


def test_current_schema_decision_record_with_malformed_hash_fails():
    """
    All five current-schema keys present, but decision_hash is not a
    valid 32-byte hex string -- DecisionRecordValidationError, caught
    and surfaced as FAIL, not silently ignored.
    """
    payload = {
        "sequence_id": 1,
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": "deadbeef",  # 4 bytes, not 32
        "generation_id": "bb" * 16,
    }
    result = verify_decision_record_line(payload)

    assert result.outcome == VerificationOutcome.FAIL
    assert result.schema_family is None
    assert "reconstruction/verification failed" in result.detail


def test_pre_generation_id_decision_record_is_unsupported_not_pass_or_fail():
    payload = {
        "sequence_id": 1,
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": "aa" * 32,
    }
    result = verify_decision_record_line(payload)

    assert result.outcome == VerificationOutcome.UNSUPPORTED_HISTORICAL_FORMAT
    assert result.schema_family is not None
    assert "pre-generation_id" in result.schema_family
    # The actual point of this whole module:
    assert result.outcome != VerificationOutcome.PASS
    assert result.outcome != VerificationOutcome.FAIL


def test_corrupt_decision_record_is_corrupt():
    payload = {"garbage": "not a real payload"}
    result = verify_decision_record_line(payload)

    assert result.outcome == VerificationOutcome.CORRUPT
    assert result.schema_family is None


# ---------------------------------------------------------------------
# ExecutionAuditRecord -- four outcomes
# ---------------------------------------------------------------------

def test_current_schema_execution_audit_record_passes():
    payload = {
        "sequence_id": 1,
        "input_hash": "aa" * 32,
        "prior_state_hash": "bb" * 32,
        "output_hash": "cc" * 32,
        "module_id": "phoenix_a_core_v1",
        "success": True,
        "frame_timestamp_ns": 1000,
        "error_message": None,
        "generation_id": "dd" * 16,
    }
    result = verify_execution_audit_record_line(payload)

    assert result.outcome == VerificationOutcome.PASS
    assert result.schema_family is None


def test_current_schema_execution_audit_record_with_consistency_violation_fails():
    """
    success=True with a non-None error_message violates
    ExecutionAuditRecord's own consistency rule -- caught, surfaced as
    FAIL.
    """
    payload = {
        "sequence_id": 1,
        "input_hash": "aa" * 32,
        "prior_state_hash": "bb" * 32,
        "output_hash": "cc" * 32,
        "module_id": "phoenix_a_core_v1",
        "success": True,
        "frame_timestamp_ns": 1000,
        "error_message": "should not be here",
        "generation_id": "dd" * 16,
    }
    result = verify_execution_audit_record_line(payload)

    assert result.outcome == VerificationOutcome.FAIL


def test_pre_generation_id_execution_audit_record_is_unsupported():
    payload = {
        "sequence_id": 1,
        "input_hash": "aa" * 32,
        "prior_state_hash": "bb" * 32,
        "output_hash": "cc" * 32,
        "module_id": "phoenix_a_core_v1",
        "success": True,
        "frame_timestamp_ns": 1000,
        "error_message": None,
    }
    result = verify_execution_audit_record_line(payload)

    assert result.outcome == VerificationOutcome.UNSUPPORTED_HISTORICAL_FORMAT
    assert result.schema_family is not None
    assert result.outcome not in (VerificationOutcome.PASS, VerificationOutcome.FAIL)


def test_corrupt_execution_audit_record_is_corrupt():
    payload = {"sequence_id": 1}
    result = verify_execution_audit_record_line(payload)

    assert result.outcome == VerificationOutcome.CORRUPT
    assert result.schema_family is None


def test_non_dict_decision_record_payload_is_corrupt_not_uncaught_exception():
    """
    The exact gap VERIFICATION_PIPELINE_MODEL.md's own precision review
    found: a payload that isn't dict-shaped at all must resolve to
    CORRUPT, not raise AttributeError out of classification.
    """
    for bad_payload in (None, "not a dict", ["also", "not", "a", "dict"], 42):
        result = verify_decision_record_line(bad_payload)
        assert result.outcome == VerificationOutcome.CORRUPT
        assert result.schema_family is None


def test_non_dict_execution_audit_record_payload_is_corrupt_not_uncaught_exception():
    for bad_payload in (None, "not a dict", ["also", "not", "a", "dict"], 42):
        result = verify_execution_audit_record_line(bad_payload)
        assert result.outcome == VerificationOutcome.CORRUPT
        assert result.schema_family is None


# ---------------------------------------------------------------------
# Structural guards -- the actual proof the contract is enforced, not
# just followed by the two functions above
# ---------------------------------------------------------------------

def test_guard_rejects_historical_family_with_pass_outcome():
    """
    The exact misuse the whole contract exists to prevent: a
    HistoricalVerificationResult claiming a recognized historical
    schema was VERIFIED. Must raise, unconditionally, regardless of
    which function (or future function) tries to construct it.
    """
    with pytest.raises(ValueError, match="recognition is not verification"):
        HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family="DecisionRecord (pre-generation_id, RECORD_HASH_FORMAT_VERSION=1)",
            outcome=VerificationOutcome.PASS,
            detail="should never be constructible",
        )


def test_guard_rejects_historical_family_with_fail_outcome():
    with pytest.raises(ValueError, match="recognition is not verification"):
        HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family="DecisionRecord (pre-generation_id, RECORD_HASH_FORMAT_VERSION=1)",
            outcome=VerificationOutcome.FAIL,
            detail="should never be constructible",
        )


def test_guard_rejects_unsupported_historical_format_without_schema_family():
    with pytest.raises(ValueError, match="requires schema_family"):
        HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family=None,
            outcome=VerificationOutcome.UNSUPPORTED_HISTORICAL_FORMAT,
            detail="incoherent -- no named schema",
        )


def test_guard_rejects_corrupt_with_a_schema_family_set():
    with pytest.raises(ValueError, match="CORRUPT means no schema was recognized"):
        HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family="some schema",
            outcome=VerificationOutcome.CORRUPT,
            detail="incoherent -- CORRUPT should never name a schema",
        )


def test_guard_permits_pass_with_no_schema_family():
    """Sanity: the guard doesn't over-reject legitimate combinations."""
    result = HistoricalVerificationResult(
        record_type="DecisionRecord",
        schema_family=None,
        outcome=VerificationOutcome.PASS,
        detail="fine",
    )
    assert result.outcome == VerificationOutcome.PASS


def test_guard_permits_unsupported_historical_format_with_schema_family():
    """Sanity: the one combination that SHOULD succeed does."""
    result = HistoricalVerificationResult(
        record_type="DecisionRecord",
        schema_family="some recognized schema",
        outcome=VerificationOutcome.UNSUPPORTED_HISTORICAL_FORMAT,
        detail="fine",
    )
    assert result.outcome == VerificationOutcome.UNSUPPORTED_HISTORICAL_FORMAT

def test_decision_record_dispatch_raises_on_unrecognized_schema_recognition_value():
    """
    Latent exhaustiveness finding (2026-08-08): verify_decision_record_line()
    previously reached its CURRENT_SCHEMA verification branch purely by
    eliminating RECOGNIZED_HISTORICAL_SCHEMA and UNRECOGNIZED, assuming
    (via comment, never a check) that anything remaining must be
    CURRENT_SCHEMA. SchemaRecognition has exactly three members today,
    so this was correct -- but nothing enforced it. This test cannot
    add a real fourth SchemaRecognition member (that would require
    editing historical_schema_recognition.py itself), so it simulates
    the shape of the risk directly: monkeypatching
    classify_decision_record_payload() to return a classification whose
    .recognition is not any of the three real SchemaRecognition values,
    confirming the dispatch now fails loudly rather than silently
    attempting real verification against an unrecognized state.
    """
    import historical_verification as hv
    from dataclasses import dataclass
    from typing import Optional

    class _FakeFutureRecognition:
        """Deliberately NOT a SchemaRecognition member -- stands in for
        a hypothetical future enum value this dispatch doesn't know
        about yet."""
        name = "PARTIALLY_RECOGNIZED"
        def __repr__(self):
            return "_FakeFutureRecognition.PARTIALLY_RECOGNIZED"

    @dataclass
    class _FakeClassification:
        recognition: object
        schema_name: Optional[str] = None

    original = hv.classify_decision_record_payload
    hv.classify_decision_record_payload = lambda payload: _FakeClassification(
        recognition=_FakeFutureRecognition()
    )
    try:
        with pytest.raises(ValueError, match="Unrecognized SchemaRecognition value"):
            hv.verify_decision_record_line({"some": "payload"})
    finally:
        hv.classify_decision_record_payload = original


def test_execution_audit_record_dispatch_raises_on_unrecognized_schema_recognition_value():
    """
    Same finding, ExecutionAuditRecord side -- see the DecisionRecord
    version's docstring for the full rationale.
    """
    import historical_verification as hv
    from dataclasses import dataclass
    from typing import Optional

    class _FakeFutureRecognition:
        name = "PARTIALLY_RECOGNIZED"
        def __repr__(self):
            return "_FakeFutureRecognition.PARTIALLY_RECOGNIZED"

    @dataclass
    class _FakeClassification:
        recognition: object
        schema_name: Optional[str] = None

    original = hv.classify_execution_audit_record_payload
    hv.classify_execution_audit_record_payload = lambda payload: _FakeClassification(
        recognition=_FakeFutureRecognition()
    )
    try:
        with pytest.raises(ValueError, match="Unrecognized SchemaRecognition value"):
            hv.verify_execution_audit_record_line({"some": "payload"})
    finally:
        hv.classify_execution_audit_record_payload = original

"""
Historical Schema Recognition - Tests
(test_historical_schema_recognition.py)

Three categories per record type: a payload matching the current
schema exactly, a payload matching the known pre-generation_id
historical schema exactly, and payloads that match neither. Plus one
edge case proving the strict-matching design choice: a payload with
every current field PLUS one unexpected extra key must NOT be silently
accepted as "current schema."
"""

from historical_schema_recognition import (
    SchemaRecognition,
    classify_decision_record_payload,
    classify_execution_audit_record_payload,
)


# ---------------------------------------------------------------------
# DecisionRecord
# ---------------------------------------------------------------------

def test_current_decision_record_schema_recognized():
    payload = {
        "sequence_id": 1,
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": "aa" * 32,
        "generation_id": "bb" * 16,
    }
    result = classify_decision_record_payload(payload)

    assert result.recognition == SchemaRecognition.CURRENT_SCHEMA
    assert result.verifiable_by_current_code is True
    assert "Matches the current schema" in result.explanation()


def test_pre_generation_id_decision_record_schema_recognized():
    """
    The exact field set every pre-generation_id DecisionRecord test
    helper in this codebase constructed, confirmed directly from this
    session's own failing-test evidence -- not a guess.
    """
    payload = {
        "sequence_id": 1,
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": "aa" * 32,
    }
    result = classify_decision_record_payload(payload)

    assert result.recognition == SchemaRecognition.RECOGNIZED_HISTORICAL_SCHEMA
    assert result.verifiable_by_current_code is False
    assert result.schema_name is not None
    assert "pre-generation_id" in result.schema_name
    assert result.missing_fields == frozenset({"generation_id"})
    explanation = result.explanation()
    assert "valid but unverifiable under current rules" in explanation
    assert "historical verifier" in explanation


def test_genuinely_corrupt_decision_record_payload_unrecognized():
    payload = {"garbage": "not a real payload at all"}
    result = classify_decision_record_payload(payload)

    assert result.recognition == SchemaRecognition.UNRECOGNIZED
    assert result.verifiable_by_current_code is False
    assert result.schema_name is None
    explanation = result.explanation()
    assert "Unrecognized" in explanation
    assert "unsupported historical schema" in explanation


def test_decision_record_with_extra_unexpected_field_is_not_silently_accepted():
    """
    All five current fields present, PLUS one extra key. Must NOT be
    classified as CURRENT_SCHEMA -- exact key-set matching, no
    leniency for "close enough."
    """
    payload = {
        "sequence_id": 1,
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": "aa" * 32,
        "generation_id": "bb" * 16,
        "some_future_field_not_yet_known": "unexpected",
    }
    result = classify_decision_record_payload(payload)

    assert result.recognition == SchemaRecognition.UNRECOGNIZED
    assert "some_future_field_not_yet_known" in result.unexpected_fields


# ---------------------------------------------------------------------
# ExecutionAuditRecord
# ---------------------------------------------------------------------

def test_current_execution_audit_record_schema_recognized():
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
    result = classify_execution_audit_record_payload(payload)

    assert result.recognition == SchemaRecognition.CURRENT_SCHEMA
    assert result.verifiable_by_current_code is True


def test_pre_generation_id_execution_audit_record_schema_recognized():
    """
    The exact field set every pre-generation_id ExecutionAuditRecord
    test helper in this codebase constructed, confirmed directly from
    this session's own failing-test evidence.
    """
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
    result = classify_execution_audit_record_payload(payload)

    assert result.recognition == SchemaRecognition.RECOGNIZED_HISTORICAL_SCHEMA
    assert result.verifiable_by_current_code is False
    assert result.missing_fields == frozenset({"generation_id"})
    assert "valid but unverifiable under current rules" in result.explanation()


def test_genuinely_corrupt_execution_audit_record_payload_unrecognized():
    payload = {"sequence_id": 1}  # missing everything else
    result = classify_execution_audit_record_payload(payload)

    assert result.recognition == SchemaRecognition.UNRECOGNIZED
    assert result.verifiable_by_current_code is False


def test_execution_audit_record_with_extra_unexpected_field_is_not_silently_accepted():
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
        "unexpected": "field",
    }
    result = classify_execution_audit_record_payload(payload)

    assert result.recognition == SchemaRecognition.UNRECOGNIZED
    assert "unexpected" in result.unexpected_fields


# ---------------------------------------------------------------------
# Cross-cutting: the two record types' classifiers are independent
# ---------------------------------------------------------------------

def test_decision_record_payload_is_not_recognized_by_audit_record_classifier():
    """
    A well-formed, current-schema DecisionRecord payload run through
    the WRONG classifier (execution audit record's) must not be
    accidentally recognized as anything -- the two record types'
    schemas share no fields in common by coincidence at the current
    field-name set, but this confirms it explicitly rather than
    assuming it.
    """
    decision_payload = {
        "sequence_id": 1,
        "module_id": "phoenix_a_core_v1",
        "allowed": True,
        "decision_hash": "aa" * 32,
        "generation_id": "bb" * 16,
    }
    result = classify_execution_audit_record_payload(decision_payload)

    assert result.recognition == SchemaRecognition.UNRECOGNIZED

def test_overlapping_historical_schemas_are_rejected_at_import_time():
    """
    Finding, SE-002's own seven-family campaign (2026-08-10), Duplication
    family. Confirmed by direct construction and execution before this
    fix: two historical schema entries sharing an identical field-name
    set caused the FIRST one in the list to silently win, with zero
    indication the ambiguity existed -- reversing list order flipped
    which schema name got reported. Not reachable through any live call
    path today (only one historical schema entry exists per real record
    type) -- the same "risk is future code evolution" shape as VP-001's
    own finding.

    Fixed: _validate_historical_schemas_are_pairwise_distinct() now runs
    at import time for both real record types' historical-schema lists,
    and is tested here directly against a deliberately constructed
    colliding pair.
    """
    from historical_schema_recognition import _validate_historical_schemas_are_pairwise_distinct

    shared_fields = frozenset({"sequence_id", "module_id", "allowed", "decision_hash"})
    colliding_schemas = [
        ("Schema A", shared_fields),
        ("Schema B, same fields", shared_fields),
    ]

    try:
        _validate_historical_schemas_are_pairwise_distinct("DecisionRecord", colliding_schemas)
        assert False, "expected AssertionError for colliding historical schemas, none was raised"
    except AssertionError as e:
        assert "IDENTICAL field set" in str(e)

def test_real_historical_schema_lists_are_genuinely_distinct():
    """
    Confirms the real, live constants pass the new validator -- the
    module already imports successfully (proving this implicitly), but
    this test makes the guarantee explicit and named, not merely
    incidental to a successful import.
    """
    from historical_schema_recognition import (
        _validate_historical_schemas_are_pairwise_distinct,
        _DECISION_RECORD_HISTORICAL_SCHEMAS,
        _EXECUTION_AUDIT_RECORD_HISTORICAL_SCHEMAS,
    )

    _validate_historical_schemas_are_pairwise_distinct(
        "DecisionRecord", _DECISION_RECORD_HISTORICAL_SCHEMAS
    )
    _validate_historical_schemas_are_pairwise_distinct(
        "ExecutionAuditRecord", _EXECUTION_AUDIT_RECORD_HISTORICAL_SCHEMAS
    )


def test_non_dict_payload_is_gracefully_unrecognized_not_a_crash():
    """
    Finding, SE-002's own seven-family campaign (2026-08-10), Omission
    family. Confirmed by direct execution before this fix:
    classify_decision_record_payload() raised an uncaught AttributeError
    on non-dict input ('list' object has no attribute 'keys') rather than
    returning a graceful UNRECOGNIZED classification. Both real callers
    already guard with isinstance(payload, dict) before calling this
    function, so no live path reached this gap -- but the function itself
    was not defensive.

    Fixed: _classify() (and both classify_*_payload() wrappers built on
    it) now return UNRECOGNIZED directly for non-dict input.
    """
    from historical_schema_recognition import (
        classify_decision_record_payload,
        classify_execution_audit_record_payload,
        SchemaRecognition,
    )

    for bad_payload in [["not", "a", "dict"], "also not a dict", 42, None]:
        result = classify_decision_record_payload(bad_payload)
        assert result.recognition == SchemaRecognition.UNRECOGNIZED

        result = classify_execution_audit_record_payload(bad_payload)
        assert result.recognition == SchemaRecognition.UNRECOGNIZED

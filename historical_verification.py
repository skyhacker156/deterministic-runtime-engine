"""
Historical Verification - Sentinel Framework
(historical_verification.py)

Answers the question historical_schema_recognition.py deliberately
does NOT: is this record actually valid, not just shaped like
something we recognize. Produces one of four outcomes per record line
-- an "evidence system" upgrade from the binary PASS/FAIL every other
verifier in this codebase currently offers:

    PASS                          -- current schema, real construction
                                      via the actual record class
                                      succeeded, hash recomputed clean
    FAIL                          -- current schema, but construction
                                      or hash recomputation failed
    UNSUPPORTED_HISTORICAL_FORMAT -- recognized as a known prior
                                      schema; NOT verified, by policy
    CORRUPT                       -- matches no known schema at all

===========================================================================
CONTRACT: RECOGNITION IS NOT VERIFICATION -- THE COMPOSING SIDE
===========================================================================
historical_schema_recognition.py's own docstring states this contract
from the pure-recognition side: that module has no capability to
verify anything, by construction, so it cannot be misused to produce a
false verification claim.

This module is the other half of that same contract. It is the ONLY
place in this codebase where a RECOGNIZED_HISTORICAL_SCHEMA
classification is ever combined with real verification machinery --
and the combination is deliberately asymmetric:

    RECOGNIZED_HISTORICAL_SCHEMA  ALWAYS produces UNSUPPORTED_HISTORICAL_FORMAT.
    NEVER PASS. NEVER FAIL. There is no code path in this module,
    under any input, that constructs a HistoricalVerificationResult
    with schema_family set AND outcome in (PASS, FAIL). This is not
    just documented -- HistoricalVerificationResult.__post_init__
    RAISES if that combination is ever constructed, anywhere, by
    anyone, including future edits to this file. See its docstring
    below for the exact guard.

PASS is reached by exactly one path: the payload classifies as
CURRENT_SCHEMA, AND the actual record class (DecisionRecord's real
decision_record_from_json(), ExecutionAuditRecord's real
audit_record_from_json() -- never reimplemented, matching this
project's standing SHALL-5 principle) successfully reconstructs the
record with no exception. Nothing about "this looks like an old
schema" or "this looks like it used to be valid" can ever produce
PASS. Recognizing a shape and verifying a claim are different
operations performed by different code in different files; this
module's only job is to combine their OUTPUTS honestly, never to blur
their MEANINGS.
===========================================================================
"""

import json
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional

from historical_schema_recognition import (
    SchemaRecognition,
    classify_decision_record_payload,
    classify_execution_audit_record_payload,
)
from decision_record_persistence import decision_record_from_json
from execution_audit_persistence import audit_record_from_json


class VerificationOutcome(Enum):
    PASS = auto()
    FAIL = auto()
    UNSUPPORTED_HISTORICAL_FORMAT = auto()
    CORRUPT = auto()


@dataclass(frozen=True)
class HistoricalVerificationResult:
    """
    record_type: which record type this result is about (e.g.
    "DecisionRecord"), for a caller juggling results across log types.

    schema_family: the recognized historical schema's name (from
    SchemaClassification.schema_name), set if and ONLY if outcome is
    UNSUPPORTED_HISTORICAL_FORMAT. None for every other outcome --
    PASS/FAIL apply only to the current schema, and CORRUPT means no
    schema was recognized at all, so there is nothing to name.

    outcome: the four-way VerificationOutcome.

    detail: human-readable explanation. For UNSUPPORTED_HISTORICAL_FORMAT
    and CORRUPT, this is SchemaClassification.explanation() verbatim --
    the same message historical_schema_recognition.py would produce on
    its own, not reworded here.

    STRUCTURAL GUARD, not just documentation: __post_init__ enforces
    that schema_family and outcome can never combine into a claim that
    a recognized historical record was verified. This is the concrete
    mechanism behind this module's "recognition is not verification"
    contract -- a future maintainer cannot accidentally construct
    HistoricalVerificationResult(schema_family="...", outcome=PASS)
    and have it silently succeed. It raises.
    """
    record_type: str
    schema_family: Optional[str]
    outcome: VerificationOutcome
    detail: str

    def __post_init__(self) -> None:
        if self.schema_family is not None and self.outcome in (
            VerificationOutcome.PASS,
            VerificationOutcome.FAIL,
        ):
            raise ValueError(
                f"Structural contract violation: a HistoricalVerificationResult "
                f"with schema_family={self.schema_family!r} can never have "
                f"outcome={self.outcome.name} -- recognition is not "
                f"verification. A recognized historical schema can only ever "
                f"resolve to UNSUPPORTED_HISTORICAL_FORMAT. This guard exists "
                f"specifically to make it impossible to construct a result "
                f"that looks like a historical record was verified when it "
                f"was, at most, recognized."
            )
        if self.outcome == VerificationOutcome.UNSUPPORTED_HISTORICAL_FORMAT and self.schema_family is None:
            raise ValueError(
                "UNSUPPORTED_HISTORICAL_FORMAT requires schema_family to name "
                "which recognized historical schema this is -- this outcome "
                "with no named schema is not a coherent state."
            )
        if self.outcome == VerificationOutcome.CORRUPT and self.schema_family is not None:
            raise ValueError(
                "CORRUPT means no schema was recognized at all -- "
                "schema_family must be None. If a schema WAS recognized, the "
                "outcome is UNSUPPORTED_HISTORICAL_FORMAT, not CORRUPT."
            )


def verify_decision_record_line(payload: Dict) -> HistoricalVerificationResult:
    """
    The only entry point that can produce PASS or FAIL for a
    DecisionRecord line. Recognition (historical_schema_recognition.py)
    always runs first and is always checked before any verification is
    attempted -- see the module docstring's contract.

    Guards against non-dict-shaped input explicitly (added after
    VERIFICATION_PIPELINE_MODEL.md's own precision review flagged this
    as an uncaught-exception gap): a payload that isn't a dict at all
    cannot be classified, and classify_decision_record_payload() would
    raise AttributeError on payload.keys() rather than returning any of
    the four defined outcomes. CORRUPT is the correct semantic answer
    here -- an unparseable shape matches neither the current nor any
    known historical schema -- so this is checked explicitly before
    classification runs, not left to an uncaught exception.
    """
    if not isinstance(payload, dict):
        return HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family=None,
            outcome=VerificationOutcome.CORRUPT,
            detail=(
                f"Payload is not a dict-shaped object (got "
                f"{type(payload).__name__}); cannot classify or verify."
            ),
        )

    classification = classify_decision_record_payload(payload)

    if classification.recognition == SchemaRecognition.RECOGNIZED_HISTORICAL_SCHEMA:
        return HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family=classification.schema_name,
            outcome=VerificationOutcome.UNSUPPORTED_HISTORICAL_FORMAT,
            detail=classification.explanation(),
        )

    if classification.recognition == SchemaRecognition.UNRECOGNIZED:
        return HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family=None,
            outcome=VerificationOutcome.CORRUPT,
            detail=classification.explanation(),
        )

    # CURRENT_SCHEMA: the only branch where real verification is
    # attempted at all. Always via the actual class, never reimplemented.
    try:
        decision_record_from_json(json.dumps(payload))
        return HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family=None,
            outcome=VerificationOutcome.PASS,
            detail="Current schema; DecisionRecord reconstructed and record_hash recomputed successfully.",
        )
    except Exception as e:
        return HistoricalVerificationResult(
            record_type="DecisionRecord",
            schema_family=None,
            outcome=VerificationOutcome.FAIL,
            detail=f"Current schema, but reconstruction/verification failed: {e}",
        )


def verify_execution_audit_record_line(payload: Dict) -> HistoricalVerificationResult:
    """
    Same shape as verify_decision_record_line(), for ExecutionAuditRecord,
    including the same non-dict-input guard.
    """
    if not isinstance(payload, dict):
        return HistoricalVerificationResult(
            record_type="ExecutionAuditRecord",
            schema_family=None,
            outcome=VerificationOutcome.CORRUPT,
            detail=(
                f"Payload is not a dict-shaped object (got "
                f"{type(payload).__name__}); cannot classify or verify."
            ),
        )

    classification = classify_execution_audit_record_payload(payload)

    if classification.recognition == SchemaRecognition.RECOGNIZED_HISTORICAL_SCHEMA:
        return HistoricalVerificationResult(
            record_type="ExecutionAuditRecord",
            schema_family=classification.schema_name,
            outcome=VerificationOutcome.UNSUPPORTED_HISTORICAL_FORMAT,
            detail=classification.explanation(),
        )

    if classification.recognition == SchemaRecognition.UNRECOGNIZED:
        return HistoricalVerificationResult(
            record_type="ExecutionAuditRecord",
            schema_family=None,
            outcome=VerificationOutcome.CORRUPT,
            detail=classification.explanation(),
        )

    try:
        audit_record_from_json(json.dumps(payload))
        return HistoricalVerificationResult(
            record_type="ExecutionAuditRecord",
            schema_family=None,
            outcome=VerificationOutcome.PASS,
            detail="Current schema; ExecutionAuditRecord reconstructed and audit_hash recomputed successfully.",
        )
    except Exception as e:
        return HistoricalVerificationResult(
            record_type="ExecutionAuditRecord",
            schema_family=None,
            outcome=VerificationOutcome.FAIL,
            detail=f"Current schema, but reconstruction/verification failed: {e}",
        )

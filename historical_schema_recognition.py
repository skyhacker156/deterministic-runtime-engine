"""
Historical Schema Recognition - Sentinel Framework
(historical_schema_recognition.py)

Implements SCHEMA_EVOLUTION_MODEL.md's archival-boundary policy in its
smallest, most concrete form: NOT migration, NOT backward-compatible
reconstruction -- recognition only. Given a raw, already-JSON-parsed
payload dict from one persisted log line, answers "what am I looking
at" precisely enough to distinguish three genuinely different
situations this codebase's existing *_from_json()/*LogCorruptionError
handling currently conflates into one undifferentiated failure:

  1. CURRENT_SCHEMA -- matches what the current code expects. Normal
     *_from_json() parsing applies; this module has nothing to add.

  2. RECOGNIZED_HISTORICAL_SCHEMA -- does NOT match the current
     schema, but DOES match a SPECIFIC, KNOWN prior schema version
     (currently: DecisionRecord and ExecutionAuditRecord as they
     existed before the generation_id migration). Per
     SCHEMA_EVOLUTION_MODEL.md's archival-boundary policy, this
     codebase does NOT attempt to verify such a record's hashes --
     that would require the historical verifier (checking out the git
     commit predating the migration). This module's job is to say so
     explicitly and precisely, not to attempt it.

  3. UNRECOGNIZED -- matches neither the current schema nor any known
     historical schema. Genuinely ambiguous: could be real corruption,
     could be an unsupported historical schema this module has no
     record of, could be an unrelated record type's payload entirely.
     This module makes NO claim about which of those it is -- it only
     confirms recognition failed, so the caller's existing
     corruption-handling path is still the right response, now
     clearly distinguished from case 2 rather than silently lumped in
     with it.

DELIBERATELY NOT BUILT HERE, matching SCHEMA_EVOLUTION_MODEL.md's own
scope boundary: no reconstruction of a usable record object under an
old schema's semantics, no hash verification under a superseded
algorithm, no schema_version dispatch mechanism. This module answers
"what is this" -- nothing more. It is the smallest concrete step the
archival-boundary policy's philosophy can be tested against without
building the migration infrastructure that policy explicitly declines
to build.

===========================================================================
CONTRACT: RECOGNITION IS NOT VERIFICATION. THIS IS THE ENTIRE POINT.
===========================================================================
A SchemaClassification of RECOGNIZED_HISTORICAL_SCHEMA means exactly
this and nothing more: "this payload's key set matches a schema this
codebase once used." It does NOT mean:

  - the record's hash is valid
  - the record's fields are internally consistent
  - the record can be trusted
  - the record has been checked in any cryptographic sense at all

This module NEVER constructs a real record object. It never calls
hashlib. It never imports decision_record_contract.py,
execution_audit_contract.py, decision_record_persistence.py, or any
module capable of actually verifying a hash. This is not an oversight
-- it is the mechanism that makes the contract impossible to violate
by accident. A future maintainer cannot accidentally turn
"recognized historical schema" into "verified current truth" FROM
THIS MODULE, because this module has no verification capability to
misuse in the first place.

Real verification -- actually constructing a record via its real
class and confirming its hash recomputes correctly -- is a genuinely
different, separate capability, requiring genuinely different
(heavier) dependencies. See historical_verification.py, which
composes THIS module's recognition output with real verification from
the actual persistence modules, and produces a four-way
VerificationOutcome (PASS / FAIL / UNSUPPORTED_HISTORICAL_FORMAT /
CORRUPT) precisely BECAUSE the two capabilities are kept in separate
files -- that module's own docstring restates this same contract from
the composing side. If you are looking for a function that tells you
whether a record is cryptographically sound, it is not in this file,
and that absence is deliberate.
===========================================================================

Zero dependency on the live record contract modules or any runtime
state. The known field-name sets below are declared directly as data,
not derived by importing decision_record_contract.py or
execution_audit_contract.py -- this module carries no risk of
repeating the transitive-import isolation problem
test_verifier_runtime_isolation.py already caught once this session
(see execution_policy_decision_contract.py's own docstring for that
history). Meant to be usable from the same pure, disk-only context
causal_history_verifier.py already establishes, though it is not
wired into that verifier as of this module's introduction -- see this
module's own accompanying discussion for why that wiring is a
separate, not-yet-made decision.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, FrozenSet, List, Optional, Tuple


class SchemaRecognition(Enum):
    CURRENT_SCHEMA = auto()
    RECOGNIZED_HISTORICAL_SCHEMA = auto()
    UNRECOGNIZED = auto()


@dataclass(frozen=True)
class SchemaClassification:
    """
    Result of classifying one payload dict against a record type's
    known schemas (current and historical). Carries enough detail for
    a caller to construct a precise, honest message rather than a
    single undifferentiated failure -- see explanation() below for the
    three distinct messages this maps to.
    """
    recognition: SchemaRecognition
    schema_name: Optional[str]
    missing_fields: FrozenSet[str] = field(default_factory=frozenset)
    unexpected_fields: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def verifiable_by_current_code(self) -> bool:
        """
        Only CURRENT_SCHEMA payloads are verifiable by current code --
        matches SCHEMA_EVOLUTION_MODEL.md's archival-boundary policy
        exactly: a recognized historical schema is real and was once
        valid, but this codebase does not attempt to recompute its
        hashes under an algorithm that predates the current one.
        """
        return self.recognition == SchemaRecognition.CURRENT_SCHEMA

    def explanation(self) -> str:
        if self.recognition == SchemaRecognition.CURRENT_SCHEMA:
            return "Matches the current schema. Normal parsing applies."

        if self.recognition == SchemaRecognition.RECOGNIZED_HISTORICAL_SCHEMA:
            return (
                f"Recognized historical schema: {self.schema_name}. "
                f"This record is valid but unverifiable under current rules -- "
                f"per SCHEMA_EVOLUTION_MODEL.md's archival-boundary policy, this "
                f"codebase does not reconstruct hashes under a superseded "
                f"algorithm. Verifying this record requires the historical "
                f"verifier: check out the git commit predating the schema "
                f"change that introduced {sorted(self.missing_fields)!r} as "
                f"required field(s)."
            )

        return (
            f"Unrecognized. Matches neither the current schema nor any known "
            f"historical one. Missing fields (relative to current): "
            f"{sorted(self.missing_fields)!r}. Unexpected fields: "
            f"{sorted(self.unexpected_fields)!r}. This may be genuine "
            f"corruption, an unsupported historical schema this module has no "
            f"record of, or an unrelated record type's payload -- this module "
            f"does not distinguish those cases; it only confirms recognition "
            f"failed."
        )


# ---------------------------------------------------------------------
# Known schemas, declared directly as data -- not derived from the live
# contract modules. Each entry is the exact set of keys that record
# type's *_to_json() wrote at that point in this project's history.
# Confirmed against this session's own failing-test evidence (the
# missing-generation_id TypeErrors), not reconstructed from memory.
# ---------------------------------------------------------------------

_DECISION_RECORD_CURRENT_FIELDS: FrozenSet[str] = frozenset({
    "sequence_id", "module_id", "allowed", "decision_hash", "generation_id",
})
_DECISION_RECORD_HISTORICAL_SCHEMAS: List[Tuple[str, FrozenSet[str]]] = [
    (
        "DecisionRecord (pre-generation_id, RECORD_HASH_FORMAT_VERSION=1)",
        frozenset({"sequence_id", "module_id", "allowed", "decision_hash"}),
    ),
]

_EXECUTION_AUDIT_RECORD_CURRENT_FIELDS: FrozenSet[str] = frozenset({
    "sequence_id", "input_hash", "prior_state_hash", "output_hash",
    "module_id", "success", "frame_timestamp_ns", "error_message",
    "generation_id",
})
_EXECUTION_AUDIT_RECORD_HISTORICAL_SCHEMAS: List[Tuple[str, FrozenSet[str]]] = [
    (
        "ExecutionAuditRecord (pre-generation_id, first hash-format-version "
        "byte not yet introduced)",
        frozenset({
            "sequence_id", "input_hash", "prior_state_hash", "output_hash",
            "module_id", "success", "frame_timestamp_ns", "error_message",
        }),
    ),
]


def classify_decision_record_payload(payload: Dict) -> SchemaClassification:
    return _classify(
        payload,
        current_fields=_DECISION_RECORD_CURRENT_FIELDS,
        historical_schemas=_DECISION_RECORD_HISTORICAL_SCHEMAS,
    )


def classify_execution_audit_record_payload(payload: Dict) -> SchemaClassification:
    return _classify(
        payload,
        current_fields=_EXECUTION_AUDIT_RECORD_CURRENT_FIELDS,
        historical_schemas=_EXECUTION_AUDIT_RECORD_HISTORICAL_SCHEMAS,
    )


def _classify(
    payload: Dict,
    current_fields: FrozenSet[str],
    historical_schemas: List[Tuple[str, FrozenSet[str]]],
) -> SchemaClassification:
    """
    Exact key-set matching, deliberately strict: a payload with every
    current field PLUS one unexpected extra key does NOT count as
    "current schema" -- it's flagged as UNRECOGNIZED instead, since it
    doesn't cleanly match anything this module actually knows about.
    Same treatment for a near-miss on a historical schema. Silently
    accepting "close enough" would be exactly the kind of unstated
    leniency SCHEMA_EVOLUTION_MODEL.md's whole point is to avoid.
    """
    payload_keys = frozenset(payload.keys())

    if payload_keys == current_fields:
        return SchemaClassification(recognition=SchemaRecognition.CURRENT_SCHEMA, schema_name="current")

    for schema_name, historical_fields in historical_schemas:
        if payload_keys == historical_fields:
            return SchemaClassification(
                recognition=SchemaRecognition.RECOGNIZED_HISTORICAL_SCHEMA,
                schema_name=schema_name,
                missing_fields=current_fields - historical_fields,
                unexpected_fields=historical_fields - current_fields,
            )

    return SchemaClassification(
        recognition=SchemaRecognition.UNRECOGNIZED,
        schema_name=None,
        missing_fields=current_fields - payload_keys,
        unexpected_fields=payload_keys - current_fields,
    )

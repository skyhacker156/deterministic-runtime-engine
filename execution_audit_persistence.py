"""
Execution Audit Record - Persistence Helpers
(execution_audit_persistence.py)

Same scope discipline as the other two persistence helper files: answers
whether ExecutionAuditRecord survives a serialize/deserialize round-trip,
nothing about crash recovery, envelopes, or versioning.

This record has the most hash surface area of the three: THREE
independent 32-byte fields (input_hash, prior_state_hash, output_hash),
all of which are, per the contract's own docstring, references to
hashes computed elsewhere (CoreExecutionFrame.provenance_hash,
KernelStateEnvelope.state_hash, ExecutionResult.module_hash) -- this
record never recomputes them, only observes them. Persistence must
therefore preserve all three byte-for-byte, unchanged, the same way
DecisionRecord.decision_hash had to be preserved opaque.

audit_hash itself IS derived (computed once in __post_init__ from every
field except error_message's None case) and must recompute identically
on reconstruction -- same category of check as DecisionRecord.record_hash
and ModuleRegistrationAttemptRecord.attempt_hash.
"""

import json

from execution_audit_contract import ExecutionAuditRecord


def audit_record_to_json(record: ExecutionAuditRecord) -> str:
    """
    Serializes an ExecutionAuditRecord to a JSON string. audit_hash is
    NOT written -- it's derived, and __post_init__ always recomputes it
    on reconstruction. See audit_record_from_json().
    """
    payload = {
        "sequence_id": record.sequence_id,
        "input_hash": record.input_hash.hex(),
        "prior_state_hash": record.prior_state_hash.hex(),
        "output_hash": record.output_hash.hex(),
        "module_id": record.module_id,
        "success": record.success,
        "frame_timestamp_ns": record.frame_timestamp_ns,
        "error_message": record.error_message,
    }
    return json.dumps(payload, sort_keys=True)


def audit_record_from_json(json_str: str) -> ExecutionAuditRecord:
    """
    Reconstructs an ExecutionAuditRecord from JSON produced by
    audit_record_to_json(). audit_hash is always recomputed by
    __post_init__ from the real fields -- never read from storage.
    """
    payload = json.loads(json_str)
    return ExecutionAuditRecord(
        sequence_id=payload["sequence_id"],
        input_hash=bytes.fromhex(payload["input_hash"]),
        prior_state_hash=bytes.fromhex(payload["prior_state_hash"]),
        output_hash=bytes.fromhex(payload["output_hash"]),
        module_id=payload["module_id"],
        success=payload["success"],
        frame_timestamp_ns=payload["frame_timestamp_ns"],
        error_message=payload["error_message"],
    )

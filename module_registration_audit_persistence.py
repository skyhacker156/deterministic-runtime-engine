"""
Module Registration Audit - Persistence Helpers
(module_registration_audit_persistence.py)

Deliberately minimal. This file answers exactly one question: does
ModuleRegistrationAttemptRecord.attempt_hash survive a serialize/
deserialize round-trip unchanged?

It does NOT attempt crash recovery, partial-write protection, envelope
versioning, or any other persistence concern. Those are all downstream
of this question and none of them are worth designing until this one
is answered. See test_registration_audit_persistence.py.

Format choice: JSON, with bytes fields (manifest_hash) hex-encoded,
since JSON has no native bytes type. This is the simplest reversible
encoding available and introduces no dependencies. If this round-trip
test reveals problems, the format is one of the first things worth
reconsidering -- but there's no reason to design past JSON until a
concrete problem with it shows up.
"""

import json

from module_registration_audit import ModuleRegistrationAttemptRecord


def record_to_json(record: ModuleRegistrationAttemptRecord) -> str:
    """
    Serializes a record to a JSON string. Every field is written
    explicitly -- no reliance on dataclasses.asdict() or __dict__,
    since attempt_hash is a derived field (computed in __post_init__)
    and must never be trusted as an input on the way back in; see
    record_from_json() below.
    """
    payload = {
        "module_id": record.module_id,
        "attempted_at_ns": record.attempted_at_ns,
        "success": record.success,
        "reason": record.reason,
        "manifest_hash": record.manifest_hash.hex() if record.manifest_hash is not None else None,
    }
    return json.dumps(payload, sort_keys=True)


def record_from_json(json_str: str) -> ModuleRegistrationAttemptRecord:
    """
    Reconstructs a record from a JSON string produced by
    record_to_json(). Deliberately does NOT read a stored attempt_hash
    from the JSON, even though nothing here writes one -- the hash is
    always recomputed by ModuleRegistrationAttemptRecord.__post_init__
    from the real fields. This is the actual property under test: if
    reconstruction here produces a DIFFERENT attempt_hash than the
    original record had, that is a real bug to find, not something to
    paper over by trusting a stored hash value instead of recomputing it.
    """
    payload = json.loads(json_str)
    manifest_hash = (
        bytes.fromhex(payload["manifest_hash"])
        if payload["manifest_hash"] is not None
        else None
    )
    return ModuleRegistrationAttemptRecord(
        module_id=payload["module_id"],
        attempted_at_ns=payload["attempted_at_ns"],
        success=payload["success"],
        reason=payload["reason"],
        manifest_hash=manifest_hash,
    )
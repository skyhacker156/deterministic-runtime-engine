"""
Decision Record - Persistence Helpers
(decision_record_persistence.py)

Same scope discipline as module_registration_audit_persistence.py:
answers exactly one question -- does DecisionRecord survive a
serialize/deserialize round-trip? -- and nothing about crash recovery,
envelopes, or versioning.

Two distinct properties are being tested here, not one, because
DecisionRecord has two different kinds of hash:

    decision_hash: OPAQUE, externally-supplied by the authorizer/policy
        layer. Per decision_record_contract.py's own docstring, this
        is "REFERENCED, never recomputed." Persistence must therefore
        preserve it byte-for-byte, unchanged -- there is no recomputation
        to fall back on if this drifts.

    record_hash: DERIVED, computed once in DecisionRecord.__post_init__
        from sequence_id, module_id, allowed, decision_hash, AND
        generation_id. Persistence correctness here means:
        reconstructing the record from disk and letting __post_init__
        recompute record_hash produces the SAME value as the original
        had. This is the same kind of check as attempt_hash in the
        registration record.

generation_id: like decision_hash, this is OPAQUE from this module's
perspective -- sourced from the kernel generation the decision belonged
to, never recomputed here. It participates in record_hash's derivation
(see decision_record_contract.py), so it must be preserved byte-for-byte
on the round-trip the same way decision_hash is, or record_hash will
legitimately fail to match on reconstruction -- not because of a bug in
the hash logic, but because a real input field was silently dropped.

These are different failure modes. A serializer could preserve
decision_hash perfectly while still producing a different record_hash
(e.g. if module_id round-tripped with different whitespace/encoding, or
if generation_id were dropped), or could corrupt decision_hash while
record_hash still happens to match by coincidence on a short fuzz run.
Both are checked independently below rather than assuming one implies
the other.
"""

import json

from decision_record_contract import DecisionRecord


def decision_record_to_json(record: DecisionRecord) -> str:
    """
    Serializes a DecisionRecord to a JSON string. record_hash is NOT
    written -- it's a derived field, and writing it would create the
    temptation to read it back on reconstruction instead of letting
    __post_init__ recompute it. See decision_record_from_json().
    """
    payload = {
        "sequence_id": record.sequence_id,
        "module_id": record.module_id,
        "allowed": record.allowed,
        "decision_hash": record.decision_hash.hex(),
        "generation_id": record.generation_id.hex(),
    }
    return json.dumps(payload, sort_keys=True)


def decision_record_from_json(json_str: str) -> DecisionRecord:
    """
    Reconstructs a DecisionRecord from JSON produced by
    decision_record_to_json(). record_hash is always recomputed by
    DecisionRecord.__post_init__ from the five real fields -- this
    function never reads or trusts a stored record_hash, because none
    is ever written. If the reconstructed record's record_hash differs
    from the original's, that's the actual property under test failing,
    not something to route around.
    """
    payload = json.loads(json_str)
    return DecisionRecord(
        sequence_id=payload["sequence_id"],
        module_id=payload["module_id"],
        allowed=payload["allowed"],
        decision_hash=bytes.fromhex(payload["decision_hash"]),
        generation_id=bytes.fromhex(payload["generation_id"]),
    )

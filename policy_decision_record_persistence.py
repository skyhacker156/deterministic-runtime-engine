"""
Policy Decision Record - Persistence Helpers
(policy_decision_record_persistence.py)

Same narrow question as the other three persistence modules: does this
record survive a serialize/deserialize round-trip with every hash
intact? No envelope, no crash recovery, no versioning.

FIRST CASE IN THIS CODEBASE of one persisted record embedding another.
PolicyDecisionRecord.policy_decision is a full ExecutionPolicyDecision,
not a hash reference to one -- see policy_decision_record_contract.py's
docstring for why (provenance: a verifier needs the real fields to
recompute decision_hash independently, not just observe it's present).

DESIGN CHOICE: policy_decision is nested as a genuine JSON object in
the payload, not serialized to a string and embedded as an escaped
blob. This keeps the persisted file human-inspectable (a reader can
see the embedded decision's fields directly, not a JSON string sitting
inside JSON) and lets this module reuse
execution_policy_decision_persistence.py's already-proven
policy_decision_to_json/policy_decision_from_json UNCHANGED, rather
than duplicating ExecutionPolicyDecision's field list a second time
here. The cost is one extra json.loads/json.dumps hop on each side to
adapt between "nested dict" and "JSON string", visible below -- kept
deliberately rather than changing policy_decision_from_json's own
signature to accept a pre-parsed dict, so every *_from_json function
in this codebase keeps the same "takes a JSON string" contract.

TWO INDEPENDENT LAYERS OF HASH RECOMPUTATION on reconstruction, not
one: policy_decision_from_json() re-derives decision_hash from
ExecutionPolicyDecision's own real fields first; PolicyDecisionRecord's
own __post_init__ then re-derives entry_hash from THAT freshly-rederived
decision_hash (among sequence_id and generation_id). If either hash
was tampered with in isolation, reconstruction surfaces it -- see
policy_decision_persistence's docstring and this module's tampering
tests for the two failure modes this is meant to catch independently.
"""

import json

from policy_decision_record_contract import PolicyDecisionRecord
from execution_policy_decision_persistence import (
    policy_decision_to_json,
    policy_decision_from_json,
)


def policy_decision_record_to_json(record: PolicyDecisionRecord) -> str:
    """
    Serializes a PolicyDecisionRecord to a JSON string. entry_hash is
    NOT written -- it's derived, and __post_init__ always recomputes it
    on reconstruction. See policy_decision_record_from_json().

    The embedded ExecutionPolicyDecision is serialized via
    policy_decision_to_json() and re-parsed back into a dict so it nests
    as a genuine JSON object under "policy_decision", not as an escaped
    string.
    """
    payload = {
        "sequence_id": record.sequence_id,
        "generation_id": record.generation_id.hex(),
        "policy_decision": json.loads(policy_decision_to_json(record.policy_decision)),
    }
    return json.dumps(payload, sort_keys=True)


def policy_decision_record_from_json(json_str: str) -> PolicyDecisionRecord:
    """
    Reconstructs a PolicyDecisionRecord from JSON produced by
    policy_decision_record_to_json(). entry_hash is always recomputed
    by __post_init__ from the real fields -- this function never reads
    or trusts a stored entry_hash, because none is ever written.

    Reconstruction happens in two hops, deliberately not collapsed into
    one: the embedded ExecutionPolicyDecision is rebuilt first (its own
    decision_hash is re-derived by policy_decision_from_json(), not
    trusted from storage), and only then does PolicyDecisionRecord wrap
    it and re-derive entry_hash from that freshly-rederived
    decision_hash. If either the inner or outer record's fields differ
    from what was originally serialized, the corresponding hash will
    differ on reconstruction -- that is the actual property under test,
    not something either hop has a path to fake.
    """
    payload = json.loads(json_str)
    policy_decision = policy_decision_from_json(
        json.dumps(payload["policy_decision"])
    )
    return PolicyDecisionRecord(
        sequence_id=payload["sequence_id"],
        generation_id=bytes.fromhex(payload["generation_id"]),
        policy_decision=policy_decision,
    )

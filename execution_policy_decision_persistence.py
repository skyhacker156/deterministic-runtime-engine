"""
Execution Policy Decision - Persistence Helpers
(execution_policy_decision_persistence.py)

Fourth and last of the record types answering the same narrow
question the other three persistence modules answer: does this
record survive a serialize/deserialize round-trip with every hash
intact? No envelope, no crash recovery, no versioning -- same scope
discipline as decision_record_persistence.py and
execution_audit_persistence.py.

ExecutionPolicyDecision has the widest field surface of any of the
four record types: two independent opaque hash fields (policy_hash,
capability_snapshot_hash -- both references to hashes computed
elsewhere, ExecutionPolicy.policy_hash and
ModuleCapabilities.capability_hash respectively, never recomputed
here) plus one derived hash (decision_hash, computed once in
__post_init__ from module_id, allowed, reason,
observed_lifecycle_state.name, policy_hash, and
capability_snapshot_hash -- see execution_authorizer.py's own
_compute_decision_hash()).

observed_lifecycle_state is a ModuleState enum, not a primitive --
serialized as its .name string and reconstructed via ModuleState[name].
This is the only field of this shape across all four record types.

IMPORTANT, load-bearing for Gap 2 closure: observed_invocation_count
IS persisted here (round-trips like any other field), but is
deliberately NOT part of decision_hash's computation. This module does
not change that -- it only makes the field itself survive the round
trip so it's at least inspectable on disk. Concretely: two
ExecutionPolicyDecision instances made at genuinely different points
in an execution history, with different observed_invocation_count
values but identical module_id/allowed/reason/lifecycle/policy/
capability values, WILL produce identical decision_hash. Any future
verifier check that tries to prove "this DecisionRecord.decision_hash
traces to a real ExecutionPolicyDecision" by looking up a matching
decision_hash alone is therefore unsound -- it can match the wrong
historical decision and still report success. See
PHOENIX_VERIFICATION_STATE.md Gap 1b/Gap 2 for the full finding;
closing Gap 2 for real requires a positional join key (analogous to
DecisionRecord.sequence_id), not just this persistence layer, before
any hash-based provenance check is wired up.
"""

import json

from execution_authorizer import ExecutionPolicyDecision
from module_lifecycle import ModuleState


def policy_decision_to_json(decision: ExecutionPolicyDecision) -> str:
    """
    Serializes an ExecutionPolicyDecision to a JSON string. decision_hash
    is NOT written -- it's derived, and __post_init__ always recomputes
    it on reconstruction. See policy_decision_from_json().
    """
    payload = {
        "module_id": decision.module_id,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "observed_lifecycle_state": decision.observed_lifecycle_state.name,
        "policy_hash": decision.policy_hash.hex(),
        "capability_snapshot_hash": decision.capability_snapshot_hash.hex(),
        "observed_invocation_count": decision.observed_invocation_count,
        "max_allowed_invocations": decision.max_allowed_invocations,
    }
    return json.dumps(payload, sort_keys=True)


def policy_decision_from_json(json_str: str) -> ExecutionPolicyDecision:
    """
    Reconstructs an ExecutionPolicyDecision from JSON produced by
    policy_decision_to_json(). decision_hash is always recomputed by
    __post_init__ from the real fields -- never read from storage. If
    the reconstructed record's decision_hash differs from the
    original's, that's the actual property under test failing, not
    something to route around.
    """
    payload = json.loads(json_str)
    return ExecutionPolicyDecision(
        module_id=payload["module_id"],
        allowed=payload["allowed"],
        reason=payload["reason"],
        observed_lifecycle_state=ModuleState[payload["observed_lifecycle_state"]],
        policy_hash=bytes.fromhex(payload["policy_hash"]),
        capability_snapshot_hash=bytes.fromhex(payload["capability_snapshot_hash"]),
        observed_invocation_count=payload["observed_invocation_count"],
        max_allowed_invocations=payload["max_allowed_invocations"],
    )

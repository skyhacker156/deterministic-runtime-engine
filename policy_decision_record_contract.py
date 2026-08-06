"""
Policy Decision Record Contract - Sentinel Framework
(policy_decision_record_contract.py)

Closes Gap 2 (see PHOENIX_VERIFICATION_STATE.md): what was previously
unprovable was not "does a decision_hash exist" (DecisionRecord already
proves that trivially) but "does this decision_hash trace to a real
ExecutionPolicyDecision, and is it THE one that belongs to this specific
execution attempt, not merely one that happens to share its hash."

Two problems, two different fixes, composed here rather than solved by
a single field:

1. PROVENANCE: ExecutionPolicyDecision was never persisted at all --
   only its decision_hash reached disk, via DecisionRecord. This module
   embeds the full ExecutionPolicyDecision object (module_id, allowed,
   reason, observed_lifecycle_state, policy_hash,
   capability_snapshot_hash, observed_invocation_count,
   max_allowed_invocations), so a verifier can independently recompute
   decision_hash from real persisted fields and confirm it matches --
   not just observe that a hash is present and well-formed.

2. CORRELATION: decision_hash alone is NOT a safe join key across time.
   ExecutionPolicyDecision._compute_decision_hash() deliberately
   excludes observed_invocation_count (see execution_authorizer.py) --
   two decisions made at genuinely different points in an execution
   history, differing only in invocation count, produce IDENTICAL
   decision_hash. A verifier joining purely on decision_hash could
   silently match the wrong historical decision to a given
   DecisionRecord and still report success. sequence_id here is the
   fix -- the same positional join key DecisionRecord and
   ExecutionAuditRecord already use for exactly this reason.

DESIGN CONSTRAINT, stated explicitly so it isn't quietly violated
later: one identity primitive per concept, already established across
this schema --
    execution ordering  -> sequence_id (frame.seq_id)
    generation identity  -> generation_id
    content identity     -> hashes (opaque references or derived)
This module introduces NO new identity primitive. It reuses
sequence_id and generation_id exactly as DecisionRecord and
ExecutionAuditRecord already do, for the same frame. Do not add an
event_id, record_id, or any other correlation field to this or any
future record type without a demonstrated need those three don't
already cover.

WHY A WRAPPER, NOT NEW FIELDS ON ExecutionPolicyDecision ITSELF:
ExecutionPolicyDecision lives in execution_policy_decision_contract.py
(moved there 2026-08-06, out of execution_authorizer.py -- see that
module's own docstring for why: a pure verifier needing
ExecutionPolicyDecision was transitively importing the entire
authorizer/registry/policy stack) and is deliberately kept free of any
dependency on kernel state or execution ordering -- see
decision_record_contract.py's own docstring for the identical
reasoning already applied to keeping generation_id off
ExecutionPolicyDecision/decision_hash. Adding sequence_id there would
mean authorize() takes a sequence_id parameter, making policy
evaluation aware of frame ordering -- a real architectural coupling,
not just an extra field. The wrapper keeps ExecutionPolicyDecision
exactly as it is; only this record, constructed by the engine (which
already has sequence_id, generation_id, and the decision in scope at
once, at the same call site DecisionRecord is already constructed),
adds the correlation context.

Normative rule, matching DecisionRecord's treatment of decision_hash:
entry_hash is computed from sequence_id, generation_id, and
policy_decision.decision_hash -- decision_hash is REFERENCED, never
recomputed here. This module never re-derives what
ExecutionPolicyDecision.decision_hash already means; it only adds the
positional and generational context needed to correlate it safely.
"""
import hashlib
import struct
from dataclasses import dataclass, field

from execution_policy_decision_contract import ExecutionPolicyDecision


class PolicyDecisionRecordValidationError(Exception):
    """Raised when a PolicyDecisionRecord is constructed with invalid values."""
    pass


@dataclass(frozen=True)
class PolicyDecisionRecord:
    """
    Immutable, engine-constructed wrapper correlating one
    ExecutionPolicyDecision with the specific execution attempt it
    belongs to.

    sequence_id: matches CoreExecutionFrame.seq_id for this attempt --
    same join key DecisionRecord.sequence_id and
    ExecutionAuditRecord.sequence_id already use.

    generation_id: sourced from the same KernelStateEnvelope
    (prior_envelope) the engine already captures before authorizing
    each frame -- same source, same value, as the corresponding
    DecisionRecord.generation_id and ExecutionAuditRecord.generation_id
    for this sequence_id.

    policy_decision: the full, real ExecutionPolicyDecision object,
    embedded rather than referenced by hash alone -- this is what makes
    provenance checkable. entry_hash is computed from
    policy_decision.decision_hash (opaque reference), not from
    policy_decision's own underlying fields directly.
    """
    sequence_id: int
    generation_id: bytes
    policy_decision: ExecutionPolicyDecision
    entry_hash: bytes = field(init=False)

    # Format version for entry_hash's packed bytes. First version for
    # this record type -- no prior format to migrate from.
    ENTRY_HASH_FORMAT_VERSION = 1

    def __post_init__(self) -> None:
        # NOTE: sequence_id validation below is NOT present on
        # DecisionRecord or ExecutionAuditRecord, both of which accept
        # any int unchecked. Added here deliberately, at test-writing
        # time, because a positional join key existing purely to prove
        # correlation is meaningless if it can be negative/nonsensical.
        # This makes PolicyDecisionRecord stricter than its two siblings
        # -- flagged as an open question (retrofit the other two, or
        # accept the inconsistency) rather than silently introduced.
        if not isinstance(self.sequence_id, int) or self.sequence_id < 0:
            raise PolicyDecisionRecordValidationError(
                "sequence_id must be a non-negative integer"
            )
        if not isinstance(self.generation_id, bytes) or len(self.generation_id) != 16:
            raise PolicyDecisionRecordValidationError(
                "generation_id must be a 16-byte UUID"
            )
        if not isinstance(self.policy_decision, ExecutionPolicyDecision):
            raise PolicyDecisionRecordValidationError(
                "policy_decision must be a real ExecutionPolicyDecision instance, "
                "not a dict or other stand-in -- entry_hash's correctness depends "
                "on decision_hash having been genuinely derived by "
                "ExecutionPolicyDecision.__post_init__, not fabricated."
            )
        object.__setattr__(self, "entry_hash", self._compute_entry_hash())

    def _compute_entry_hash(self) -> bytes:
        hasher = hashlib.sha256()
        hasher.update(struct.pack(">B", self.ENTRY_HASH_FORMAT_VERSION))
        hasher.update(struct.pack(">q", self.sequence_id))
        hasher.update(self.generation_id)
        hasher.update(self.policy_decision.decision_hash)
        return hasher.digest()

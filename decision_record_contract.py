"""
Decision Record Contract - Sentinel Framework
(decision_record_contract.py)
Represents an authorization decision as OBSERVED by the engine during a
real execution attempt. Distinct domain object from ExecutionAuditRecord
("execution occurred") — DecisionRecord answers "authorization was
observed." Deliberately independent schema, not a copy of
ExecutionAuditRecord's fields with names swapped.
Normative rule: DecisionRecord references ExecutionPolicyDecision.decision_hash.
It never recomputes, duplicates, or reinterprets authorization reasoning.

v2 (generation_id): DecisionRecord gains generation_id, sourced from
the same KernelStateEnvelope the engine captures as prior_envelope
before authorizing/dispatching each frame -- the engine already has
this value at construction time, same source as
ExecutionAuditRecord.generation_id for the same frame. This closes
the decision-level half of Gap 1b. ExecutionPolicyDecision and
decision_hash are UNCHANGED -- threading generation_id there would
require giving the authorizer a new dependency on kernel state, a
materially larger change than adding a field here, which the engine
already constructs with direct access to both values. See
GENERATION_ID_MIGRATION_NOTE.md for the full migration philosophy.

record_hash's format version bumps 1 -> 2 in this change (it already
had an explicit version byte, unlike ExecutionAuditRecord and
KernelStateEnvelope, which gain their first version byte in this same
pass).
"""
import hashlib
import struct
from dataclasses import dataclass, field
class DecisionRecordValidationError(Exception):
    """Raised when a DecisionRecord is constructed with invalid values."""
    pass
@dataclass(frozen=True)
class DecisionRecord:
    """
    Immutable, engine-observed record of one authorization decision.
    sequence_id ties this record to the specific execution attempt it
    belongs to (matching CoreExecutionFrame.seq_id), giving Invariant B
    a concrete join key.
    record_hash is computed from this object's own fields — decision_hash
    is REFERENCED, never recomputed.

    generation_id: sourced from the same KernelStateEnvelope as the
    corresponding ExecutionAuditRecord for this sequence_id (NEW in v2).
    Included in record_hash, not in decision_hash (decision_hash remains
    the authorizer's opaque, unmodified reference).
    """
    sequence_id: int
    module_id: str
    allowed: bool
    decision_hash: bytes
    generation_id: bytes
    record_hash: bytes = field(init=False)

    # Format version for record_hash's packed bytes. Bumped 1 -> 2 in
    # this change (generation_id added to what's hashed).
    RECORD_HASH_FORMAT_VERSION = 2

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or not self.module_id.strip():
            raise DecisionRecordValidationError("module_id must be a non-empty string")
        if not isinstance(self.decision_hash, bytes) or len(self.decision_hash) != 32:
            raise DecisionRecordValidationError("decision_hash must be a 32-byte digest")
        if not isinstance(self.generation_id, bytes) or len(self.generation_id) != 16:
            raise DecisionRecordValidationError("generation_id must be a 16-byte UUID")
        object.__setattr__(self, "record_hash", self._compute_record_hash())

    def _compute_record_hash(self) -> bytes:
        hasher = hashlib.sha256()
        hasher.update(struct.pack(">B", self.RECORD_HASH_FORMAT_VERSION))
        hasher.update(struct.pack(">q", self.sequence_id))
        hasher.update(self.module_id.encode("utf-8"))
        hasher.update(b"\x01" if self.allowed else b"\x00")
        hasher.update(self.decision_hash)
        hasher.update(self.generation_id)
        return hasher.digest()

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
    """
    sequence_id: int
    module_id: str
    allowed: bool
    decision_hash: bytes

    record_hash: bytes = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or not self.module_id.strip():
            raise DecisionRecordValidationError("module_id must be a non-empty string")
        if not isinstance(self.decision_hash, bytes) or len(self.decision_hash) != 32:
            raise DecisionRecordValidationError("decision_hash must be a 32-byte digest")

        object.__setattr__(self, "record_hash", self._compute_record_hash())

    def _compute_record_hash(self) -> bytes:
        hasher = hashlib.sha256()
        hasher.update(struct.pack(">B", 1))
        hasher.update(struct.pack(">q", self.sequence_id))
        hasher.update(self.module_id.encode("utf-8"))
        hasher.update(b"\x01" if self.allowed else b"\x00")
        hasher.update(self.decision_hash)
        return hasher.digest()

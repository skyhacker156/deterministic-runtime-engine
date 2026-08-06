"""
Execution Audit Contract - Sentinel Framework
(execution_audit_contract.py)

Defines an immutable, observational record of a single frame's passage through
the execution engine. The audit layer records facts already computed elsewhere
(frame provenance, prior state, module output) — it never recomputes, reinterprets,
or introduces new judgment. It observes; it does not control.

v2 (generation_id): ExecutionAuditRecord gains generation_id, sourced
directly from the KernelStateEnvelope the engine already captures as
prior_envelope before dispatching each frame -- no new coupling, the
engine already has this value at construction time. This closes the
audit-level half of Gap 1b: two audit records with identical
sequence_id, module_id, and content hashes, occurring in different
kernel generations, now produce different audit_hash values. See
GENERATION_ID_MIGRATION_NOTE.md for the full migration philosophy.

audit_hash's computation also gains an explicit format-version byte
for the first time (previously unversioned) -- normalized in the same
pass as generation_id.

DETERMINISM CONTRACT:
----------------------
Given identical (sequence_id, input_hash, prior_state_hash, module_id, success,
output_hash, frame_timestamp_ns, generation_id), audit_hash is always identical.

Wall-clock values (creation time, latency) are explicitly excluded from the
audit_hash computation and, if present at all, live in a separately-named,
clearly-non-hashed field. This mirrors the fix already applied to
ExecutionResult.module_hash, which previously broke determinism by hashing
execution_latency_us.
"""

from dataclasses import dataclass, field
from typing import Optional
import hashlib
import struct


@dataclass(frozen=True)
class ExecutionAuditRecord:
    """
    Immutable observational record of one frame's execution.

    All hash fields are references to hashes already computed by upstream
    components (CoreExecutionFrame.provenance_hash, KernelStateEnvelope.state_hash,
    ExecutionResult.module_hash) — this record does not recompute them.

    generation_id: sourced directly from KernelStateEnvelope.generation_id
    (the prior_envelope the engine captures before dispatching this
    frame) — not independently derived. Included in audit_hash.
    """
    sequence_id: int
    input_hash: bytes            # CoreExecutionFrame.provenance_hash
    prior_state_hash: bytes      # KernelStateEnvelope.state_hash, captured before execution
    output_hash: bytes           # ExecutionResult.module_hash
    module_id: str
    success: bool                # sourced directly from ExecutionResult.success
    frame_timestamp_ns: int      # CoreExecutionFrame.timestamp_ns — data, not wall-clock
    generation_id: bytes         # KernelStateEnvelope.generation_id at capture time -- NEW in v2
    error_message: Optional[str] = None  # sourced directly from ExecutionResult.error_message

    audit_hash: bytes = field(init=False)

    # Format version for audit_hash's packed bytes. First explicit
    # version for this hash -- previously unversioned.
    AUDIT_HASH_FORMAT_VERSION = 1

    def __post_init__(self) -> None:
        # Structural validation: all hash fields must be well-formed 32-byte SHA-256 digests.
        for name, value in (
            ("input_hash", self.input_hash),
            ("prior_state_hash", self.prior_state_hash),
            ("output_hash", self.output_hash),
        ):
            if not isinstance(value, bytes) or len(value) != 32:
                raise ValueError(f"{name} must be a 32-byte SHA-256 digest, got {value!r}")

        if not isinstance(self.generation_id, bytes) or len(self.generation_id) != 16:
            raise ValueError(
                f"generation_id must be a 16-byte UUID, got {self.generation_id!r}"
            )

        if not isinstance(self.module_id, str) or not self.module_id:
            raise ValueError("module_id must be a non-empty string")

        # Mirror ExecutionResult's success/error_message consistency rule.
        if not self.success:
            if not self.error_message or not self.error_message.strip():
                raise ValueError("error_message must be provided when success is False")
        else:
            if self.error_message is not None:
                raise ValueError("error_message must be None when success is True")

        object.__setattr__(self, "audit_hash", self._compute_audit_hash())

    def _compute_audit_hash(self) -> bytes:
        """
        Deterministic fingerprint of this audit record.

        Uses fixed-width binary packing for numeric fields (matching the
        approach already used in CoreExecutionFrame and KernelStateEnvelope)
        rather than string formatting, to avoid the class of hash-mismatch
        bugs that arose earlier from inconsistent string-vs-binary encoding
        across different modules.

        Packs an explicit format_version byte first (NEW in v2), followed
        by the existing fields, followed by generation_id (NEW in v2).
        """
        hasher = hashlib.sha256()
        hasher.update(struct.pack(">B", self.AUDIT_HASH_FORMAT_VERSION))
        hasher.update(struct.pack(">q", self.sequence_id))
        hasher.update(self.input_hash)
        hasher.update(self.prior_state_hash)
        hasher.update(self.output_hash)
        hasher.update(self.module_id.encode("utf-8"))
        hasher.update(b"\x01" if self.success else b"\x00")
        hasher.update(struct.pack(">Q", self.frame_timestamp_ns))
        hasher.update(self.generation_id)
        if self.error_message:
            hasher.update(self.error_message.encode("utf-8"))
        return hasher.digest()

    @classmethod
    def from_execution(
        cls,
        sequence_id: int,
        input_hash: bytes,
        prior_state_hash: bytes,
        frame_timestamp_ns: int,
        module_id: str,
        result,  # ExecutionResult — typed loosely here to avoid a hard import cycle
        generation_id: bytes,
    ) -> "ExecutionAuditRecord":
        """
        Convenience constructor that pulls success/output_hash/error_message
        directly off an ExecutionResult, so the audit layer never restates
        those facts independently.

        generation_id is now a required parameter (NEW in v2) -- callers
        must pass KernelStateEnvelope.generation_id from the same
        prior_envelope that supplied prior_state_hash, since both values
        describe the same kernel snapshot.
        """
        return cls(
            sequence_id=sequence_id,
            input_hash=input_hash,
            prior_state_hash=prior_state_hash,
            output_hash=result.module_hash,
            module_id=module_id,
            success=result.success,
            frame_timestamp_ns=frame_timestamp_ns,
            generation_id=generation_id,
            error_message=result.error_message,
        )

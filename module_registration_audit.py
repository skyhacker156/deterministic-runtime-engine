"""
Module Registration Attempt Audit - Sentinel Framework
(module_registration_audit.py)

Purpose: capture the outcome of every ExecutionModuleRegistry.register()
attempt -- success or failure -- as a first-class, hashable record,
WITHOUT conflating this with ExecutionAuditRecord (which is scoped to
frame execution and requires fields -- sequence_id, input_hash,
prior_state_hash, output_hash -- that have no real referent at
registration time).

Design mirrors ExecutionAuditRecord's validation pattern:
    success=True  -> reason must be None
    success=False -> reason must be a non-empty string

This is deliberate symmetry, not copy-paste: a registration failure and
a frame execution failure are structurally the same kind of event
("an attempt was made; here is what happened and why"), so the
success/reason mutual-exclusivity contract is reused on purpose.
Everything else about ExecutionAuditRecord (frame hashes, sequence
chaining) is dropped because it does not apply here.

Nothing in this file is a stub. Every field either has a real value at
call time or the record construction rejects it.
"""

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Optional


class ModuleRegistrationAttemptError(ValueError):
    """Raised when constructing a ModuleRegistrationAttemptRecord with
    an internally inconsistent set of fields (e.g. success=True with a
    reason attached, or success=False with no reason)."""
    pass


@dataclass(frozen=True)
class ModuleRegistrationAttemptRecord:
    """
    One immutable record of a single register() attempt against
    ExecutionModuleRegistry, whether it succeeded or failed.

    Fields:
        module_id:        the module_id the attempt was made under.
        attempted_at_ns:   wall-clock timestamp of the attempt, in
                            nanoseconds (time.time_ns()).
        success:           whether this attempt resulted in a committed
                            registration.
        reason:            required and non-empty when success=False
                            (the exception message that caused the
                            rejection). Must be None when success=True.
        manifest_hash:     optional 32-byte SHA-256 digest identifying
                            the manifest that was attempted, if the
                            caller chooses to supply one. None is a
                            valid value -- not every caller will have
                            a manifest hash on hand, and this field
                            existing or not does not change the
                            validity of the record.

    attempt_hash is computed once, here, from the fields above, and is
    never recomputed or overridden downstream -- consistent with the
    "hash computed once by its owning object" invariant used elsewhere
    in Sentinel (ExecutionAuditRecord, ExecutionPolicy, etc).
    """

    module_id: str
    attempted_at_ns: int
    success: bool
    reason: Optional[str] = None
    manifest_hash: Optional[bytes] = None

    attempt_hash: bytes = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or self.module_id.strip() == "":
            raise ModuleRegistrationAttemptError(
                "module_id must be a non-empty string."
            )

        if not isinstance(self.attempted_at_ns, int) or self.attempted_at_ns < 0:
            raise ModuleRegistrationAttemptError(
                "attempted_at_ns must be a non-negative integer (nanoseconds)."
            )

        if not isinstance(self.success, bool):
            raise ModuleRegistrationAttemptError(
                "success must be a bool."
            )

        if self.success:
            if self.reason is not None:
                raise ModuleRegistrationAttemptError(
                    "reason must be None when success=True."
                )
        else:
            if not isinstance(self.reason, str) or self.reason.strip() == "":
                raise ModuleRegistrationAttemptError(
                    "reason must be provided (non-empty string) when success=False."
                )

        if self.manifest_hash is not None:
            if not isinstance(self.manifest_hash, bytes) or len(self.manifest_hash) != 32:
                raise ModuleRegistrationAttemptError(
                    "manifest_hash must be a 32-byte SHA-256 digest when provided."
                )

        object.__setattr__(self, "attempt_hash", self._compute_hash())

    def _compute_hash(self) -> bytes:
        """
        Deterministic hash over every real field. Optional-but-absent
        fields (reason=None, manifest_hash=None) are hashed as an
        explicit sentinel byte rather than skipped, so that
        (reason=None) and (reason="") can never collide, and so that
        a record with a manifest_hash can never collide with an
        otherwise-identical record without one.
        """
        h = hashlib.sha256()
        h.update(struct.pack(">B", 1))  # format version
        h.update(self.module_id.encode("utf-8"))
        h.update(struct.pack(">Q", self.attempted_at_ns))
        h.update(struct.pack(">B", int(self.success)))

        if self.reason is not None:
            h.update(b"\x01")
            h.update(self.reason.encode("utf-8"))
        else:
            h.update(b"\x00")

        if self.manifest_hash is not None:
            h.update(b"\x01")
            h.update(self.manifest_hash)
        else:
            h.update(b"\x00")

        return h.digest()
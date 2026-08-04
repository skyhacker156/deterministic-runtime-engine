"""
Execution Policy - Sentinel Framework
(execution_policy.py)

Step 1 of the execution authorization layer: defines ExecutionPolicy as an
immutable, deterministically-hashable ruleset. Deliberately contains no
mutable state and no authorization logic — those are ExecutionPolicyState
(Step 2) and ExecutionAuthorizer (Step 3), kept as separate objects per
the same configuration/state separation already used throughout this
codebase (e.g. KernelStateMachine's fixed transition table vs. its mutable
per-instance state).

policy_hash is owned by ExecutionPolicy itself, computed from its own
canonical byte representation — matching ExecutionResult.module_hash and
ExecutionAuditRecord.audit_hash, both of which are computed by the object
they describe, never by a downstream consumer. Anything referencing a
policy's hash later (e.g. ExecutionPolicyDecision) reads policy.policy_hash;
nothing recomputes it independently.
"""

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Optional


class PolicyValidationError(Exception):
    """Raised when an ExecutionPolicy is constructed with invalid rule values."""
    pass


@dataclass(frozen=True)
class ExecutionPolicy:
    """
    Immutable ruleset. All fields are policy RULES, never runtime counters
    or telemetry — those live in ExecutionPolicyState, kept as a separate
    object.

    max_invocations_per_module_lifetime: if set, the maximum number of
    times a single module_id may be authorized to execute across the
    entire lifetime of one ExecutionPolicyState instance. None means
    unlimited.
    """
    max_invocations_per_module_lifetime: Optional[int] = None

    policy_hash: bytes = field(init=False)

    def __post_init__(self) -> None:
        if self.max_invocations_per_module_lifetime is not None:
            if not isinstance(self.max_invocations_per_module_lifetime, int):
                raise PolicyValidationError(
                    "max_invocations_per_module_lifetime must be an int or None."
                )
            if self.max_invocations_per_module_lifetime < 0:
                raise PolicyValidationError(
                    "max_invocations_per_module_lifetime must be non-negative."
                )

        object.__setattr__(self, "policy_hash", self._compute_hash())

    def canonical_bytes(self) -> bytes:
        """
        Deterministic, explicit-format byte serialization of this policy's
        rules. Uses fixed-width binary packing (matching CoreExecutionFrame,
        KernelStateEnvelope, and ExecutionAuditRecord's approach) rather
        than str()/repr(), which are not guaranteed stable serialization
        formats across Python versions or field additions.

        A sentinel value (0xFFFFFFFFFFFFFFFF, the max uint64) is used to
        represent "unset" (None) so that unset-vs-zero is unambiguous in
        the byte stream — 0 and None must hash differently, since they are
        different rules ("never allowed" vs "unlimited").
        """
        UNSET_SENTINEL = 0xFFFFFFFFFFFFFFFF

        max_invocations = (
            UNSET_SENTINEL
            if self.max_invocations_per_module_lifetime is None
            else self.max_invocations_per_module_lifetime
        )

        # Explicit format version byte first, so future field additions to
        # this policy can change the packed format without ambiguity about
        # which format produced a given hash.
        return struct.pack(">BQ", 1, max_invocations)

    def _compute_hash(self) -> bytes:
        return hashlib.sha256(self.canonical_bytes()).digest()
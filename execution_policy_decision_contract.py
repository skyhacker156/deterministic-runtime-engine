"""
Execution Policy Decision Contract - Sentinel Framework
(execution_policy_decision_contract.py)

Extracted from execution_authorizer.py (2026-08-06) -- see
test_verifier_runtime_isolation.py, which caught the original problem:
causal_history_verifier.py needed ExecutionPolicyDecision (to
reconstruct PolicyDecisionRecord for Check 4), but that class lived
inside execution_authorizer.py alongside ExecutionAuthorizer, which
unconditionally imports execution_module_registry, module_lifecycle,
execution_policy, and execution_policy_state at module load time.
Importing ExecutionPolicyDecision from that file therefore transitively
imported all of those into a supposedly disk-only, pure verifier's
process -- exactly the property test_verifier_runtime_isolation.py
exists to catch, and did.

This module contains ONLY what ExecutionPolicyDecision itself needs:
hashlib, struct, dataclasses, and (still, as of this extraction)
module_lifecycle.ModuleState, since observed_lifecycle_state's real
type is that enum -- see this module's own remaining KNOWN GAP note
below. Everything else that used to sit alongside this class in
execution_authorizer.py (ExecutionModuleRegistry, ModuleCapabilities,
ExecutionPolicy, ExecutionPolicyState types, used only by
ExecutionAuthorizer, never by ExecutionPolicyDecision itself) is gone
from this file's import list entirely.

execution_authorizer.py now imports ExecutionPolicyDecision and
DecisionValidationError FROM this module rather than defining them --
ExecutionAuthorizer's behavior is completely unchanged; only the
location of its dependency moved. RecordExecutionError stays in
execution_authorizer.py, since it describes a failure of
ExecutionAuthorizer.record_execution() specifically, not of
ExecutionPolicyDecision's own construction.

===========================================================================
KNOWN GAP -- module_lifecycle.ModuleState, RESOLVED 2026-08-06
===========================================================================
ORIGINAL TEXT, preserved: this extraction removes execution_authorizer,
execution_module_registry, execution_policy, and execution_policy_state
from the import chain a pure verifier pulls in when it needs
ExecutionPolicyDecision. It does NOT remove module_lifecycle:
observed_lifecycle_state's field type is the real ModuleState enum, and
decision_hash's computation depends on observed_lifecycle_state.name
(see _compute_decision_hash() below), so faithful reconstruction
requires the real enum, not a stand-in -- building a parallel
lightweight reconstruction here would violate this project's own
"never reimplement a hash, always recompute via the real class"
principle (see cold_boot_reconstruction.py's own SHALL 5 enforcement
for the established precedent).

module_lifecycle is on test_verifier_runtime_isolation.py's
FORBIDDEN_MODULES list. Whether ModuleState (the enum) can be cleanly
separated from ModuleLifecycleManager (the live orchestration class
module_lifecycle.py also contains) into its own dependency-free module
was not known at the time this note was first written -- that depended
on module_lifecycle.py's actual structure.

RESOLUTION: on inspection, module_lifecycle.py had ZERO transitive
imports of its own beyond Python's stdlib -- the forbidden-module
categorization was never about heaviness, only about
ModuleLifecycleManager (genuinely live, mutable state) sharing a file
with ModuleState (genuinely pure data). Exact same shape as this
module's own extraction from execution_authorizer.py. ModuleState is
now defined in module_state.py, a new, dependency-free module containing
only the enum. This module imports ModuleState from there directly,
bypassing module_lifecycle.py (and therefore ModuleLifecycleManager)
entirely. module_lifecycle.py still re-exports ModuleState via its own
import, so every OTHER existing `from module_lifecycle import
ModuleState` call site continues to work unchanged.
===========================================================================
"""

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Optional

from module_state import ModuleState


class DecisionValidationError(Exception):
    """Raised when an ExecutionPolicyDecision is constructed with invalid values."""
    pass


@dataclass(frozen=True)
class ExecutionPolicyDecision:
    module_id: str
    allowed: bool
    reason: str
    observed_lifecycle_state: ModuleState
    policy_hash: bytes
    capability_snapshot_hash: bytes
    observed_invocation_count: int
    max_allowed_invocations: Optional[int]

    decision_hash: bytes = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or not self.module_id.strip():
            raise DecisionValidationError("module_id must be a non-empty string")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise DecisionValidationError("reason must be a non-empty string")
        if not isinstance(self.policy_hash, bytes) or len(self.policy_hash) != 32:
            raise DecisionValidationError("policy_hash must be a 32-byte digest")
        if not isinstance(self.capability_snapshot_hash, bytes) or len(self.capability_snapshot_hash) != 32:
            raise DecisionValidationError("capability_snapshot_hash must be a 32-byte digest")

        object.__setattr__(self, "decision_hash", self._compute_decision_hash())

    def _compute_decision_hash(self) -> bytes:
        hasher = hashlib.sha256()
        hasher.update(struct.pack(">B", 1))
        hasher.update(self.module_id.encode("utf-8"))
        hasher.update(b"\x01" if self.allowed else b"\x00")
        hasher.update(self.reason.encode("utf-8"))
        hasher.update(self.observed_lifecycle_state.name.encode("utf-8"))
        hasher.update(self.policy_hash)
        hasher.update(self.capability_snapshot_hash)
        return hasher.digest()

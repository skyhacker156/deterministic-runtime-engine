"""
Execution Authorizer - Sentinel Framework
(execution_authorizer.py)

v2.2 correction: authorize() no longer increments ExecutionPolicyState.
Authorization is a permission check, not an execution event — incrementing
inside authorize() would let a caller burn invocation budget on a decision
they never acted on. The caller must call record_execution() explicitly,
and only after the module actually ran, mirroring how ExecutionAuditRecord
is only emitted for frames that reach real dispatch, never for a frame
that was merely considered.

    Execution Request
            |
            v
        Authorizer.authorize()
            |
    +---- denied ----+---- allowed ----+
    |                                  |
    v                                  v
 (caller stops)                  Execute Module
                                       |
                                       v
                          Authorizer.record_execution()
                                       |
                                       v
                              Produce Audit Record
"""

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Optional

from execution_module_registry import ExecutionModuleRegistry, ModuleCapabilities
from module_lifecycle import ModuleState
from execution_policy import ExecutionPolicy
from execution_policy_state import ExecutionPolicyState


class DecisionValidationError(Exception):
    """Raised when an ExecutionPolicyDecision is constructed with invalid values."""
    pass


class RecordExecutionError(Exception):
    """Raised when record_execution() is called in a way that violates
    the authorize-then-record contract."""
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


class ExecutionAuthorizer:
    """
    authorize() is read-only with respect to ExecutionPolicyState: it
    observes the current count, evaluates the policy, and returns a
    Decision. It does not mutate state.

    record_execution() is the only method that increments the counter,
    and must be called by the caller only after the module has actually
    executed following an allowed=True decision.
    """

    def __init__(
        self,
        registry: ExecutionModuleRegistry,
        policy: ExecutionPolicy,
        state: ExecutionPolicyState,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._state = state

    def authorize(self, module_id: str) -> ExecutionPolicyDecision:
        """
        Pure permission check. Does NOT mutate ExecutionPolicyState.

        Raises:
            ModuleNotFoundError / ModuleNotActiveError: propagated from
                registry.resolve() for module-level failures.

        Returns:
            ExecutionPolicyDecision. Callers must call record_execution()
            separately, and only if they actually go on to execute the
            module.
        """
        self._registry.resolve(module_id)  # raises on lifecycle failure

        lifecycle_state = self._registry.lifecycle_state(module_id)
        capabilities = self._registry.capabilities(module_id)
        current_count = self._state.get_count(module_id)
        limit = self._policy.max_invocations_per_module_lifetime

        if limit is not None and current_count >= limit:
            return ExecutionPolicyDecision(
                module_id=module_id,
                allowed=False,
                reason="DENIED_RATE_LIMIT",
                observed_lifecycle_state=lifecycle_state,
                policy_hash=self._policy.policy_hash,
                capability_snapshot_hash=capabilities.capability_hash,
                observed_invocation_count=current_count,
                max_allowed_invocations=limit,
            )

        return ExecutionPolicyDecision(
            module_id=module_id,
            allowed=True,
            reason="ALLOWED",
            observed_lifecycle_state=lifecycle_state,
            policy_hash=self._policy.policy_hash,
            capability_snapshot_hash=capabilities.capability_hash,
            observed_invocation_count=current_count,
            max_allowed_invocations=limit,
        )

    def record_execution(self, decision: ExecutionPolicyDecision) -> int:
        """
        Records that execution actually occurred following an allowed
        decision. Increments ExecutionPolicyState for decision.module_id
        and returns the new count.

        Raises:
            RecordExecutionError: decision.allowed is False. Recording
                execution for a denied decision is never valid — the
                caller should not have executed in that case.
        """
        if not decision.allowed:
            raise RecordExecutionError(
                f"Cannot record_execution() for a denied decision "
                f"(module '{decision.module_id}', reason: {decision.reason}). "
                f"Only allowed=True decisions may be followed by execution."
            )
        return self._state.increment(decision.module_id)
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

v2.3 (2026-08-06): ExecutionPolicyDecision and DecisionValidationError
moved to execution_policy_decision_contract.py -- see that module's own
docstring for why (test_verifier_runtime_isolation.py caught
causal_history_verifier.py transitively importing this entire module,
including ExecutionModuleRegistry/ExecutionPolicy/ExecutionPolicyState,
merely to get ExecutionPolicyDecision, which never needed any of them).
Imported here instead of defined here -- ExecutionAuthorizer's behavior
is completely unchanged; only the location of its own dependency moved.
RecordExecutionError stays here, since it describes a failure mode of
ExecutionAuthorizer.record_execution() specifically, not of
ExecutionPolicyDecision's construction.
"""

from execution_module_registry import ExecutionModuleRegistry, ModuleCapabilities
from module_lifecycle import ModuleState
from execution_policy import ExecutionPolicy
from execution_policy_state import ExecutionPolicyState
from execution_policy_decision_contract import (
    ExecutionPolicyDecision,
    DecisionValidationError,
)


class RecordExecutionError(Exception):
    """Raised when record_execution() is called in a way that violates
    the authorize-then-record contract."""
    pass


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

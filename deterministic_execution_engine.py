"""
Deterministic Execution Engine & State Evolution Operator - Sentinel Framework

v2.5: DecisionRecord history. The engine now records exactly one
DecisionRecord per execution attempt that reaches the authorization
boundary, whenever an authorizer is attached — for both allowed and
denied outcomes. This is separate from audit_log (which only records
executions that actually dispatched). See v2.5 design document for the
full invariant set (A: exactly one decision per attempt, B: every audit
record has exactly one preceding allowed decision, C: replay preserves
causal ordering, not just hash values).

Still holds from v2.4: this module imports NOTHING from execution_policy.py,
execution_policy_state.py, or execution_authorizer.py beyond duck-typed
calls to authorizer.authorize()/record_execution(). decision_record_contract
IS imported here, since DecisionRecord is engine-owned history, not policy
internals — it's the same category as ExecutionAuditRecord already is.
"""

from typing import Any, List, Optional, Tuple

from execution_kernel_state import (
    KernelState,
    KernelStateMachine,
    KernelStateEnvelope,
    InvalidStateTransitionError,
    StateMachineError,
)
from execution_kernel_contract import CoreExecutionFrame
from execution_module_contract import ExecutionModule, ExecutionResult
from execution_audit_contract import ExecutionAuditRecord
from decision_record_contract import DecisionRecord


class ExecutionEngineError(Exception):
    """Base exception for deterministic execution engine failures."""
    pass


class StateIntegrityError(ExecutionEngineError):
    """Raised when incoming frame provenance verification fails."""
    pass


class AuthorizationDeniedError(ExecutionEngineError):
    """
    Raised when an injected authorizer denies execution for a frame.
    A DecisionRecord is appended to decision_log BEFORE this is raised —
    denial is a recorded event, not just an exception.
    """

    def __init__(self, decision: Any) -> None:
        self.decision = decision
        module_id = getattr(decision, "module_id", "<unknown>")
        reason = getattr(decision, "reason", "<no reason provided>")
        super().__init__(
            "Execution denied for module '" + str(module_id) + "': " + str(reason)
        )


class DeterministicExecutionEngine:
    def __init__(
        self,
        module: Optional[ExecutionModule] = None,
        authorizer: Optional[Any] = None,
    ) -> None:
        self._state_machine = KernelStateMachine(initial_state=KernelState.UNINITIALIZED)
        self._module = module
        self._authorizer = authorizer
        self._audit_log: List[ExecutionAuditRecord] = []
        self._decision_log: List[DecisionRecord] = []

    @property
    def state_machine(self) -> KernelStateMachine:
        return self._state_machine

    @property
    def module(self) -> Optional[ExecutionModule]:
        return self._module

    @property
    def authorizer(self) -> Optional[Any]:
        return self._authorizer

    @property
    def audit_log(self) -> Tuple[ExecutionAuditRecord, ...]:
        return tuple(self._audit_log)

    @property
    def decision_log(self) -> Tuple[DecisionRecord, ...]:
        """
        Engine-owned decision history. Contains exactly one DecisionRecord
        per execution attempt that reached the authorization boundary with
        an authorizer attached — Invariant A. Independent of audit_log:
        a denied attempt appears here with no corresponding audit_log entry.
        """
        return tuple(self._decision_log)

    def initialize(self) -> KernelStateEnvelope:
        self._state_machine.transition_to(KernelState.INITIALIZING)
        return self._state_machine.transition_to(KernelState.READY)

    def process_frame(self, frame: CoreExecutionFrame) -> Tuple[KernelStateEnvelope, Optional[ExecutionResult]]:
        current_state = self._state_machine.current_state

        if current_state not in (KernelState.READY, KernelState.PROCESSING):
            raise ExecutionEngineError(
                "Cannot process frame in state " + current_state.name + ". Must be in READY or PROCESSING."
            )

        # 1. Frame integrity — unchanged.
        try:
            frame.verify_integrity()
        except ValueError as ve:
            if self._state_machine.current_state != KernelState.FAULTED:
                try:
                    self._state_machine.transition_to(
                        KernelState.FAULTED,
                        reason="PROVENANCE_FAILURE: Frame " + str(frame.seq_id) + " failed integrity verification."
                    )
                except InvalidStateTransitionError:
                    pass
            raise StateIntegrityError(
                "Frame " + str(frame.seq_id) + " failed provenance hash verification."
            ) from ve

        prior_envelope = self._state_machine.get_envelope()

        # 2. Authorization gate + DecisionRecord emission (v2.5).
        # Recorded for BOTH allowed and denied outcomes, before any kernel
        # state mutation — matching v2.4's "denial leaves kernel state
        # untouched" behavior. The record itself is not kernel state; it's
        # decision history, appended regardless of the outcome.
        decision = None
        if self._authorizer is not None and self._module is not None:
            decision = self._authorizer.authorize(self._module.module_id)

            record = DecisionRecord(
                sequence_id=frame.seq_id,
                module_id=self._module.module_id,
                allowed=decision.allowed,
                decision_hash=decision.decision_hash,
            )
            self._decision_log.append(record)

            if not decision.allowed:
                raise AuthorizationDeniedError(decision)

        # 3. Existing PROCESSING transition and sequence tracking.
        if current_state == KernelState.READY:
            self._state_machine.transition_to(KernelState.PROCESSING)

        try:
            self._state_machine.record_frame_execution(frame.seq_id)

            result = None
            if self._module is not None:
                result = self._module.execute(frame, prior_envelope)

                audit_record = ExecutionAuditRecord.from_execution(
                    sequence_id=frame.seq_id,
                    input_hash=frame.provenance_hash,
                    prior_state_hash=prior_envelope.state_hash,
                    frame_timestamp_ns=frame.timestamp_ns,
                    module_id=self._module.module_id,
                    result=result,
                )
                self._audit_log.append(audit_record)

                if self._authorizer is not None and decision is not None:
                    self._authorizer.record_execution(decision)

                if not result.success:
                    if self._state_machine.current_state != KernelState.FAULTED:
                        try:
                            self._state_machine.transition_to(
                                KernelState.FAULTED,
                                reason=str(result.error_message)
                            )
                        except InvalidStateTransitionError:
                            pass
                    raise ExecutionEngineError(
                        "Module execution failed on seq_id " + str(frame.seq_id) + ": " + str(result.error_message)
                    )

            post_envelope = self._state_machine.transition_to(KernelState.READY)
            return post_envelope, result

        except StateMachineError:
            if self._state_machine.current_state != KernelState.FAULTED:
                try:
                    self._state_machine.transition_to(
                        KernelState.FAULTED,
                        reason="SEQUENCE_VIOLATION: seq_id " + str(frame.seq_id)
                    )
                except InvalidStateTransitionError:
                    pass
            raise

        except ExecutionEngineError:
            raise

        except Exception as err:
            if self._state_machine.current_state != KernelState.FAULTED:
                try:
                    self._state_machine.transition_to(
                        KernelState.FAULTED,
                        reason="EXECUTION_FAILURE: " + str(err)
                    )
                except InvalidStateTransitionError:
                    pass
            raise ExecutionEngineError("Execution failed on seq_id " + str(frame.seq_id) + ": " + str(err)) from err

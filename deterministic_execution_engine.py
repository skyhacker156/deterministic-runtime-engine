"""
Deterministic Execution Engine & State Evolution Operator - Sentinel Framework
Implements Step 2 of Phase 2 (Execution Semantics): f(S_t, Frame_k) -> (S_{t+1}, ExecutionResult_k)

Step 2 addition: the engine now emits an immutable ExecutionAuditRecord for every
frame that reaches module dispatch (success or graceful failure). The audit layer
is purely observational — it records facts already computed elsewhere and never
alters the control flow, transition logic, or fault behavior established prior to
this change.
"""

from typing import List, Optional, Tuple

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


class ExecutionEngineError(Exception):
    """Base exception for deterministic execution engine failures."""
    pass


class StateIntegrityError(ExecutionEngineError):
    """Raised when incoming frame provenance verification fails."""
    pass


class DeterministicExecutionEngine:
    def __init__(self, module: Optional[ExecutionModule] = None) -> None:
        self._state_machine = KernelStateMachine(initial_state=KernelState.UNINITIALIZED)
        self._module = module
        self._audit_log: List[ExecutionAuditRecord] = []

    @property
    def state_machine(self) -> KernelStateMachine:
        return self._state_machine

    @property
    def module(self) -> Optional[ExecutionModule]:
        return self._module

    @property
    def audit_log(self) -> Tuple[ExecutionAuditRecord, ...]:
        """Immutable, ordered view of every audit record emitted so far."""
        return tuple(self._audit_log)

    def initialize(self) -> KernelStateEnvelope:
        self._state_machine.transition_to(KernelState.INITIALIZING)
        return self._state_machine.transition_to(KernelState.READY)

    def process_frame(self, frame: CoreExecutionFrame) -> Tuple[KernelStateEnvelope, Optional[ExecutionResult]]:
        current_state = self._state_machine.current_state

        if current_state not in (KernelState.READY, KernelState.PROCESSING):
            raise ExecutionEngineError(
                "Cannot process frame in state " + current_state.name + ". Must be in READY or PROCESSING."
            )

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

        if current_state == KernelState.READY:
            self._state_machine.transition_to(KernelState.PROCESSING)

        try:
            self._state_machine.record_frame_execution(frame.seq_id)

            result = None
            if self._module is not None:
                result = self._module.execute(frame, prior_envelope)

                # --- Step 2: emit observational audit record ---
                # Recorded regardless of success/failure, before any fault handling,
                # so the audit trail captures exactly what the module reported.
                audit_record = ExecutionAuditRecord.from_execution(
                    sequence_id=frame.seq_id,
                    input_hash=frame.provenance_hash,
                    prior_state_hash=prior_envelope.state_hash,
                    frame_timestamp_ns=frame.timestamp_ns,
                    module_id=self._module.module_id,
                    result=result,
                )
                self._audit_log.append(audit_record)
                # --- end Step 2 addition ---

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
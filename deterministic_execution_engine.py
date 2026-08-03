"""
Deterministic Execution Engine & State Evolution Operator - Sentinel Framework
Implements Step 2 of Phase 2 (Execution Semantics): f(S_t, Frame_k) -> (S_{t+1}, ExecutionResult_k)
"""

from typing import Optional, Tuple

from execution_kernel_state import (
    KernelState,
    KernelStateMachine,
    KernelStateEnvelope,
    InvalidStateTransitionError,
    StateMachineError,
)
from execution_kernel_contract import CoreExecutionFrame
from execution_module_contract import ExecutionModule, ExecutionResult


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

    @property
    def state_machine(self) -> KernelStateMachine:
        return self._state_machine

    @property
    def module(self) -> Optional[ExecutionModule]:
        return self._module

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
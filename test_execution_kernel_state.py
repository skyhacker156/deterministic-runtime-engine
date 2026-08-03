"""
Unit Test Suite for Execution Kernel State Machine (test_execution_kernel_state.py)
"""

import pytest
from execution_kernel_state import (
    KernelState,
    KernelStateMachine,
    KernelStateEnvelope,
    StateMachineError,
    InvalidStateTransitionError,
    VALID_TRANSITIONS,
)


def test_initialization_and_envelope_struct_pack():
    sm = KernelStateMachine(initial_state=KernelState.UNINITIALIZED)
    assert sm.current_state == KernelState.UNINITIALIZED
    assert sm.last_processed_seq == -1
    assert sm.total_frames_processed == 0

    envelope = sm.get_envelope()
    assert isinstance(envelope, KernelStateEnvelope)
    assert envelope.state == KernelState.UNINITIALIZED
    assert len(envelope.state_hash) == 32  # SHA-256 digest size


def test_valid_lifecycle_progression():
    sm = KernelStateMachine()
    
    # UNINITIALIZED -> INITIALIZING -> READY
    sm.transition_to(KernelState.INITIALIZING)
    assert sm.current_state == KernelState.INITIALIZING
    
    sm.transition_to(KernelState.READY)
    assert sm.current_state == KernelState.READY

    # READY -> PROCESSING -> READY
    sm.transition_to(KernelState.PROCESSING)
    sm.record_frame_execution(0)
    assert sm.last_processed_seq == 0
    assert sm.total_frames_processed == 1

    sm.transition_to(KernelState.READY)
    assert sm.current_state == KernelState.READY


def test_illegal_transition_auto_faults():
    """
    Verifies that attempting an illegal transition automatically forces the state
    machine into KernelState.FAULTED and raises InvalidStateTransitionError.
    """
    sm = KernelStateMachine(initial_state=KernelState.UNINITIALIZED)

    # UNINITIALIZED -> PROCESSING is illegal (must go through INITIALIZING and READY)
    with pytest.raises(InvalidStateTransitionError, match="Illegal state transition"):
        sm.transition_to(KernelState.PROCESSING)

    # State machine must be forced to FAULTED
    assert sm.current_state == KernelState.FAULTED
    assert "TRANSITION_VIOLATION" in sm.get_envelope().active_fault_reason


def test_administrative_reset_clears_sequence_counters():
    sm = KernelStateMachine()
    sm.transition_to(KernelState.INITIALIZING)
    sm.transition_to(KernelState.READY)
    sm.transition_to(KernelState.PROCESSING)
    sm.record_frame_execution(0)

    # Trip fault
    sm.transition_to(KernelState.FAULTED, reason="Test fault injection")
    assert sm.current_state == KernelState.FAULTED

    # Reset path: FAULTED -> INITIALIZING
    sm.transition_to(KernelState.INITIALIZING)
    assert sm.current_state == KernelState.INITIALIZING
    assert sm.last_processed_seq == -1
    assert sm.total_frames_processed == 0
    assert sm.fault_reason is None


def test_non_monotonic_frame_execution_rejected():
    """Verifies that submitting out-of-order sequence IDs raises StateMachineError."""
    sm = KernelStateMachine(initial_state=KernelState.UNINITIALIZED)
    sm.transition_to(KernelState.INITIALIZING)
    sm.transition_to(KernelState.READY)
    sm.transition_to(KernelState.PROCESSING)

    # Submitting sequence 10 out of order (expecting 0) must raise StateMachineError
    with pytest.raises(StateMachineError):
        sm.record_frame_execution(10)
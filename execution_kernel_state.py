"""
Execution Kernel State Machine & Envelope Tracking - Sentinel Framework
Provides lifecycle state management, invariant enforcement, and SHA-256 state hashing.
"""

from enum import Enum, auto
from dataclasses import dataclass
import hashlib
import struct
from typing import Optional, Set, Dict


class KernelState(Enum):
    UNINITIALIZED = auto()
    INITIALIZING = auto()
    READY = auto()
    PROCESSING = auto()
    TERMINATED = auto()
    FAULTED = auto()


class StateMachineError(Exception):
    """Base exception for kernel state machine violations."""
    pass


class InvalidStateTransitionError(StateMachineError):
    """Raised when an illegal transition between states is attempted."""
    pass


# Public map of permissible state transitions
VALID_TRANSITIONS: Dict[KernelState, Set[KernelState]] = {
    KernelState.UNINITIALIZED: {KernelState.INITIALIZING, KernelState.FAULTED},
    KernelState.INITIALIZING: {KernelState.READY, KernelState.FAULTED},
    KernelState.READY: {KernelState.PROCESSING, KernelState.TERMINATED, KernelState.FAULTED},
    KernelState.PROCESSING: {KernelState.READY, KernelState.FAULTED},
    KernelState.FAULTED: {KernelState.INITIALIZING},  # Administrative reset path
    KernelState.TERMINATED: set(),  # Terminal state
}


@dataclass(frozen=True)
class KernelStateEnvelope:
    """
    Immutable envelope capturing a cryptographic snapshot of current state.
    """
    state: KernelState
    last_processed_seq: int
    total_frames_processed: int
    fault_reason: Optional[str]
    state_hash: bytes

    @property
    def active_fault_reason(self) -> Optional[str]:
        """Alias for fault_reason to maintain compatibility across assertion contracts."""
        return self.fault_reason


class KernelStateMachine:
    """
    Enforces state transitions and sequence tracking for the execution core.
    """

    VALID_TRANSITIONS = VALID_TRANSITIONS

    def __init__(self, initial_state: KernelState = KernelState.UNINITIALIZED) -> None:
        self._current_state: KernelState = initial_state
        self._last_processed_seq: int = -1
        self._total_frames_processed: int = 0
        self._fault_reason: Optional[str] = None

    @property
    def current_state(self) -> KernelState:
        return self._current_state

    @property
    def last_processed_seq(self) -> int:
        return self._last_processed_seq

    @property
    def total_frames_processed(self) -> int:
        return self._total_frames_processed

    @property
    def fault_reason(self) -> Optional[str]:
        return self._fault_reason

    def transition_to(self, new_state: KernelState, reason: Optional[str] = None) -> KernelStateEnvelope:
        """
        Transitions kernel state if allowed by state machine invariants.
        If transition is illegal, trips the kernel into FAULTED state and raises InvalidStateTransitionError.
        """
        allowed = self.VALID_TRANSITIONS.get(self._current_state, set())

        if new_state not in allowed:
            err_msg = f"Illegal state transition from {self._current_state.name} to {new_state.name}"
            if self._current_state != KernelState.FAULTED:
                self._current_state = KernelState.FAULTED
                self._fault_reason = f"TRANSITION_VIOLATION: {err_msg}"
            raise InvalidStateTransitionError(err_msg)

        # Handle Administrative Reset (FAULTED -> INITIALIZING)
        if self._current_state == KernelState.FAULTED and new_state == KernelState.INITIALIZING:
            self._last_processed_seq = -1
            self._total_frames_processed = 0
            self._fault_reason = None

        if new_state == KernelState.FAULTED:
            self._fault_reason = reason or "Unspecified kernel fault"

        self._current_state = new_state
        return self.get_envelope()

    def record_frame_execution(self, seq_id: int) -> None:
        """
        Updates monotonic sequence execution tracking. Must be called while in PROCESSING state.
        Enforces strict contiguous progression (seq_id == last_processed_seq + 1).
        """
        if self._current_state != KernelState.PROCESSING:
            raise StateMachineError(
                f"Frame execution can only be recorded in PROCESSING state, currently in {self._current_state.name}."
            )

        expected_seq = self._last_processed_seq + 1 if self._last_processed_seq != -1 else 0
        if seq_id != expected_seq:
            raise StateMachineError(
                f"Non-contiguous or non-monotonic sequence ID execution attempt: received {seq_id}, expected {expected_seq}."
            )

        self._last_processed_seq = seq_id
        self._total_frames_processed += 1

    def get_envelope(self) -> KernelStateEnvelope:
        """
        Computes current cryptographic state hash and returns KernelStateEnvelope.
        Packs metadata using big-endian struct encoding:
        - last_processed_seq: int64 ('q')
        - total_frames_processed: uint64 ('Q')
        - state_enum_value: uint32 ('I')
        """
        hasher = hashlib.sha256()

        packed_meta = struct.pack(
            ">qQI",
            self._last_processed_seq,
            self._total_frames_processed,
            self._current_state.value
        )
        hasher.update(packed_meta)

        if self._fault_reason:
            hasher.update(self._fault_reason.encode("utf-8"))

        state_hash = hasher.digest()

        return KernelStateEnvelope(
            state=self._current_state,
            last_processed_seq=self._last_processed_seq,
            total_frames_processed=self._total_frames_processed,
            fault_reason=self._fault_reason,
            state_hash=state_hash,
        )
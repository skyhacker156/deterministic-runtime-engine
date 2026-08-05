"""
Execution Kernel State Machine & Envelope Tracking - Sentinel Framework
Provides lifecycle state management, invariant enforcement, and SHA-256 state hashing.

v2 (generation_id): KernelStateEnvelope and its hash now include
generation_id, a 16-byte UUID4 generated once at true genesis
(KernelStateMachine.__init__) and regenerated ONLY on an administrative
reset (FAULTED -> INITIALIZING). This closes the kernel-level half of
Gap 1b: two envelopes with identical scalar snapshots (last_processed_seq,
total_frames_processed, current_state, fault_reason) that occurred in
different generations now produce DIFFERENT state_hash values, because
generation_id differs. See GENERATION_ID_MIGRATION_NOTE.md for the full
migration philosophy -- this intentionally invalidates prior hash values;
no backward hash compatibility is attempted.

get_envelope()'s hash computation also gains an explicit format-version
byte for the first time (previously unversioned) -- normalized in the
same pass as generation_id, since this is the cheapest point to fix
that inconsistency.

v2.1 (from_history): added KernelStateMachine.from_history(), the ONLY
entry point through which an externally-supplied generation_id can enter
a KernelStateMachine. __init__ still never accepts one and never will --
"mint a new identity" (production genesis, and production's
FAULTED->INITIALIZING reset) and "restore a known identity" (replay)
are kept as two structurally distinct entry points on purpose. See
from_history()'s own docstring for its scope (single-generation
reconstruction only) and GenerationMismatchError for the exception type
replay callers should raise when that scope is exceeded.
"""

from enum import Enum, auto
from dataclasses import dataclass
import hashlib
import struct
import uuid
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


class GenerationMismatchError(StateMachineError):
    """
    Raised by replay-driving code (NOT by KernelStateMachine itself) when
    a persisted record's generation_id does not match the generation a
    KernelStateMachine was reconstructed to represent via from_history()
    -- i.e. replay has hit a generation boundary (an administrative
    reset occurred in the real history being replayed) that the current
    single-generation scope of from_history() doesn't cross.

    KernelStateMachine has no way to raise this on its own -- it has no
    visibility into a persisted record stream. It exists here, alongside
    the other state-machine exceptions, so replay code (e.g.
    kernel_state_replay.py) has a shared, discoverable exception type to
    raise or fold into a report rather than each replay caller inventing
    its own. See from_history()'s docstring and
    GENERATION_ID_MIGRATION_NOTE.md.
    """
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

    generation_id: 16-byte UUID4 identifying which kernel generation
    this envelope belongs to. Constant across an entire generation;
    changes only when an administrative reset occurs. Included in
    state_hash specifically so two envelopes with otherwise-identical
    scalar fields, occurring in different generations, produce
    different hashes -- see module docstring.
    """
    state: KernelState
    last_processed_seq: int
    total_frames_processed: int
    fault_reason: Optional[str]
    generation_id: bytes
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

    # Format version for KernelStateEnvelope.state_hash's packed bytes.
    # First explicit version for this hash -- previously unversioned.
    STATE_HASH_FORMAT_VERSION = 1

    def __init__(self, initial_state: KernelState = KernelState.UNINITIALIZED) -> None:
        self._current_state: KernelState = initial_state
        self._last_processed_seq: int = -1
        self._total_frames_processed: int = 0
        self._fault_reason: Optional[str] = None
        # True genesis: one generation_id for the life of this instance,
        # UNLESS an administrative reset occurs (see transition_to below).
        # This is the ONLY place besides the reset branch below where
        # uuid.uuid4() is called -- from_history() below never calls it.
        self._generation_id: bytes = uuid.uuid4().bytes

    @classmethod
    def from_history(
        cls,
        generation_id: bytes,
        state: KernelState = KernelState.PROCESSING,
        last_processed_seq: int = -1,
        total_frames_processed: int = 0,
        fault_reason: Optional[str] = None,
    ) -> "KernelStateMachine":
        """
        Reconstructs a KernelStateMachine representing an ALREADY-KNOWN
        generation, for replay/verification use only.

        This is the one and only way a generation_id enters a
        KernelStateMachine from outside. __init__ never accepts one and
        never will -- "mint a new identity" (production genesis, and
        production's FAULTED->INITIALIZING reset) and "restore a known
        identity" (replay) are kept as two structurally distinct entry
        points on purpose, so a future caller can't hand a real
        generation_id into ordinary construction by accident and quietly
        defeat the genesis guarantee this migration exists to establish.

        Bypasses __init__ entirely (via cls.__new__) specifically so this
        path never calls uuid.uuid4() under any circumstance -- fresh
        identity minting and identity restoration cannot share a code
        path here even coincidentally.

        SCOPE -- deliberate, current limitation:
        This reconstructs a SINGLE generation. It does not walk a
        persisted history that contains an administrative reset
        (FAULTED -> INITIALIZING) and does not attempt multi-generation
        lineage reconstruction. If a machine built here is driven through
        transition_to() and legitimately hits a reset, it WILL mint a
        genuinely new random generation_id at that point -- identical
        behavior to a fresh KernelStateMachine(), because it's the same
        code path. This method does not detect or reject that on its
        own.

        Responsibility for staying within this scope belongs to the
        replay caller, not to this method: generation_id is already a
        stored field on both DecisionRecord and ExecutionAuditRecord, so
        code walking a persisted log in sequence can and should compare
        each record's generation_id against the value it started
        from_history() with, and stop -- reporting the boundary rather
        than silently continuing past it -- the moment it changes.
        Raise GenerationMismatchError (or fold the boundary into the
        calling report structure, e.g. KernelReplayReport) at that
        comparison point; this method has no way to enforce it from
        inside, since it has no visibility into the record stream at
        all.

        Lineage-spanning reconstruction (replaying THROUGH a reset and
        adopting each successive generation_id in turn) is intentionally
        out of scope here and tracked as a separate follow-up.
        """
        instance = cls.__new__(cls)
        instance._current_state = state
        instance._last_processed_seq = last_processed_seq
        instance._total_frames_processed = total_frames_processed
        instance._fault_reason = fault_reason
        instance._generation_id = generation_id
        return instance

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

    @property
    def generation_id(self) -> bytes:
        return self._generation_id

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
            # NEW generation begins here -- this is the ONLY place
            # generation_id ever changes after __init__ (and the only
            # other place besides __init__ that calls uuid.uuid4() at
            # all). Everything from this point forward is a distinct
            # generation from what came before, and every
            # envelope/record produced after this line will carry a
            # different generation_id than everything produced before
            # it.
            self._generation_id = uuid.uuid4().bytes

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
        - format_version: uint8 ('B') -- NEW in v2
        - last_processed_seq: int64 ('q')
        - total_frames_processed: uint64 ('Q')
        - state_enum_value: uint32 ('I')
        followed by generation_id (16 raw bytes) and, if present,
        fault_reason (utf-8 encoded).
        """
        hasher = hashlib.sha256()

        hasher.update(struct.pack(">B", self.STATE_HASH_FORMAT_VERSION))

        packed_meta = struct.pack(
            ">qQI",
            self._last_processed_seq,
            self._total_frames_processed,
            self._current_state.value
        )
        hasher.update(packed_meta)

        hasher.update(self._generation_id)

        if self._fault_reason:
            hasher.update(self._fault_reason.encode("utf-8"))

        state_hash = hasher.digest()

        return KernelStateEnvelope(
            state=self._current_state,
            last_processed_seq=self._last_processed_seq,
            total_frames_processed=self._total_frames_processed,
            fault_reason=self._fault_reason,
            generation_id=self._generation_id,
            state_hash=state_hash,
        )

"""
Deterministic Ordering Barrier - Sentinel Framework (Phoenix A Core)
Re-orders concurrently parsed CoreExecutionFrame objects into a strictly monotonic stream
(0, 1, 2...) for the execution kernel.

ARCHITECTURAL CONTRACT (Option B - Single Consumer Queue Pattern):
-----------------------------------------------------------------
This component is intentionally NOT internally thread-safe.
To maximize single-thread instruction throughput and eliminate lock contention:
  1. Concurrently executing worker pools MUST push parsed frames into an upstream thread-safe Queue.
  2. A SINGLE dedicated consumer loop MUST poll the Queue and invoke push() on this barrier.

Direct concurrent invocations from multiple threads will trigger a ThreadBoundaryError.
"""

from dataclasses import dataclass
import threading
from typing import Dict, List, Optional, Tuple
from execution_kernel_contract import CoreExecutionFrame


class BarrierError(Exception):
    """Base exception for ordering barrier violations."""
    pass


class ThreadBoundaryError(BarrierError):
    """Raised when the barrier is accessed concurrently across multiple thread contexts."""
    pass


class BackpressureExceededError(BarrierError):
    """Raised when out-of-order buffer exceeds capacity due to a missing sequence ID."""
    pass


class DuplicateFrameError(BarrierError):
    """Raised when a frame with an already-processed or buffered seq_id arrives."""
    pass


@dataclass(frozen=True)
class SequenceGapRecord:
    """Audit record indicating an explicitly skipped/lost frame sequence number."""
    skipped_seq_id: int
    reason: str


@dataclass
class BarrierMetrics:
    """Diagnostic readout for the barrier's current operational state."""
    next_expected_seq: int
    buffer_depth: int
    max_window_size: int
    total_emitted: int
    total_gaps_skipped: int


class DeterministicOrderingBarrier:
    """
    Sliding-window priority re-ordering barrier.
    Guarantees deterministic, sequential delivery of frames to the execution core.
    """
    def __init__(
        self, 
        initial_seq_id: int = 0, 
        max_window_size: int = 1000,
        auto_skip_on_backpressure: bool = False,
        enforce_single_thread_ownership: bool = True
    ) -> None:
        self._next_expected_seq: int = initial_seq_id
        self._max_window_size: int = max_window_size
        self._auto_skip: bool = auto_skip_on_backpressure
        self._enforce_single_thread: bool = enforce_single_thread_ownership
        self._owner_thread_id: Optional[int] = None
        
        self._total_emitted: int = 0
        self._total_gaps_skipped: int = 0
        self._gap_log: List[SequenceGapRecord] = []
        
        # Internal buffer mapping seq_id -> CoreExecutionFrame for O(1) lookup
        self._frame_buffer: Dict[int, CoreExecutionFrame] = {}

    def _verify_thread_safety(self) -> None:
        """Enforces that all mutations originate from the single assigned consumer thread."""
        current_thread = threading.get_ident()
        if self._owner_thread_id is None:
            self._owner_thread_id = current_thread
        elif self._owner_thread_id != current_thread and self._enforce_single_thread:
            raise ThreadBoundaryError(
                f"Barrier thread boundary violation: Owner thread is {self._owner_thread_id}, "
                f"but call was made from thread {current_thread}. "
                "Ensure upstream workers route through a single-consumer queue."
            )

    @property
    def next_expected_seq(self) -> int:
        return self._next_expected_seq

    @property
    def buffer_depth(self) -> int:
        return len(self._frame_buffer)

    def push(self, frame: CoreExecutionFrame) -> List[CoreExecutionFrame]:
        """
        Ingests a frame from the dedicated consumer thread.
        Returns a consecutive sequence of ready frames.
        """
        self._verify_thread_safety()
        seq = frame.seq_id

        # 1. Ignore/Reject stale or duplicate frames
        if seq < self._next_expected_seq:
            raise DuplicateFrameError(
                f"Received stale frame {seq}. Currently expecting >= {self._next_expected_seq}."
            )

        if seq in self._frame_buffer:
            raise DuplicateFrameError(f"Duplicate frame {seq} already present in barrier buffer.")

        unblocked_from_skip: List[CoreExecutionFrame] = []

        # 2. Check Backpressure Boundaries
        if len(self._frame_buffer) >= self._max_window_size:
            if self._auto_skip:
                # Resolve stall by skipping stalled sequence frame and capturing unblocked frames
                _, unblocked_from_skip = self.force_skip_next_expected(
                    f"Auto-skipped missing frame {self._next_expected_seq} due to backpressure."
                )
            else:
                raise BackpressureExceededError(
                    f"Barrier window depth limit ({self._max_window_size}) reached. "
                    f"Missing frame {self._next_expected_seq} is stalling the pipeline."
                )

        # 3. Insert frame into buffer
        self._frame_buffer[seq] = frame

        # 4. Drain contiguous monotonic sequence starting at next_expected_seq
        drained = self._drain_ready_frames()

        return unblocked_from_skip + drained

    def force_skip_next_expected(self, reason: str = "Manual caller skip") -> Tuple[SequenceGapRecord, List[CoreExecutionFrame]]:
        """
        Explicitly skips the currently expected sequence number to break a pipeline deadlock.
        Advances next_expected_seq, logs an immutable audit record, and drains any newly unblocked frames.
        """
        self._verify_thread_safety()
        stalled_seq = self._next_expected_seq
        gap = SequenceGapRecord(skipped_seq_id=stalled_seq, reason=reason)
        
        self._gap_log.append(gap)
        self._total_gaps_skipped += 1
        self._next_expected_seq += 1

        # Immediately drain frames unlocked by skipping this gap
        unblocked_frames = self._drain_ready_frames()

        return gap, unblocked_frames

    def _drain_ready_frames(self) -> List[CoreExecutionFrame]:
        """Internal helper to pop all contiguous sequential frames available."""
        ready_frames: List[CoreExecutionFrame] = []
        while self._next_expected_seq in self._frame_buffer:
            next_frame = self._frame_buffer.pop(self._next_expected_seq)
            ready_frames.append(next_frame)
            self._next_expected_seq += 1
            self._total_emitted += 1

        return ready_frames

    def get_gap_log(self) -> List[SequenceGapRecord]:
        """Returns read-only list of gap audit records."""
        return list(self._gap_log)

    def get_metrics(self) -> BarrierMetrics:
        """Returns snapshot of barrier metrics."""
        return BarrierMetrics(
            next_expected_seq=self._next_expected_seq,
            buffer_depth=self.buffer_depth,
            max_window_size=self._max_window_size,
            total_emitted=self._total_emitted,
            total_gaps_skipped=self._total_gaps_skipped,
        )
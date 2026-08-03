"""
Ordering Barrier Verification & Hypothesis Fuzz Suite - Sentinel Framework
Verifies permutation reordering, stale frame rejection, backpressure bounds, 
explicit deadlock resolution, and thread boundary invariants.
"""

import concurrent.futures
import hashlib
import struct
import pytest
import numpy as np
from hypothesis import given, strategies as st, settings

from execution_kernel_contract import CoreExecutionFrame
from ordering_barrier import (
    DeterministicOrderingBarrier,
    BackpressureExceededError,
    DuplicateFrameError,
    ThreadBoundaryError,
)


def create_mock_frame(seq_id: int) -> CoreExecutionFrame:
    """Utility helper to build valid CoreExecutionFrame instances."""
    timestamp_ns = 1_000_000_000 + seq_id * 1_000
    payload = np.full(256, 1.0, dtype=np.float64)

    hasher = hashlib.sha256()
    hasher.update(struct.pack(">QQ", seq_id, timestamp_ns))
    hasher.update(payload.tobytes())

    return CoreExecutionFrame(
        seq_id=seq_id,
        timestamp_ns=timestamp_ns,
        provenance_hash=hasher.digest(),
        payload=payload,
    )


@given(st.lists(st.integers(min_value=0, max_value=99), unique=True))
@settings(max_examples=50)
def test_hypothesis_fuzz_arrival_permutation_ordering(seq_ids):
    """
    Fuzzes arrival orders across arbitrary sequence ID permutations.
    Asserts output frames are ALWAYS emitted in strictly monotonic sequential order.
    """
    barrier = DeterministicOrderingBarrier(initial_seq_id=0, max_window_size=200)
    emitted_frames = []

    for seq in seq_ids:
        frame = create_mock_frame(seq)
        emitted = barrier.push(frame)
        emitted_frames.extend(emitted)

    # Check monotonicity of emitted frames
    for idx in range(len(emitted_frames) - 1):
        assert emitted_frames[idx + 1].seq_id == emitted_frames[idx].seq_id + 1

    # Verify next_expected_seq matches contiguous head count
    if seq_ids:
        # If sequence was contiguous from 0..N, barrier should have drained everything
        expected_contiguous = list(range(len(seq_ids)))
        if sorted(seq_ids) == expected_contiguous:
            assert len(emitted_frames) == len(seq_ids)
            assert barrier.buffer_depth == 0


def test_stale_and_duplicate_rejection():
    """Verify that duplicate or stale sequence numbers raise DuplicateFrameError."""
    barrier = DeterministicOrderingBarrier(initial_seq_id=0)

    f0 = create_mock_frame(0)
    f1 = create_mock_frame(1)

    barrier.push(f0)
    barrier.push(f1)

    # Push duplicate seq_id=0 (already emitted)
    with pytest.raises(DuplicateFrameError, match="stale frame"):
        barrier.push(f0)

    # Push f3 (f2 missing), buffering f3
    f3 = create_mock_frame(3)
    barrier.push(f3)

    # Push duplicate f3 (currently buffered)
    with pytest.raises(DuplicateFrameError, match="already present"):
        barrier.push(f3)


def test_backpressure_manual_skip_deadlock_resolution():
    """
    Tests that a stalled missing frame triggers backpressure, and force_skip_next_expected()
    resolves the deadlock and immediately drains buffered higher-sequence frames.
    """
    barrier = DeterministicOrderingBarrier(initial_seq_id=0, max_window_size=5)

    # Ingest frames 1 through 5 (Frame 0 is missing!)
    for seq in range(1, 6):
        barrier.push(create_mock_frame(seq))

    assert barrier.buffer_depth == 5
    assert barrier.next_expected_seq == 0

    # Pushing frame 6 should breach backpressure capacity (max_window_size=5)
    with pytest.raises(BackpressureExceededError):
        barrier.push(create_mock_frame(6))

    # Resolve deadlock by explicitly declaring Frame 0 lost.
    # force_skip_next_expected() returns the gap record AND drains unlocked frames 1..5!
    gap_record, unblocked_frames = barrier.force_skip_next_expected("Worker crashed on frame 0")

    assert gap_record.skipped_seq_id == 0
    assert [f.seq_id for f in unblocked_frames] == [1, 2, 3, 4, 5]
    assert barrier.next_expected_seq == 6  # Advanced past 0, 1, 2, 3, 4, 5
    assert barrier.buffer_depth == 0      # Window completely clear now

    # Pushing frame 6 succeeds immediately and returns frame 6
    emitted = barrier.push(create_mock_frame(6))
    assert [f.seq_id for f in emitted] == [6]


def test_auto_skip_on_backpressure_mode():
    """Tests automatic stall recovery when auto_skip_on_backpressure is enabled."""
    barrier = DeterministicOrderingBarrier(
        initial_seq_id=0, 
        max_window_size=3, 
        auto_skip_on_backpressure=True
    )

    # Push frames 1, 2, 3 (Frame 0 missing)
    barrier.push(create_mock_frame(1))
    barrier.push(create_mock_frame(2))
    barrier.push(create_mock_frame(3))

    assert barrier.buffer_depth == 3

    # Frame 4 triggers auto-skip for Frame 0, draining 1, 2, 3 AND 4 in monotonic sequence
    emitted = barrier.push(create_mock_frame(4))

    assert [f.seq_id for f in emitted] == [1, 2, 3, 4]
    assert barrier.get_metrics().total_gaps_skipped == 1
    assert barrier.get_gap_log()[0].skipped_seq_id == 0


def test_single_consumer_thread_boundary_enforcement():
    """
    Verifies that calling push() from a non-owner thread raises ThreadBoundaryError,
    locking down the Option B architectural invariant.
    """
    barrier = DeterministicOrderingBarrier(initial_seq_id=0)

    # Ingest frame 0 on MainThread (establishes ownership)
    barrier.push(create_mock_frame(0))

    # Attempting to call push() from a separate thread worker pool must fail cleanly
    def cross_thread_push():
        barrier.push(create_mock_frame(1))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(cross_thread_push)
        with pytest.raises(ThreadBoundaryError, match="thread boundary violation"):
            future.result()


if __name__ == "__main__":
    pytest.main(["-v", __file__])
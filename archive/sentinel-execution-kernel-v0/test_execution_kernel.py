"""
Execution Kernel Verification Suite - Sentinel Framework
Tests zero-mutation enforcement, deterministic state transitions across independent instances,
and state non-poisoning upon invalid frame entry.
"""

import hashlib
import struct
import pytest
import numpy as np
from execution_kernel_contract import (
    SentinelExecutionKernel,
    CoreExecutionFrame,
    FrameMutationError,
    SequenceDiscontinuityError,
    StateIntegrityError,
)


def create_mock_frame(seq_id: int, payload_val: float = 1.0) -> CoreExecutionFrame:
    """Helper to construct a valid CoreExecutionFrame with matching provenance hash."""
    timestamp_ns = 1_000_000_000 + seq_id * 1_000
    payload = np.full(256, payload_val, dtype=np.float64)

    hasher = hashlib.sha256()
    hasher.update(struct.pack(">QQ", seq_id, timestamp_ns))
    hasher.update(payload.tobytes())
    provenance_hash = hasher.digest()

    return CoreExecutionFrame(
        seq_id=seq_id,
        timestamp_ns=timestamp_ns,
        provenance_hash=provenance_hash,
        payload=payload,
    )


def test_frame_immutability():
    """Verify that payload array modification is strictly blocked at the numpy level."""
    frame = create_mock_frame(seq_id=0)

    # Attempt direct mutation on read-only array
    with pytest.raises(ValueError, match="assignment destination is read-only"):
        frame.payload[0] = 999.0

    # Ensure array writeable flag remains False
    assert not frame.payload.flags.writeable


def test_cross_run_determinism():
    """Verify two separate kernel instances produce identical state digests across N frames."""
    kernel_a = SentinelExecutionKernel(initial_seed=b"SEED_TEST_42")
    kernel_b = SentinelExecutionKernel(initial_seed=b"SEED_TEST_42")

    frames = [create_mock_frame(seq_id=i, payload_val=float(i + 1)) for i in range(50)]

    for f in frames:
        digest_a, success_a = kernel_a.process_frame(f)
        digest_b, success_b = kernel_b.process_frame(f)

        assert success_a and success_b
        assert digest_a == digest_b

    assert kernel_a.state_digest == kernel_b.state_digest
    assert kernel_a.frame_count == 50


def test_sequence_discontinuity_rejection():
    """Verify that out-of-order sequence IDs trigger SequenceDiscontinuityError."""
    kernel = SentinelExecutionKernel()
    frame_0 = create_mock_frame(seq_id=0)
    frame_2 = create_mock_frame(seq_id=2)  # Missing seq_id=1

    kernel.process_frame(frame_0)

    with pytest.raises(SequenceDiscontinuityError):
        kernel.process_frame(frame_2)

    # Confirm kernel state remained at seq_id 0 and did not increment
    snapshot = kernel.get_snapshot()
    assert snapshot.last_seq_id == 0
    assert snapshot.frame_count == 1


def test_state_non_poisoning_on_corrupt_provenance():
    """Verify that a frame with bad provenance is rejected without altering the state digest."""
    kernel = SentinelExecutionKernel()
    frame_valid = create_mock_frame(seq_id=0)

    digest_before, _ = kernel.process_frame(frame_valid)

    # Create a frame with a tampered provenance hash
    bad_payload = np.zeros(256, dtype=np.float64)
    frame_corrupt = CoreExecutionFrame(
        seq_id=1,
        timestamp_ns=1_000_001_000,
        provenance_hash=b"\x00" * 32,  # Invalid hash
        payload=bad_payload,
    )

    with pytest.raises(StateIntegrityError):
        kernel.process_frame(frame_corrupt)

    # Assert state digest S_t remains identical to state before corrupt attempt
    assert kernel.state_digest == digest_before
    assert kernel.get_snapshot().last_seq_id == 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
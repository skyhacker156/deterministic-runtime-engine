"""
Unit Test Suite for Deterministic Execution Engine
(test_deterministic_execution_engine.py)
"""

import hashlib
import struct
import numpy as np
import pytest

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelState, StateMachineError
from deterministic_execution_engine import (
    DeterministicExecutionEngine,
    ExecutionEngineError,
    StateIntegrityError,
)


def create_valid_frame(seq_id: int, timestamp_ns: int = 1_000_000, seed_val: float = 1.0) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    hasher = hashlib.sha256()
    hasher.update(struct.pack(">QQ", seq_id, timestamp_ns))
    hasher.update(payload.tobytes())
    provenance_hash = hasher.digest()

    return CoreExecutionFrame(
        seq_id=seq_id,
        timestamp_ns=timestamp_ns,
        payload=payload,
        provenance_hash=provenance_hash,
    )


def test_happy_path_and_cryptographic_state_chaining():
    engine = DeterministicExecutionEngine()
    initial_env = engine.initialize()
    assert initial_env.state == KernelState.READY
    assert initial_env.last_processed_seq == -1

    frame0 = create_valid_frame(seq_id=0, seed_val=1.0)
    env0, _ = engine.process_frame(frame0)
    assert env0.state == KernelState.READY
    assert env0.last_processed_seq == 0

    frame1 = create_valid_frame(seq_id=1, seed_val=2.0)
    env1, _ = engine.process_frame(frame1)
    assert env1.state == KernelState.READY
    assert env1.last_processed_seq == 1
    assert env1.state_hash != env0.state_hash


def test_corrupted_frame_integrity_rejected():
    engine = DeterministicExecutionEngine()
    engine.initialize()

    corrupt_frame = CoreExecutionFrame(
        seq_id=0,
        timestamp_ns=1_000_000,
        payload=np.full(256, fill_value=1.0, dtype=np.float64),
        provenance_hash=b"\x00" * 32,
    )

    with pytest.raises(StateIntegrityError, match="failed provenance hash verification"):
        engine.process_frame(corrupt_frame)

    assert engine.state_machine.current_state == KernelState.FAULTED


def test_out_of_order_and_duplicate_sequence_rejection():
    engine = DeterministicExecutionEngine()
    engine.initialize()

    engine.process_frame(create_valid_frame(seq_id=0))

    # Duplicate sequence rejection
    with pytest.raises(StateMachineError, match="non-monotonic sequence ID execution attempt"):
        engine.process_frame(create_valid_frame(seq_id=0))

    assert engine.state_machine.current_state == KernelState.FAULTED


def test_replay_equivalence_determinism():
    def run_sequence():
        eng = DeterministicExecutionEngine()
        eng.initialize()
        e0, _ = eng.process_frame(create_valid_frame(seq_id=0, seed_val=10.0))
        e1, _ = eng.process_frame(create_valid_frame(seq_id=1, seed_val=20.0))
        return e0.state_hash, e1.state_hash

    hash0_run1, hash1_run1 = run_sequence()
    hash0_run2, hash1_run2 = run_sequence()

    assert hash0_run1 == hash0_run2
    assert hash1_run1 == hash1_run2
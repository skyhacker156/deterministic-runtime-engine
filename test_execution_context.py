"""
Unit Tests for Stateful Execution Context
(test_execution_context.py)
"""

import pytest
import numpy as np
from execution_context import ExecutionContext


def test_genesis_context_initialization():
    ctx = ExecutionContext(
        seq_id=0,
        timestamp_ns=1700000000000000000,
        state_vector={"counter": 0, "status": "INITIALIZED"}
    )
    assert ctx.seq_id == 0
    assert ctx.timestamp_ns == 1700000000000000000
    assert len(ctx.state_hash) == 32
    assert ctx.parent_state_hash == b"\x00" * 32
    assert len(ctx.history_window) == 0


def test_monotonic_derivation_and_chaining():
    ctx0 = ExecutionContext(
        seq_id=0,
        timestamp_ns=1000,
        state_vector={"val": 10}
    )
    
    ctx1 = ctx0.derive_next(
        next_seq_id=1,
        next_timestamp_ns=2000,
        state_delta={"val": 20, "new_key": "active"}
    )

    assert ctx1.seq_id == 1
    assert ctx1.timestamp_ns == 2000
    assert ctx1.state_vector["val"] == 20
    assert ctx1.state_vector["new_key"] == "active"
    assert ctx1.parent_state_hash == ctx0.state_hash
    assert ctx1.state_hash != ctx0.state_hash
    assert ctx1.history_window == (ctx0.state_hash,)


def test_non_monotonic_sequence_rejection():
    ctx = ExecutionContext(seq_id=5, timestamp_ns=5000)
    
    # Attempt to derive with non-sequential ID (jump to 7) using ValueError
    with pytest.raises(ValueError, match="Non-monotonic context transition"):
        ctx.derive_next(next_seq_id=7, next_timestamp_ns=6000, state_delta={})

    # Attempt backwards sequence using ValueError
    with pytest.raises(ValueError, match="Non-monotonic context transition"):
        ctx.derive_next(next_seq_id=4, next_timestamp_ns=4000, state_delta={})


def test_replay_determinism_across_instances():
    state_data = {"metrics": [1.1, 2.2], "flag": True}
    
    ctx_a = ExecutionContext(seq_id=0, timestamp_ns=123456, state_vector=state_data)
    ctx_b = ExecutionContext(seq_id=0, timestamp_ns=123456, state_vector=state_data)
    
    assert ctx_a.state_hash == ctx_b.state_hash, "Independent instances with identical data produced divergent state hashes!"


def test_strict_type_rejection():
    # Attempt to pass an unsupported type into state_vector (e.g. set) to trigger strict serialization failure
    with pytest.raises(TypeError, match="Non-serializable type in state_vector"):
        ExecutionContext(
            seq_id=0,
            timestamp_ns=1000,
            state_vector={"invalid_set": {1, 2, 3}}
        )


def test_history_window_bounded_limit():
    ctx = ExecutionContext(seq_id=0, timestamp_ns=100)
    # Derive 20 sequential contexts with max_history_len=5
    curr = ctx
    for i in range(1, 21):
        curr = curr.derive_next(next_seq_id=i, next_timestamp_ns=100 + i * 10, state_delta={"step": i}, max_history_len=5)
    
    assert len(curr.history_window) == 5, f"Expected history window bounded to 5, got {len(curr.history_window)}"
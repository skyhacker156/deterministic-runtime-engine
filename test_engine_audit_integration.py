"""
Integration Tests - Engine Audit Emission
(test_engine_audit_integration.py)

Verifies that DeterministicExecutionEngine correctly emits ExecutionAuditRecord
entries as an observational side effect of process_frame, without altering
existing execution, sequencing, or fault behavior.
"""

import hashlib
import struct
import numpy as np
import pytest

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelState
from execution_module_contract import ExecutionResult
from deterministic_execution_engine import DeterministicExecutionEngine, ExecutionEngineError


def create_frame(seq_id: int, timestamp_ns: int = 1_000_000, seed_val: float = 1.0) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    hasher = hashlib.sha256()
    hasher.update(struct.pack(">QQ", seq_id, timestamp_ns))
    hasher.update(payload.tobytes())
    provenance_hash = hasher.digest()
    return CoreExecutionFrame(
        seq_id=seq_id, timestamp_ns=timestamp_ns, payload=payload, provenance_hash=provenance_hash,
    )


class IdentityModule:
    @property
    def module_id(self) -> str:
        return "identity_v1"

    def execute(self, frame, state) -> ExecutionResult:
        return ExecutionResult(
            seq_id=frame.seq_id,
            success=True,
            output_payload=frame.payload * 2.0,
            metrics={"scale": 2.0},
        )


class FailingModule:
    @property
    def module_id(self) -> str:
        return "failing_v1"

    def execute(self, frame, state) -> ExecutionResult:
        return ExecutionResult(
            seq_id=frame.seq_id,
            success=False,
            output_payload=frame.payload,
            error_message="Simulated failure for audit test.",
        )


def test_audit_log_empty_before_any_frames():
    engine = DeterministicExecutionEngine(module=IdentityModule())
    engine.initialize()
    assert engine.audit_log == ()


def test_audit_record_emitted_on_successful_frame():
    engine = DeterministicExecutionEngine(module=IdentityModule())
    engine.initialize()

    frame = create_frame(seq_id=0)
    envelope, result = engine.process_frame(frame)

    assert len(engine.audit_log) == 1
    record = engine.audit_log[0]

    assert record.sequence_id == 0
    assert record.input_hash == frame.provenance_hash
    assert record.output_hash == result.module_hash
    assert record.module_id == "identity_v1"
    assert record.success is True
    assert record.frame_timestamp_ns == frame.timestamp_ns
    assert record.error_message is None


def test_audit_log_accumulates_across_multiple_frames():
    engine = DeterministicExecutionEngine(module=IdentityModule())
    engine.initialize()

    for i in range(5):
        engine.process_frame(create_frame(seq_id=i, timestamp_ns=1_000_000 + i))

    assert len(engine.audit_log) == 5
    assert [r.sequence_id for r in engine.audit_log] == [0, 1, 2, 3, 4]


def test_audit_record_chains_to_prior_state_hash():
    """Each record's prior_state_hash must equal the kernel's envelope hash
    captured immediately before that frame was processed."""
    engine = DeterministicExecutionEngine(module=IdentityModule())
    initial_envelope = engine.initialize()

    frame0 = create_frame(seq_id=0)
    env0, _ = engine.process_frame(frame0)

    frame1 = create_frame(seq_id=1, timestamp_ns=2_000_000)
    env1, _ = engine.process_frame(frame1)

    assert engine.audit_log[0].prior_state_hash == initial_envelope.state_hash
    assert engine.audit_log[1].prior_state_hash == env0.state_hash


def test_audit_record_captures_module_failure_before_raising():
    """Even though a failed module trips ExecutionEngineError, the audit
    record for that frame must still exist and reflect the failure."""
    engine = DeterministicExecutionEngine(module=FailingModule())
    engine.initialize()

    frame = create_frame(seq_id=0)
    with pytest.raises(ExecutionEngineError):
        engine.process_frame(frame)

    assert len(engine.audit_log) == 1
    record = engine.audit_log[0]
    assert record.success is False
    assert record.error_message == "Simulated failure for audit test."


def test_no_audit_record_without_registered_module():
    engine = DeterministicExecutionEngine(module=None)
    engine.initialize()

    engine.process_frame(create_frame(seq_id=0))
    assert engine.audit_log == ()


def test_audit_log_replay_determinism():
    """Two independent engines processing identical frames must produce
    identical audit_hash sequences."""
    def run():
        engine = DeterministicExecutionEngine(module=IdentityModule())
        engine.initialize()
        for i in range(3):
            engine.process_frame(create_frame(seq_id=i, timestamp_ns=1_000_000 + i, seed_val=float(i)))
        return [r.audit_hash for r in engine.audit_log]

    hashes_1 = run()
    hashes_2 = run()
    assert hashes_1 == hashes_2
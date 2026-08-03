"""
Unit Test Suite for Execution Interface & Module Dispatch (test_execution_interface.py)
"""

import hashlib
import struct
import numpy as np
import pytest

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelState
from execution_module_contract import ExecutionResult
from deterministic_execution_engine import (
    DeterministicExecutionEngine,
    ExecutionEngineError,
)


def create_dummy_frame(seq_id: int, timestamp_ns: int = 1_000_000, seed_val: float = 1.0) -> CoreExecutionFrame:
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


class IdentityTransformModule:
    """Concrete execution module scaling vector payload."""

    @property
    def module_id(self) -> str:
        return "identity_transform_v1"

    def execute(self, frame: CoreExecutionFrame, state) -> ExecutionResult:
        transformed_payload = frame.payload * 2.0
        mean_val = float(np.mean(transformed_payload))

        return ExecutionResult(
            seq_id=frame.seq_id,
            success=True,
            output_payload=transformed_payload,
            metrics={"mean_val": mean_val, "scale_factor": 2.0},
        )


class FaultyModule:
    """Module implementation that intentionally fails on seq_id == 2."""

    @property
    def module_id(self) -> str:
        return "faulty_test_module"

    def execute(self, frame: CoreExecutionFrame, state) -> ExecutionResult:
        if frame.seq_id == 2:
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=frame.payload,
                error_message="Simulated domain arithmetic overflow.",
            )

        return ExecutionResult(
            seq_id=frame.seq_id,
            success=True,
            output_payload=frame.payload,
        )


def test_engine_dispatches_to_registered_module():
    module = IdentityTransformModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()

    frame = create_dummy_frame(seq_id=0, seed_val=2.5)
    envelope, result = engine.process_frame(frame)

    assert envelope.state == KernelState.READY
    assert result is not None
    assert result.seq_id == 0
    assert result.success is True
    assert result.output_payload[0] == 5.0
    assert result.metrics["mean_val"] == 5.0


def test_module_failure_trips_kernel_into_faulted_state():
    module = FaultyModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()

    engine.process_frame(create_dummy_frame(seq_id=0))
    engine.process_frame(create_dummy_frame(seq_id=1))

    with pytest.raises(ExecutionEngineError, match="Module execution failed on seq_id 2"):
        engine.process_frame(create_dummy_frame(seq_id=2))

    assert engine.state_machine.current_state == KernelState.FAULTED
    assert "Simulated domain arithmetic overflow" in engine.state_machine.get_envelope().active_fault_reason


def test_replay_determinism_with_execution_module():
    def execute_pipeline():
        mod = IdentityTransformModule()
        eng = DeterministicExecutionEngine(module=mod)
        eng.initialize()
        
        env0, res0 = eng.process_frame(create_dummy_frame(seq_id=0, seed_val=1.2))
        env1, res1 = eng.process_frame(create_dummy_frame(seq_id=1, seed_val=3.4))
        
        return env1.state_hash, res0.module_hash, res1.module_hash

    state_hash_1, mod_hash0_1, mod_hash1_1 = execute_pipeline()
    state_hash_2, mod_hash0_2, mod_hash1_2 = execute_pipeline()

    assert state_hash_1 == state_hash_2
    assert mod_hash0_1 == mod_hash0_2
    assert mod_hash1_1 == mod_hash1_2
"""
Unit & Fuzz Test Suite for Phoenix A / ACE Execution Module
(test_phoenix_a_module.py)
"""

import hashlib
import struct
import uuid
import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelState, KernelStateEnvelope
from execution_module_contract import ExecutionResult
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule


def create_dummy_frame(seq_id: int, seed_val: float = 1.0) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    timestamp_ns = 1_000_000_000 + seq_id
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


# Fixed placeholder generation_id for the standalone dummy envelopes built
# directly in this file below. Each test using it builds exactly ONE
# envelope and uses it once -- none of them compare across independent
# DeterministicExecutionEngine instances, so a fixed constant is safe
# here. See test_phoenix_a_module_replay_determinism below for the one
# test in this file that DOES span two independent instances, which uses
# a separately-generated shared generation_id instead of this constant.
_DUMMY_ENVELOPE_GENERATION_ID = b"\xEE" * 16


def test_phoenix_a_module_direct_execution():
    module = PhoenixAExecutionModule()
    assert module.module_id == "phoenix_a_core_v1"

    frame = create_dummy_frame(seq_id=0, seed_val=2.5)
    dummy_envelope = KernelStateEnvelope(
        state=KernelState.PROCESSING,
        last_processed_seq=-1,
        total_frames_processed=0,
        state_hash=b"\x01" * 32,
        fault_reason=None,
        generation_id=_DUMMY_ENVELOPE_GENERATION_ID,
    )

    result = module.execute(frame, dummy_envelope)

    assert result.success is True
    assert result.seq_id == 0
    assert result.output_payload.shape == (256,)
    assert "signal_energy" in result.metrics
    assert "execution_latency_us" in result.metrics
    assert "envelope_state_fingerprint" in result.metrics


def test_phoenix_a_module_near_zero_norm_guard():
    """Verify subnormal / tiny values near zero are handled safely without overflow/NaN."""
    module = PhoenixAExecutionModule()
    dummy_envelope = KernelStateEnvelope(
        state=KernelState.PROCESSING,
        last_processed_seq=-1,
        total_frames_processed=0,
        state_hash=b"\x02" * 32,
        fault_reason=None,
        generation_id=_DUMMY_ENVELOPE_GENERATION_ID,
    )

    # Subnormal payload (1e-300) where naive division would blow up
    tiny_payload = np.full(256, fill_value=1e-300, dtype=np.float64)
    frame = CoreExecutionFrame(
        seq_id=0,
        timestamp_ns=1_000_000,
        payload=tiny_payload,
        provenance_hash=b"\x00" * 32
    )

    result = module.execute(frame, dummy_envelope)

    assert result.success is True
    assert np.all(np.isfinite(result.output_payload))


def test_execution_result_central_finiteness_enforcement():
    """Verify ExecutionResult __post_init__ rejects non-finite (NaN / Inf) output payloads."""
    nan_payload = np.full(256, fill_value=np.nan, dtype=np.float64)
    inf_payload = np.full(256, fill_value=np.inf, dtype=np.float64)

    with pytest.raises(ValueError, match="contains non-finite values"):
        ExecutionResult(seq_id=0, success=True, output_payload=nan_payload)

    with pytest.raises(ValueError, match="contains non-finite values"):
        ExecutionResult(seq_id=0, success=True, output_payload=inf_payload)


# --- Property-Based Fuzz Testing ---

st_float_payload = st.lists(
    st.floats(
        allow_nan=False,
        allow_infinity=False,
        min_value=-1e150,
        max_value=1e150
    ),
    min_size=256,
    max_size=256
).map(lambda lst: np.array(lst, dtype=np.float64))


@settings(deadline=500)
@given(payload=st_float_payload, seq_id=st.integers(min_value=0, max_value=10_000))
def test_fuzz_phoenix_a_module_numerical_stability(payload: np.ndarray, seq_id: int):
    """
    Fuzz PhoenixAExecutionModule with extreme floating-point variations:
    Asserts:
    1. execute() NEVER raises an unhandled exception.
    2. Output payload is guaranteed finite (no NaN, no Inf).
    3. Output payload retains valid (256,) shape and float64 dtype.
    """
    module = PhoenixAExecutionModule()
    dummy_envelope = KernelStateEnvelope(
        state=KernelState.PROCESSING,
        last_processed_seq=seq_id - 1,
        total_frames_processed=seq_id,
        state_hash=hashlib.sha256(struct.pack(">Q", seq_id)).digest(),
        fault_reason=None,
        generation_id=_DUMMY_ENVELOPE_GENERATION_ID,
    )
    frame = CoreExecutionFrame(
        seq_id=seq_id,
        timestamp_ns=1_000_000,
        payload=payload,
        provenance_hash=b"\x00" * 32
    )

    result = module.execute(frame, dummy_envelope)

    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.output_payload.shape == (256,)
    assert result.output_payload.dtype == np.float64
    assert np.all(np.isfinite(result.output_payload))


def test_phoenix_a_module_integration_with_engine():
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()

    frame0 = create_dummy_frame(seq_id=0, seed_val=1.0)
    envelope0, res0 = engine.process_frame(frame0)

    assert envelope0.state == KernelState.READY
    assert envelope0.last_processed_seq == 0
    assert res0 is not None
    assert res0.success is True
    assert len(res0.module_hash) == 32


def test_phoenix_a_module_replay_determinism():
    """
    generation_id is held fixed across both run_pipeline() calls below --
    two ordinary DeterministicExecutionEngine() instances are, by design,
    two different kernel generations, so comparing module_hash across
    them would be comparing two different lifetimes rather than proving
    determinism given the same one. See
    DeterministicExecutionEngine.with_generation()'s own docstring.
    """
    shared_generation_id = uuid.uuid4().bytes

    def run_pipeline():
        mod = PhoenixAExecutionModule()
        eng = DeterministicExecutionEngine.with_generation(
            generation_id=shared_generation_id, module=mod
        )
        eng.initialize()

        _, res0 = eng.process_frame(create_dummy_frame(seq_id=0, seed_val=0.5))
        _, res1 = eng.process_frame(create_dummy_frame(seq_id=1, seed_val=1.5))

        return res0.module_hash, res1.module_hash

    run1_h0, run1_h1 = run_pipeline()
    run2_h0, run2_h1 = run_pipeline()

    assert run1_h0 == run2_h0
    assert run1_h1 == run2_h1

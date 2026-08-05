"""
End-to-End Pipeline Integration Test
(test_end_to_end_pipeline.py)

Validates the complete closed-loop pipeline across all verified contract boundaries:
RawVentTelemetryPacket -> VentAdapterContract -> BridgeIntegrator -> [Seam Converter]
                       -> DeterministicOrderingBarrier -> DeterministicExecutionEngine
                       -> PhoenixAExecutionModule -> ExecutionResult
"""

import time
import hashlib
import struct
import uuid
import numpy as np
import pytest

from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket
from bridge_integrator_contract import BridgeIntegrator
from ordering_barrier import DeterministicOrderingBarrier
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule
from execution_module_contract import ExecutionResult
from execution_kernel_contract import CoreExecutionFrame as KernelCoreExecutionFrame


def transform_bridge_frame_to_kernel_frame(bridge_frame, seq_id: int) -> KernelCoreExecutionFrame:
    """
    Explicit seam adapter bridging domain frames to runtime kernel frames.
    Computes the canonical kernel provenance hash over final structured fields 
    (seq_id, timestamp_ns, payload bytes) to satisfy verify_integrity().
    """
    # 1. Construct the contiguous 256-element payload
    combined_payload = np.concatenate([
        np.array(bridge_frame.temp_slice, dtype=np.float64),
        np.array(bridge_frame.seismic_slice, dtype=np.float64),
        np.array(bridge_frame.ph_slice, dtype=np.float64),
    ]).astype(np.float64)

    assert combined_payload.shape == (256,), f"Expected payload shape (256,), got {combined_payload.shape}"

    # 2. Establish canonical kernel timestamp in nanoseconds
    timestamp_ns = int(bridge_frame.timestamp * 1e9)

    # 3. Compute canonical kernel provenance hash matching CoreExecutionFrame.verify_integrity()
    header_bytes = struct.pack(">QQ", seq_id, timestamp_ns)
    payload_bytes = combined_payload.tobytes()
    canonical_hash = hashlib.sha256(header_bytes + payload_bytes).digest()

    # 4. Construct Kernel-compliant CoreExecutionFrame with matching integrity hash
    return KernelCoreExecutionFrame(
        seq_id=seq_id,
        timestamp_ns=timestamp_ns,
        provenance_hash=canonical_hash,
        payload=combined_payload,
    )


def test_end_to_end_pipeline_scrambled_ingestion_to_verified_execution():
    adapter = VentAdapterContract()
    bridge = BridgeIntegrator()
    barrier = DeterministicOrderingBarrier(max_window_size=16)
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()  # Initialize the engine state machine from UNINITIALIZED

    # 1. Generate 5 Raw Telemetry Packets with required timestamp
    base_time = 1700000000.0
    np.random.seed(42)
    raw_packets = []
    for seq_id in range(5):
        raw_packets.append(
            RawVentTelemetryPacket(
                batch_id=f"BATCH_{seq_id:04d}",
                timestamp=base_time + (seq_id * 0.01),
                temperature_readings=np.random.uniform(200.0, 400.0, size=85).tolist(),
                seismic_amplitude=np.random.uniform(0.0, 5.0, size=85).tolist(),
                chemical_pH=np.random.uniform(2.0, 8.0, size=86).tolist(),
            )
        )

    # 2. Intentionally Scramble Arrival Order: [Seq 2, Seq 0, Seq 4, Seq 1, Seq 3]
    scrambled_indices = [2, 0, 4, 1, 3]
    scrambled_packets = [(idx, raw_packets[idx]) for idx in scrambled_indices]

    resequenced_frames = []
    for seq_id, pkt in scrambled_packets:
        sanitized_batch, log_record = adapter.process_raw_packet(pkt)
        assert sanitized_batch is not None, f"Adapter rejected valid packet: {log_record}"

        bridge_frame = bridge.verify_and_transform(sanitized_batch)
        kernel_frame = transform_bridge_frame_to_kernel_frame(bridge_frame, seq_id=seq_id)

        ready_frames = barrier.push(kernel_frame)
        resequenced_frames.extend(ready_frames)

    # 3. Verify Barrier Resequenced Frames in Monotonic Order (0, 1, 2, 3, 4)
    assert len(resequenced_frames) == 5, f"Expected 5 resequenced frames, got {len(resequenced_frames)}"
    for expected_seq, frame in enumerate(resequenced_frames):
        assert frame.seq_id == expected_seq, (
            f"Sequence order mismatch: expected {expected_seq}, got {frame.seq_id}"
        )

    # 4. Process Resequenced Frames in Execution Engine
    execution_results = []
    for frame in resequenced_frames:
        envelope, result = engine.process_frame(frame)
        execution_results.append(result)

    # 5. Verify E2E Invariants
    assert engine.state_machine.current_state.name == "READY"
    assert engine.state_machine.total_frames_processed == 5

    for seq_id, result in enumerate(execution_results):
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.seq_id == seq_id
        assert result.output_payload.shape == (256,)
        assert np.isfinite(result.output_payload).all()
        assert len(result.module_hash) == 32


def test_end_to_end_replay_determinism():
    """
    Verify end-to-end replay determinism from scrambled raw packets down to
    execution hashes.

    generation_id is held fixed across both run_pipeline() calls below --
    two ordinary DeterministicExecutionEngine() instances are, by design,
    two different kernel generations, so comparing module hashes across
    them would be comparing two different lifetimes rather than proving
    determinism given the same one. See
    DeterministicExecutionEngine.with_generation()'s own docstring.
    """
    shared_generation_id = uuid.uuid4().bytes

    def run_pipeline():
        adapter = VentAdapterContract()
        bridge = BridgeIntegrator()
        barrier = DeterministicOrderingBarrier(max_window_size=16)
        engine = DeterministicExecutionEngine.with_generation(
            generation_id=shared_generation_id, module=PhoenixAExecutionModule()
        )
        engine.initialize()  # Initialize the engine state machine from UNINITIALIZED

        base_time = 1700000000.0
        np.random.seed(12345)
        raw_packets = [
            (
                i,
                RawVentTelemetryPacket(
                    batch_id=f"BATCH_{i:04d}",
                    timestamp=base_time + (i * 0.01),
                    temperature_readings=np.random.uniform(200.0, 400.0, size=85).tolist(),
                    seismic_amplitude=np.random.uniform(0.0, 5.0, size=85).tolist(),
                    chemical_pH=np.random.uniform(2.0, 8.0, size=86).tolist(),
                ),
            )
            for i in range(4)
        ]

        # Scramble arrival order: [3, 1, 0, 2]
        drained_frames = []
        for seq_id, pkt in [raw_packets[3], raw_packets[1], raw_packets[0], raw_packets[2]]:
            batch, _ = adapter.process_raw_packet(pkt)
            b_frame = bridge.verify_and_transform(batch)
            k_frame = transform_bridge_frame_to_kernel_frame(b_frame, seq_id=seq_id)
            drained_frames.extend(barrier.push(k_frame))

        results = []
        for frame in drained_frames:
            _, res = engine.process_frame(frame)
            results.append(res)

        return (
            [res.module_hash for res in results],
            engine.state_machine.last_processed_seq,
        )

    hashes_1, seq_1 = run_pipeline()
    hashes_2, seq_2 = run_pipeline()

    assert hashes_1 == hashes_2, "E2E Execution result module hash mismatch between runs!"
    assert seq_1 == seq_2 == 3, "E2E Last processed sequence mismatch between runs!"

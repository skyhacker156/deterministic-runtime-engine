"""
replay_engine.py - Streamer & Replay Harness using AdapterLogRecord

Step 3 addition: full pipeline replay through the kernel engine, capturing
and verifying the ExecutionAuditRecord chain across independent passes.
This extends the existing "can I reproduce the output?" guarantee into
"can I reproduce the entire causal chain?" — the audit_hash sequence, not
just the final tensors.

This is purely additive: execute_replay_pass (bridge-level replay) is
unchanged. The new execute_full_pipeline_replay and verify methods are a
separate, higher path that goes all the way through the kernel engine.
"""

import os
import struct
import hashlib
from dataclasses import dataclass
from typing import List, Generator, Tuple

from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket, SanitizedEngineBatch, AdapterLogRecord
from bridge_integrator_contract import BridgeIntegrator, CoreExecutionFrame as BridgeExecutionFrame

from execution_kernel_contract import CoreExecutionFrame as KernelExecutionFrame
from deterministic_execution_engine import DeterministicExecutionEngine
from execution_audit_contract import ExecutionAuditRecord

MAGIC_HEADER = b"VENTLOG1"


@dataclass(frozen=True)
class StreamExecutionSummary:
    total_frames: int
    first_hash: str
    last_hash: str
    cumulative_stream_hash: str


@dataclass(frozen=True)
class FullPipelineReplaySummary:
    """
    Summary of a complete replay pass through adapter -> bridge -> kernel engine.
    Distinct from StreamExecutionSummary, which only covers the bridge-level replay.

    Note: final_kernel_state_hash is a structural/positional fingerprint of the
    kernel (sequence position, frame count, kernel state) — NOT a content hash.
    Two runs of equal length ending in the same kernel state will always match
    on this field, even with completely different frame content. Content
    sensitivity lives in audit_hashes, which incorporates each frame's actual
    input/output hashes.
    """
    total_frames_processed: int
    audit_hashes: Tuple[bytes, ...]
    final_kernel_state_hash: bytes


class BinaryTelemetryLogWriter:

    @staticmethod
    def serialize_packet(packet: RawVentTelemetryPacket) -> bytes:
        temps_str = ",".join(f"{x:.10f}" for x in packet.temperature_readings)
        seismic_str = ",".join(f"{x:.10f}" for x in packet.seismic_amplitude)
        ph_str = ",".join(f"{x:.10f}" for x in packet.chemical_pH)

        payload_str = f"{packet.batch_id}|{packet.timestamp:.8f}|{temps_str}|{seismic_str}|{ph_str}"
        payload_bytes = payload_str.encode('utf-8')

        length_prefix = struct.pack('>I', len(payload_bytes))
        return length_prefix + payload_bytes

    @classmethod
    def write_dataset_to_file(cls, filepath: str, packets: List[RawVentTelemetryPacket]) -> int:
        with open(filepath, 'wb') as f:
            f.write(MAGIC_HEADER)
            bytes_written = len(MAGIC_HEADER)
            for pkt in packets:
                data = cls.serialize_packet(pkt)
                f.write(data)
                bytes_written += len(data)
        return bytes_written


class BinaryTelemetryLogReader:

    @staticmethod
    def parse_packet(payload_bytes: bytes) -> RawVentTelemetryPacket:
        payload_str = payload_bytes.decode('utf-8')
        parts = payload_str.split('|')

        batch_id = parts[0]
        timestamp = float(parts[1])
        temps = [float(x) for x in parts[2].split(',')] if parts[2] else []
        seismic = [float(x) for x in parts[3].split(',')] if parts[3] else []
        ph = [float(x) for x in parts[4].split(',')] if parts[4] else []

        return RawVentTelemetryPacket(
            batch_id=batch_id,
            timestamp=timestamp,
            temperature_readings=temps,
            seismic_amplitude=seismic,
            chemical_pH=ph
        )

    @classmethod
    def stream_dataset(cls, filepath: str) -> Generator[RawVentTelemetryPacket, None, None]:
        with open(filepath, 'rb') as f:
            header = f.read(len(MAGIC_HEADER))
            if header != MAGIC_HEADER:
                raise ValueError(f"Invalid dataset magic header! Expected {MAGIC_HEADER}, got {header}")

            while True:
                length_bytes = f.read(4)
                if not length_bytes or len(length_bytes) < 4:
                    break

                payload_len = struct.unpack('>I', length_bytes)[0]
                payload_bytes = f.read(payload_len)
                if len(payload_bytes) < payload_len:
                    raise IOError("Truncated log entry encountered during replay streaming.")

                yield cls.parse_packet(payload_bytes)


def _bridge_frame_to_kernel_frame(bridge_frame: BridgeExecutionFrame, seq_id: int) -> KernelExecutionFrame:
    """
    Seam conversion: BridgeIntegrator's three-slice CoreExecutionFrame ->
    the kernel's single 256-payload CoreExecutionFrame.

    Concatenates ph_slice + seismic_slice + temp_slice into one array,
    padded/truncated to exactly 256 elements, and recomputes provenance
    using the kernel's own binary hash scheme (struct.pack(">QQ", ...)),
    matching the seam already proven in the end-to-end pipeline tests.
    """
    import numpy as np

    combined = list(bridge_frame.ph_slice) + list(bridge_frame.seismic_slice) + list(bridge_frame.temp_slice)
    payload = np.zeros(256, dtype=np.float64)
    limit = min(len(combined), 256)
    payload[:limit] = combined[:limit]

    timestamp_ns = int(bridge_frame.timestamp * 1_000_000_000)

    hasher = hashlib.sha256()
    hasher.update(struct.pack(">QQ", seq_id, timestamp_ns))
    hasher.update(payload.tobytes())
    provenance_hash = hasher.digest()

    return KernelExecutionFrame(
        seq_id=seq_id,
        timestamp_ns=timestamp_ns,
        payload=payload,
        provenance_hash=provenance_hash,
    )


class ReplayEngine:

    @staticmethod
    def generate_synthetic_dataset(num_records: int = 100, seed: int = 42) -> List[RawVentTelemetryPacket]:
        state = seed
        def next_float(min_val: float, max_val: float) -> float:
            nonlocal state
            state = (state * 1103515245 + 12345) & 0x7fffffff
            ratio = state / 2147483647.0
            return min_val + ratio * (max_val - min_val)

        packets = []
        base_time = 1700000000.0

        for i in range(num_records):
            batch_id = f"REPLAY-{i:06d}"
            timestamp = base_time + (i * 0.1)

            t_base = next_float(100.0, 300.0)
            temps = [t_base + (j * next_float(0.5, 2.0)) for j in range(10)]

            s_base = next_float(1.0, 20.0)
            seismic = [s_base + (j * next_float(0.1, 1.0)) for j in range(10)]

            ph_base = next_float(5.0, 9.0)
            ph = [ph_base + (j * next_float(0.05, 0.3)) for j in range(10)]

            packets.append(RawVentTelemetryPacket(
                batch_id=batch_id,
                timestamp=timestamp,
                temperature_readings=temps,
                seismic_amplitude=seismic,
                chemical_pH=ph
            ))

        return packets

    @classmethod
    def execute_replay_pass(cls, dataset_path: str) -> Tuple[StreamExecutionSummary, List[BridgeExecutionFrame]]:
        """
        Existing bridge-level replay pass. Unchanged from prior behavior:
        answers "can I reproduce the output?" up through BridgeIntegrator.
        """
        adapter = VentAdapterContract()
        cumulative_hasher = hashlib.sha256()
        execution_frames: List[BridgeExecutionFrame] = []

        first_hash = ""
        last_hash = ""
        frame_count = 0

        for packet in BinaryTelemetryLogReader.stream_dataset(dataset_path):
            batch, log_record = adapter.process_raw_packet(packet)

            if not log_record.qa_passed or batch is None:
                raise RuntimeError(f"Replay ingestion failed at packet {packet.batch_id}: {log_record.error_message}")

            frame = BridgeIntegrator.verify_and_transform(batch)
            execution_frames.append(frame)

            cumulative_hasher.update(frame.provenance_hash.encode('utf-8'))

            if frame_count == 0:
                first_hash = frame.provenance_hash
            last_hash = frame.provenance_hash
            frame_count += 1

        summary = StreamExecutionSummary(
            total_frames=frame_count,
            first_hash=first_hash,
            last_hash=last_hash,
            cumulative_stream_hash=cumulative_hasher.hexdigest()
        )
        return summary, execution_frames

    @classmethod
    def execute_full_pipeline_replay(cls, dataset_path: str, module) -> FullPipelineReplaySummary:
        """
        Step 3: full pipeline replay through adapter -> bridge -> seam
        conversion -> DeterministicExecutionEngine, capturing the complete
        audit_log for this pass.

        `module` must be a fresh ExecutionModule instance (e.g.
        PhoenixAExecutionModule()) supplied by the caller, so each call
        gets an independent engine and log rather than sharing state.
        """
        adapter = VentAdapterContract()
        engine = DeterministicExecutionEngine(module=module)
        engine.initialize()

        seq_id = 0
        for packet in BinaryTelemetryLogReader.stream_dataset(dataset_path):
            batch, log_record = adapter.process_raw_packet(packet)

            if not log_record.qa_passed or batch is None:
                raise RuntimeError(f"Replay ingestion failed at packet {packet.batch_id}: {log_record.error_message}")

            bridge_frame = BridgeIntegrator.verify_and_transform(batch)
            kernel_frame = _bridge_frame_to_kernel_frame(bridge_frame, seq_id=seq_id)

            envelope, _ = engine.process_frame(kernel_frame)
            seq_id += 1

        return FullPipelineReplaySummary(
            total_frames_processed=len(engine.audit_log),
            audit_hashes=tuple(r.audit_hash for r in engine.audit_log),
            final_kernel_state_hash=engine.state_machine.get_envelope().state_hash,
        )

    @classmethod
    def verify_causal_chain_determinism(cls, dataset_path: str, module_factory) -> bool:
        """
        Runs execute_full_pipeline_replay twice, using module_factory() to
        construct a fresh module instance each time, and confirms the entire
        audit_hash chain — not just the final output — is bit-identical
        across both independent passes.

        module_factory: a zero-arg callable returning a fresh ExecutionModule
        instance, e.g. `lambda: PhoenixAExecutionModule()`.
        """
        summary_1 = cls.execute_full_pipeline_replay(dataset_path, module_factory())
        summary_2 = cls.execute_full_pipeline_replay(dataset_path, module_factory())

        if summary_1.total_frames_processed != summary_2.total_frames_processed:
            return False
        if summary_1.audit_hashes != summary_2.audit_hashes:
            return False
        if summary_1.final_kernel_state_hash != summary_2.final_kernel_state_hash:
            return False
        return True
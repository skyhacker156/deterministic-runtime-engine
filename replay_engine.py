"""
replay_engine.py - Streamer & Replay Harness using AdapterLogRecord
"""

import os
import struct
import hashlib
from dataclasses import dataclass
from typing import List, Generator, Tuple

from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket, SanitizedEngineBatch, AdapterLogRecord
from bridge_integrator_contract import BridgeIntegrator, CoreExecutionFrame

MAGIC_HEADER = b"VENTLOG1"


@dataclass(frozen=True)
class StreamExecutionSummary:
    total_frames: int
    first_hash: str
    last_hash: str
    cumulative_stream_hash: str


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
    def execute_replay_pass(cls, dataset_path: str) -> Tuple[StreamExecutionSummary, List[CoreExecutionFrame]]:
        adapter = VentAdapterContract()
        cumulative_hasher = hashlib.sha256()
        execution_frames: List[CoreExecutionFrame] = []

        first_hash = ""
        last_hash = ""
        frame_count = 0

        for packet in BinaryTelemetryLogReader.stream_dataset(dataset_path):
            batch, log_record = adapter.process_raw_packet(packet)
            
            # Robust QA check against AdapterLogRecord
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
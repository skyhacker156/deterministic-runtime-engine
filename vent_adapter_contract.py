"""
vent_adapter_contract.py - Surface Telemetry Ingestion Contract
Classification: Surface Layer
"""

import math
import hashlib
import struct
from dataclasses import dataclass
from typing import List, Tuple, Optional

EXPECTED_TENSOR_DIM = 256


@dataclass(frozen=True)
class RawVentTelemetryPacket:
    batch_id: str
    timestamp: float
    temperature_readings: List[float]
    seismic_amplitude: List[float]
    chemical_pH: List[float]


@dataclass(frozen=True)
class SanitizedEngineBatch:
    """Canonical Data Transfer Object shared across surface and bridge layers."""
    batch_id: str
    timestamp: float
    data_tensor: Tuple[float, ...]
    provenance_hash: str


@dataclass(frozen=True)
class AdapterLogRecord:
    """Structured operational audit record emitted on every packet ingestion attempt."""
    batch_id: str
    qa_passed: bool
    data_points_processed: int
    error_message: Optional[str] = None


class StratifiedTensorPacker:
    """Downsamples and normalizes incoming channels into a fixed 256-dim tensor."""

    @staticmethod
    def pack_channels_stratified(channels: dict, target_dim: int = EXPECTED_TENSOR_DIM) -> Tuple[float, ...]:
        num_channels = len(channels)
        if num_channels > target_dim or num_channels == 0:
            raise ValueError(f"Number of channels ({num_channels}) exceeds target tensor dimension ({target_dim}).")

        quota = target_dim // num_channels
        remainder = target_dim % num_channels
        packed_tensor = []

        sorted_keys = sorted(channels.keys())
        for idx, key in enumerate(sorted_keys):
            channel_data = channels[key]
            allocated_size = quota + (1 if idx < remainder else 0)

            if not channel_data:
                packed_tensor.extend([0.0] * allocated_size)
                continue

            n = len(channel_data)
            for i in range(allocated_size):
                src_idx = int(i * (n / allocated_size))
                raw_val = channel_data[min(src_idx, n - 1)]

                if not math.isfinite(raw_val):
                    raw_val = 0.0

                scaled_diff = -0.01 * (raw_val - 200.0)
                clamped_arg = max(-700.0, min(700.0, scaled_diff))
                normalized_val = 1.0 / (1.0 + math.exp(clamped_arg))
                packed_tensor.append(normalized_val)

        return tuple(packed_tensor)


class VentAdapterContract:
    """Surface Layer Contract emitting SanitizedEngineBatch and AdapterLogRecord."""

    @staticmethod
    def compute_canonical_hash(batch_id: str, timestamp: float, tensor: Tuple[float, ...]) -> str:
        hasher = hashlib.sha256()
        hasher.update(batch_id.encode('utf-8'))
        hasher.update(struct.pack('>d', timestamp))
        for val in tensor:
            hasher.update(struct.pack('>d', val))
        return hasher.hexdigest()

    def process_raw_packet(self, packet: RawVentTelemetryPacket) -> Tuple[Optional[SanitizedEngineBatch], AdapterLogRecord]:
        channels = {
            "chemical_pH": packet.chemical_pH,
            "seismic_amplitude": packet.seismic_amplitude,
            "temperature_readings": packet.temperature_readings
        }

        total_points = len(packet.chemical_pH) + len(packet.seismic_amplitude) + len(packet.temperature_readings)

        try:
            tensor = StratifiedTensorPacker.pack_channels_stratified(channels, EXPECTED_TENSOR_DIM)
            prov_hash = self.compute_canonical_hash(packet.batch_id, packet.timestamp, tensor)

            batch = SanitizedEngineBatch(
                batch_id=packet.batch_id,
                timestamp=packet.timestamp,
                data_tensor=tensor,
                provenance_hash=prov_hash
            )
            log = AdapterLogRecord(
                batch_id=packet.batch_id,
                qa_passed=True,
                data_points_processed=total_points
            )
            return batch, log
        except Exception as e:
            log = AdapterLogRecord(
                batch_id=packet.batch_id,
                qa_passed=False,
                data_points_processed=total_points,
                error_message=str(e)
            )
            return None, log
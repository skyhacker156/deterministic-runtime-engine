"""
bridge_integrator_contract.py - Core Handshake & Provenance Verification Bridge
Classification: Internal Core Boundary / Pipeline Integrator

Imports canonical SanitizedEngineBatch from surface layer, enforcing
constant-time provenance verification, remainder-aware channel slicing, 
and sensor stagnation checks.
"""

import hmac
import hashlib
import struct
from dataclasses import dataclass
from typing import Tuple

# Single Source of Truth import from surface contract
from vent_adapter_contract import SanitizedEngineBatch, EXPECTED_TENSOR_DIM

MINIMUM_VARIANCE_THRESHOLD = 1e-9


class IntegrityError(Exception):
    """Raised when incoming tensor data fails constant-time provenance hash verification."""
    pass


class SensorStagnationFault(Exception):
    """Raised when incoming tensor exhibits zero or sub-threshold variance (dead-sensor)."""
    pass


@dataclass(frozen=True)
class CoreExecutionFrame:
    """Verified payload accepted by the Phoenix A execution core."""
    frame_id: str
    timestamp: float
    ph_slice: Tuple[float, ...]
    seismic_slice: Tuple[float, ...]
    temp_slice: Tuple[float, ...]
    provenance_hash: str


class BridgeIntegrator:
    """
    Stateless bridge governing the handshake between VentAdapter and Phoenix A.
    This module performs no domain inference or correction; its sole responsibility
    is enforcing boundary contracts and transforming validated tensors into execution frames.
    """

    CHANNEL_LAYOUT = (
        ("ph", 86),          # 256 // 3 + 1 (remainder allocation)
        ("seismic", 85),     # 256 // 3
        ("temperature", 85)  # 256 // 3
    )

    @staticmethod
    def compute_tensor_hash(batch_id: str, timestamp: float, tensor: Tuple[float, ...]) -> str:
        """Computes canonical SHA-256 matching VentAdapter binary serialization."""
        hasher = hashlib.sha256()
        hasher.update(batch_id.encode('utf-8'))
        hasher.update(struct.pack('>d', timestamp))
        for val in tensor:
            hasher.update(struct.pack('>d', val))
        return hasher.hexdigest()

    @staticmethod
    def calculate_variance(tensor: Tuple[float, ...]) -> float:
        """Computes population variance across the tensor."""
        if not tensor:
            return 0.0
        mean = sum(tensor) / len(tensor)
        return sum((x - mean) ** 2 for x in tensor) / len(tensor)

    @classmethod
    def verify_and_transform(cls, batch: SanitizedEngineBatch) -> CoreExecutionFrame:
        # 1. Enforce Shape Invariant
        if len(batch.data_tensor) != EXPECTED_TENSOR_DIM:
            raise ValueError(
                f"Invalid tensor dimension: expected {EXPECTED_TENSOR_DIM}, got {len(batch.data_tensor)}"
            )

        # 2. Constant-Time Provenance Verification
        recalculated_hash = cls.compute_tensor_hash(
            batch.batch_id, batch.timestamp, batch.data_tensor
        )
        if not hmac.compare_digest(recalculated_hash, batch.provenance_hash):
            raise IntegrityError(
                f"Provenance Hash Mismatch! Recorded: {batch.provenance_hash[:10]}... "
                f"Recalculated: {recalculated_hash[:10]}..."
            )

        # 3. Enforce Signal Variance Guard (Filters flatline and dormant sensor streams)
        var = cls.calculate_variance(batch.data_tensor)
        if var < MINIMUM_VARIANCE_THRESHOLD:
            raise SensorStagnationFault(
                f"Sensor Stagnation Detected! Variance ({var:.12f}) "
                f"is below safety threshold ({MINIMUM_VARIANCE_THRESHOLD})."
            )

        # 4. Remainder-Aware Slicing (Preserves all 256 elements without data drop)
        # Slices: pH [0:86], Seismic [86:171], Temperature [171:256]
        ph_len = cls.CHANNEL_LAYOUT[0][1]
        seismic_len = cls.CHANNEL_LAYOUT[1][1]
        temp_len = cls.CHANNEL_LAYOUT[2][1]

        ph_slice = batch.data_tensor[0 : ph_len]
        seismic_slice = batch.data_tensor[ph_len : ph_len + seismic_len]
        temp_slice = batch.data_tensor[ph_len + seismic_len : ph_len + seismic_len + temp_len]

        return CoreExecutionFrame(
            frame_id=f"FRAME-{batch.batch_id}",
            timestamp=batch.timestamp,
            ph_slice=ph_slice,
            seismic_slice=seismic_slice,
            temp_slice=temp_slice,
            provenance_hash=batch.provenance_hash
        )
"""
Execution Kernel Contract - Sentinel Framework (Phoenix A Execution Core)
Defines the immutable execution frame contract for Phoenix A deterministic execution.
"""

from dataclasses import dataclass
import hashlib
import struct
import numpy as np


@dataclass(frozen=True)
class CoreExecutionFrame:
    """
    Immutable execution input frame.
    """
    seq_id: int
    timestamp_ns: int
    payload: np.ndarray
    provenance_hash: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.payload, np.ndarray):
            object.__setattr__(
                self, "payload", np.asarray(self.payload, dtype=np.float64)
            )

    def calculate_hash(self) -> bytes:
        hasher = hashlib.sha256()
        hasher.update(struct.pack(">QQ", self.seq_id, self.timestamp_ns))
        hasher.update(self.payload.astype(np.float64).tobytes())
        return hasher.digest()

    def verify_integrity(self) -> bool:
        if self.payload is None:
            raise ValueError("Payload missing")
        if self.payload.shape != (256,):
            raise ValueError(
                f"Invalid payload shape. Expected (256,), got {self.payload.shape}"
            )
        if not isinstance(self.provenance_hash, bytes):
            raise ValueError("Invalid provenance hash type")

        expected = self.calculate_hash()
        if expected != self.provenance_hash:
            raise ValueError("Frame provenance hash mismatch")
        return True

    @classmethod
    def create(cls, seq_id: int, payload, timestamp_ns: int = 0):
        payload = np.asarray(payload, dtype=np.float64)
        temp = cls(seq_id=seq_id, timestamp_ns=timestamp_ns, payload=payload, provenance_hash=b"")
        return cls(
            seq_id=seq_id,
            timestamp_ns=timestamp_ns,
            payload=payload,
            provenance_hash=temp.calculate_hash(),
        )
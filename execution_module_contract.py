"""
Execution Module Protocols & Interfaces - Sentinel Framework
(execution_module_contract.py)
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, runtime_checkable
import hashlib
import json
import numpy as np


@dataclass(frozen=True)
class ExecutionResult:
    """
    Immutable, deterministically-hashable output envelope returned by an ExecutionModule.
    """
    seq_id: int
    success: bool
    output_payload: np.ndarray
    metrics: Dict[str, float] = field(default_factory=dict)
    error_message: Optional[str] = None
    module_hash: bytes = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.output_payload, np.ndarray):
            raise TypeError("output_payload must be a numpy ndarray")
        if self.output_payload.shape != (256,):
            raise ValueError(f"output_payload shape must be (256,), got {self.output_payload.shape}")
        if self.output_payload.dtype != np.float64:
            raise TypeError(f"output_payload dtype must be float64, got {self.output_payload.dtype}")
        if not np.all(np.isfinite(self.output_payload)):
            raise ValueError("output_payload contains non-finite values (NaN or Inf)")

        if not self.success:
            if not self.error_message or not self.error_message.strip():
                raise ValueError("error_message must be provided when success is False")
        else:
            if self.error_message is not None:
                raise ValueError("error_message must be None when success is True")

        hasher = hashlib.sha256()
        hasher.update(self.seq_id.to_bytes(8, byteorder="big", signed=True))
        hasher.update(b"\x01" if self.success else b"\x00")
        hasher.update(self.output_payload.tobytes())

        deterministic_metrics = {
            k: v for k, v in self.metrics.items()
            if not k.endswith("_latency_us") and not k.startswith("telemetry_")
        }
        sorted_metrics = sorted(deterministic_metrics.items(), key=lambda kv: kv[0])
        metrics_json = json.dumps(sorted_metrics, separators=(",", ":"))
        hasher.update(metrics_json.encode("utf-8"))

        if self.error_message:
            hasher.update(self.error_message.encode("utf-8"))

        object.__setattr__(self, "module_hash", hasher.digest())


@runtime_checkable
class ExecutionModule(Protocol):
    """
    State-isolated domain execution interface contract.
    """
    @property
    def module_id(self) -> str:
        ...

    def execute(self, frame: "CoreExecutionFrame", envelope: "KernelStateEnvelope") -> ExecutionResult:
        ...
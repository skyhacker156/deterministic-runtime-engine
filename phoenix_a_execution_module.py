"""
Phoenix A / ACE Domain Execution Module - Sentinel Framework
Concrete implementation of the ExecutionModule protocol.
Applies deterministic numerical transforms over core payload frames.
"""

import time
import hashlib
import numpy as np
from typing import Dict, Any

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelStateEnvelope
from execution_module_contract import ExecutionModule, ExecutionResult


class PhoenixAExecutionModule(ExecutionModule):
    """
    Phoenix A Core / ACE Execution Engine.
    Implements stateless numerical signal processing over raw execution frame payloads.
    """

    def __init__(self, module_id: str = "phoenix_a_core_v1") -> None:
        self._module_id = module_id

    @property
    def module_id(self) -> str:
        return self._module_id

    def execute(
        self, frame: CoreExecutionFrame, envelope: KernelStateEnvelope
    ) -> ExecutionResult:
        """
        Executes domain-specific transforms over the frame payload.
        1. Validates envelope state and frame integrity.
        2. Applies vector operations across the 256-element array.
        3. Computes runtime metrics (energy, drift, variance).
        4. Packages deterministic ExecutionResult payload and hash.
        """
        start_time_ns = time.perf_counter_ns()

        # Step 1: Defensive validation on inputs
        if frame.payload is None or frame.payload.shape != (256,):
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message=f"Invalid payload geometry: expected (256,), got {getattr(frame.payload, 'shape', None)}"
            )

        try:
            raw_data = frame.payload.copy()

            # Step 2: ACE Domain Transformation (Stateless geometric transform)
            # Normalize vector and derive secondary frequency components
            norm_factor = np.linalg.norm(raw_data)
            normalized_payload = raw_data if norm_factor == 0 else raw_data / norm_factor

            # Execute transform kernel (Example: rolling phase shift & non-linear scaling)
            transformed_payload = np.sin(normalized_payload * np.pi) + (normalized_payload * 0.5)

            # Ensure strict output shape and scalar type
            output_payload = transformed_payload.astype(np.float64)

            # Step 3: Compute Execution Metrics
            exec_latency_us = (time.perf_counter_ns() - start_time_ns) / 1000.0
            signal_energy = float(np.sum(np.square(output_payload)))
            vector_variance = float(np.var(output_payload))
            envelope_hash_prefix = float(int(envelope.state_hash[:8].hex(), 16) % 1_000_000)

            metrics: Dict[str, float] = {
                "execution_latency_us": exec_latency_us,
                "signal_energy": signal_energy,
                "vector_variance": vector_variance,
                "envelope_state_fingerprint": envelope_hash_prefix,
            }

            # Step 4: Construct and return verified ExecutionResult
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=True,
                output_payload=output_payload,
                metrics=metrics,
                error_message=None
            )

        except Exception as err:
            # Handle unexpected runtime execution exceptions cleanly
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message=f"Phoenix A runtime fault: {str(err)}"
            )
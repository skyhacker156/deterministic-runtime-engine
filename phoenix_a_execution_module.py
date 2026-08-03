"""
Phoenix A / ACE Domain Execution Module - Sentinel Framework
Concrete implementation of the ExecutionModule protocol.
Applies deterministic numerical transforms over core payload frames.

Hardening note (v1.6): the norm-based normalization path previously
triggered a RuntimeWarning on extreme-magnitude inputs (e.g. 1e300) —
np.linalg.norm's internal squaring step can overflow float64 range before
the sqrt brings the result back down, even though the final output stayed
finite. This version adds an explicit magnitude guard that routes extreme
inputs through a numerically safe path before that overflow can occur,
rather than relying on the eventual finite-output check to catch it after
the fact. Per ARCHITECTURE_FREEZE_v1.5.md's implicit goal of deterministic
warnings alongside deterministic results and failures, no code path in
this module should raise a numpy warning on any input the module is
expected to handle.
"""
import time
import hashlib
import numpy as np
from typing import Dict, Any
from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelStateEnvelope
from execution_module_contract import ExecutionModule, ExecutionResult

# Magnitude threshold above which raw values are pre-scaled before norm
# computation, to avoid overflow in the intermediate x.dot(x) step of
# np.linalg.norm. Chosen well below sqrt(float64_max) (~1.34e154) with
# a wide safety margin for the subsequent squaring operations performed
# on the normalized vector.
SAFE_MAGNITUDE_THRESHOLD = 1e100


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
            # Guard against overflow in the norm computation itself: if any
            # component's magnitude exceeds the safe threshold, pre-scale the
            # whole vector by its max absolute value before computing the norm.
            # This produces a mathematically equivalent direction (normalization
            # is scale-invariant) while keeping every intermediate squaring
            # operation well within float64 range.
            max_abs = np.max(np.abs(raw_data))

            if max_abs > SAFE_MAGNITUDE_THRESHOLD:
                scale_factor = max_abs
                scaled_data = raw_data / scale_factor
                norm_factor = np.linalg.norm(scaled_data)
            else:
                scaled_data = raw_data
                norm_factor = np.linalg.norm(raw_data)

            # Near-zero guard: exact-zero AND near-zero norms both route to
            # the unnormalized (or scaled-but-unnormalized) vector rather
            # than dividing by a value close enough to zero to blow up.
            if norm_factor < 1e-12:
                normalized_payload = scaled_data
            else:
                normalized_payload = scaled_data / norm_factor

            # Step: Execute transform kernel (rolling phase shift & non-linear scaling)
            transformed_payload = np.sin(normalized_payload * np.pi) + (normalized_payload * 0.5)

            # Ensure strict output shape and scalar type
            output_payload = transformed_payload.astype(np.float64)

            if not np.all(np.isfinite(output_payload)):
                return ExecutionResult(
                    seq_id=frame.seq_id,
                    success=False,
                    output_payload=np.zeros(256, dtype=np.float64),
                    error_message="ACE transform produced non-finite output despite magnitude guarding.",
                )

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
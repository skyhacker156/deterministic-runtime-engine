"""
Example Execution Module - Reference Implementation
(example_execution_module.py)

Deliberately minimal ExecutionModule implementation. This module does not
exist to solve a real problem — it exists to prove that
execution_module_spec.md and test_module_contract_compliance.py describe a
contract that is actually satisfiable by a straightforward implementation,
not just by PhoenixAExecutionModule's more elaborate one.

The transform is intentionally trivial: output = input * 2.
The point is not the math. The point is that an "unknown module" following
this pattern arrives at "known guarantees" by passing the compliance harness.
"""

import numpy as np

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelStateEnvelope
from execution_module_contract import ExecutionModule, ExecutionResult


class ExampleExecutionModule(ExecutionModule):
    """
    Reference ExecutionModule: doubles the input payload.

    Deliberately has none of PhoenixAExecutionModule's domain logic
    (no normalization, no sigmoid, no near-zero guards) so that it stays
    easy to read end-to-end as a template for what minimal compliance
    actually requires.
    """

    def __init__(self, module_id: str = "example_doubler_v1") -> None:
        self._module_id = module_id

    @property
    def module_id(self) -> str:
        return self._module_id

    def execute(
        self, frame: CoreExecutionFrame, envelope: KernelStateEnvelope
    ) -> ExecutionResult:
        """
        Requirement 1 (determinism): output is a pure function of frame.payload.
        No wall-clock reads, no randomness, no external state.

        Requirement 2 (finite outputs): guarded explicitly below rather than
        relying solely on ExecutionResult's structural backstop, per
        execution_module_spec.md's guidance to guard defensively.

        Requirement 5 (no independent hashing): output_hash is never touched
        here — module_hash is produced entirely by ExecutionResult's own
        __post_init__.
        """
        if frame.payload is None or frame.payload.shape != (256,):
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message=(
                    f"Invalid payload geometry: expected (256,), "
                    f"got {getattr(frame.payload, 'shape', None)}"
                ),
            )

        try:
            output_payload = (frame.payload * 2.0).astype(np.float64)

            if not np.all(np.isfinite(output_payload)):
                return ExecutionResult(
                    seq_id=frame.seq_id,
                    success=False,
                    output_payload=np.zeros(256, dtype=np.float64),
                    error_message="Doubling produced non-finite output (overflow).",
                )

            return ExecutionResult(
                seq_id=frame.seq_id,
                success=True,
                output_payload=output_payload,
                metrics={
                    "input_sum": float(np.sum(frame.payload)),
                    "output_sum": float(np.sum(output_payload)),
                },
                error_message=None,
            )

        except Exception as err:
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message=f"ExampleExecutionModule runtime fault: {err}",
            )
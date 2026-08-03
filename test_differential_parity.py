"""
Layer 3 Differential Parity Harness (Python Core vs. Rust Compiled Kernel)
Module ID: SENTINEL-DIFFERENTIAL-HARNESS-V1
"""

import ctypes
import math
import os
import pytest
from hypothesis import given, strategies as st, settings

# Import Python Reference Implementation
from phoenix_a_core import PhoenixAExecutionCore, PhoenixInputPacket, ExecutionStatus

# ---------------------------------------------------------------------
# 1. C-FFI BINDING TO RUST DLL
# ---------------------------------------------------------------------
class C_PhoenixInputPacket(ctypes.Structure):
    _fields_ = [
        ("current_weight", ctypes.c_double),
        ("target_weight", ctypes.c_double),
        ("dt", ctypes.c_double),
    ]

class C_PhoenixOutputPacket(ctypes.Structure):
    _fields_ = [
        ("next_weight", ctypes.c_double),
        ("delta_applied", ctypes.c_double),
        ("status_code", ctypes.c_int32),
    ]

# Load compiled Rust dynamic library
DLL_PATH = os.path.join("phoenix_core_rs", "target", "release", "phoenix_core_rs.dll")
rust_lib = ctypes.CDLL(DLL_PATH)

rust_lib.phoenix_a_core_step.argtypes = [C_PhoenixInputPacket]
rust_lib.phoenix_a_core_step.restype = C_PhoenixOutputPacket


# ---------------------------------------------------------------------
# 2. EXPLICIT STATUS CODE EDGE CASE TESTS
# ---------------------------------------------------------------------
def test_explicit_nan_fallback_status_parity():
    """Verify status code parity on NaN current weight with valid target and dt."""
    py_out = PhoenixAExecutionCore.step(PhoenixInputPacket(float("nan"), 0.8, 0.1))
    rust_out = rust_lib.phoenix_a_core_step(C_PhoenixInputPacket(float("nan"), 0.8, 0.1))

    assert py_out.status == ExecutionStatus.POLICY_FALLBACK
    assert rust_out.status_code == 2
    assert math.isclose(py_out.next_weight, rust_out.next_weight, abs_tol=1e-12)


def test_explicit_equilibrium_with_bad_dt_status_parity():
    """Verify status code parity when equal weights are combined with non-finite dt."""
    py_out = PhoenixAExecutionCore.step(PhoenixInputPacket(0.5, 0.5, float("nan")))
    rust_out = rust_lib.phoenix_a_core_step(C_PhoenixInputPacket(0.5, 0.5, float("nan")))

    assert py_out.status == ExecutionStatus.POLICY_FALLBACK
    assert rust_out.status_code == 2
    assert py_out.delta_applied == 0.0
    assert rust_out.delta_applied == 0.0


# ---------------------------------------------------------------------
# 3. DIFFERENTIAL PROPERTY TESTS
# ---------------------------------------------------------------------
class TestDifferentialParity:

    @settings(max_examples=5000)
    @given(
        current=st.floats(allow_nan=True, allow_infinity=True),
        target=st.floats(allow_nan=True, allow_infinity=True),
        dt=st.floats(allow_nan=True, allow_infinity=True),
    )
    def test_bit_exact_parity_python_vs_rust(
        self, current: float, target: float, dt: float
    ):
        py_input = PhoenixInputPacket(current_weight=current, target_weight=target, dt=dt)
        py_output = PhoenixAExecutionCore.step(py_input)

        rust_input = C_PhoenixInputPacket(
            current_weight=current, target_weight=target, dt=dt
        )
        rust_output = rust_lib.phoenix_a_core_step(rust_input)

        status_map = {
            0: ExecutionStatus.CONVERGING,
            1: ExecutionStatus.AT_EQUILIBRIUM,
            2: ExecutionStatus.POLICY_FALLBACK,
        }
        rust_mapped_status = status_map[rust_output.status_code]

        assert math.isclose(
            py_output.next_weight, rust_output.next_weight, abs_tol=1e-12
        ), f"Weight Mismatch: Py={py_output.next_weight}, Rust={rust_output.next_weight}"

        assert math.isclose(
            py_output.delta_applied, rust_output.delta_applied, abs_tol=1e-12
        ), f"Delta Mismatch: Py={py_output.delta_applied}, Rust={rust_output.delta_applied}"

        assert (
            py_output.status == rust_mapped_status
        ), f"Status Mismatch: Py={py_output.status}, Rust={rust_mapped_status}"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
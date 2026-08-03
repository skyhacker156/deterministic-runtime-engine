"""
Execution Module Registry Test Suite
(test_module_registry.py)

Verifies ExecutionModuleRegistry's registration, lookup, duplicate/unknown
rejection, replay-safe resolution, and capability verification behavior.
"""

import pytest

from execution_module_registry import (
    ExecutionModuleRegistry,
    DuplicateModuleError,
    ModuleNotFoundError,
    ModuleCapabilities,
)
from module_compliance_checks import ModuleComplianceError
from phoenix_a_execution_module import PhoenixAExecutionModule
from example_execution_module import ExampleExecutionModule
from execution_kernel_contract import CoreExecutionFrame
from deterministic_execution_engine import DeterministicExecutionEngine


# ---------------------------------------------------------------------
# 1. Registration and deterministic lookup
# ---------------------------------------------------------------------

def test_register_and_resolve_returns_same_instance():
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    registry.register(module)
    resolved = registry.resolve("phoenix_a_core_v1")

    assert resolved is module


def test_registered_ids_reflects_registration():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.register(ExampleExecutionModule())

    assert registry.registered_ids() == ("example_doubler_v1", "phoenix_a_core_v1")


def test_is_registered_reflects_state():
    registry = ExecutionModuleRegistry()
    assert registry.is_registered("phoenix_a_core_v1") is False

    registry.register(PhoenixAExecutionModule())
    assert registry.is_registered("phoenix_a_core_v1") is True


# ---------------------------------------------------------------------
# 2. Duplicate ID rejection
# ---------------------------------------------------------------------

def test_duplicate_module_id_rejected():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())

    with pytest.raises(DuplicateModuleError, match="already registered"):
        registry.register(PhoenixAExecutionModule())


def test_duplicate_rejection_does_not_replace_original_entry():
    """A rejected duplicate registration must not disturb the original."""
    registry = ExecutionModuleRegistry()
    original = PhoenixAExecutionModule()
    registry.register(original)

    duplicate = PhoenixAExecutionModule()
    with pytest.raises(DuplicateModuleError):
        registry.register(duplicate)

    assert registry.resolve("phoenix_a_core_v1") is original


# ---------------------------------------------------------------------
# 3. Unknown module rejection
# ---------------------------------------------------------------------

def test_resolve_unknown_module_id_raises():
    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleNotFoundError, match="does_not_exist"):
        registry.resolve("does_not_exist")


def test_capabilities_unknown_module_id_raises():
    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleNotFoundError):
        registry.capabilities("does_not_exist")


# ---------------------------------------------------------------------
# 4. Replay-safe resolution: registry-mediated execution is still
#    deterministic through the full engine, not just at the registry
#    boundary.
# ---------------------------------------------------------------------

def test_resolution_replay_is_deterministic():
    """
    Given the same registry state, resolving a module by ID and running
    it through the engine twice must produce an identical audit chain —
    not just identical objects at the registry boundary.
    """
    def run():
        registry = ExecutionModuleRegistry()
        registry.register(PhoenixAExecutionModule())
        module = registry.resolve("phoenix_a_core_v1")

        engine = DeterministicExecutionEngine(module=module)
        engine.initialize()

        import numpy as np
        payload = np.full(256, fill_value=1.5, dtype=np.float64)
        frame = CoreExecutionFrame.create(seq_id=0, timestamp_ns=1_000_000, payload=payload)

        engine.process_frame(frame)
        return tuple(r.audit_hash for r in engine.audit_log)

    assert run() == run()


# ---------------------------------------------------------------------
# 5. Capability verification: registry confirms, doesn't trust
# ---------------------------------------------------------------------

def test_verified_registration_produces_confirmed_capabilities():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule(), verify=True)

    caps = registry.capabilities("phoenix_a_core_v1")
    assert caps.verified is True
    assert caps.deterministic is True
    assert caps.replayable is True
    assert caps.audit_safe is True


def test_unverified_registration_produces_unverified_capabilities():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule(), verify=False)

    caps = registry.capabilities("phoenix_a_core_v1")
    assert caps.verified is False
    assert caps.deterministic is False
    assert caps.replayable is False
    assert caps.audit_safe is False


def test_noncompliant_module_registration_fails():
    """
    A module that violates the contract must fail registration under
    verify=True, not be silently accepted with false capabilities.
    """

    class _NonDeterministicModule:
        """Deliberately violates determinism by embedding a call counter
        in the output, so identical input produces different results."""

        def __init__(self):
            self._call_count = 0

        @property
        def module_id(self) -> str:
            return "non_deterministic_test_module"

        def execute(self, frame, envelope):
            import numpy as np
            from execution_module_contract import ExecutionResult

            self._call_count += 1
            payload = frame.payload.copy()
            payload[0] += self._call_count  # breaks determinism

            return ExecutionResult(
                seq_id=frame.seq_id,
                success=True,
                output_payload=payload,
            )

    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleComplianceError, match="determinism"):
        registry.register(_NonDeterministicModule())

    # Critically: a failed registration must not leave a partial entry.
    assert registry.is_registered("non_deterministic_test_module") is False


def test_second_module_capabilities_independent_of_first():
    """Registering two modules must not cross-contaminate their capability records."""
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule(), verify=True)
    registry.register(ExampleExecutionModule(), verify=False)

    phoenix_caps = registry.capabilities("phoenix_a_core_v1")
    example_caps = registry.capabilities("example_doubler_v1")

    assert phoenix_caps.verified is True
    assert example_caps.verified is False
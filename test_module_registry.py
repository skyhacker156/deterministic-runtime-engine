"""
Execution Module Registry Test Suite
(test_module_registry.py)

Verifies ExecutionModuleRegistry's registration, lifecycle-gated lookup,
duplicate/unknown rejection, activation, fault/retire administration, and
capability verification behavior.

Wiring update: resolve() now requires the module to be ACTIVE, not just
registered — activation is a separate, explicit step. Every test that
needs a resolvable module now calls activate() before resolve().
"""

import pytest

from execution_module_registry import (
    ExecutionModuleRegistry,
    DuplicateModuleError,
    ModuleNotFoundError,
    ModuleNotActiveError,
    ModuleCapabilities,
)
from module_lifecycle import ModuleState
from module_compliance_checks import ModuleComplianceError
from phoenix_a_execution_module import PhoenixAExecutionModule
from example_execution_module import ExampleExecutionModule
from execution_kernel_contract import CoreExecutionFrame
from deterministic_execution_engine import DeterministicExecutionEngine


# ---------------------------------------------------------------------
# 1. Registration and lifecycle-gated lookup
# ---------------------------------------------------------------------

def test_register_then_activate_then_resolve_returns_same_instance():
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    registry.register(module)
    registry.activate("phoenix_a_core_v1")
    resolved = registry.resolve("phoenix_a_core_v1")

    assert resolved is module


def test_resolve_before_activation_raises_module_not_active():
    """
    The core wiring fix: register() alone must NOT make a module
    resolvable. Only an explicit activate() does.
    """
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())

    with pytest.raises(ModuleNotActiveError, match="not ACTIVE"):
        registry.resolve("phoenix_a_core_v1")


def test_resolve_before_activation_error_reports_registered_state():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())

    with pytest.raises(ModuleNotActiveError, match="REGISTERED"):
        registry.resolve("phoenix_a_core_v1")


def test_registered_ids_reflects_registration_regardless_of_activation():
    """registered_ids() reflects registry presence, not activation state."""
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.register(ExampleExecutionModule())

    assert registry.registered_ids() == ("example_doubler_v1", "phoenix_a_core_v1")


def test_is_registered_reflects_state_regardless_of_activation():
    registry = ExecutionModuleRegistry()
    assert registry.is_registered("phoenix_a_core_v1") is False

    registry.register(PhoenixAExecutionModule())
    assert registry.is_registered("phoenix_a_core_v1") is True
    # Registered but not yet activated — is_registered is still True.


def test_lifecycle_state_reflects_registration_progress():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    assert registry.lifecycle_state("phoenix_a_core_v1") == ModuleState.REGISTERED

    registry.activate("phoenix_a_core_v1")
    assert registry.lifecycle_state("phoenix_a_core_v1") == ModuleState.ACTIVE


# ---------------------------------------------------------------------
# 2. Duplicate ID rejection
# ---------------------------------------------------------------------

def test_duplicate_module_id_rejected():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())

    with pytest.raises(DuplicateModuleError, match="already registered"):
        registry.register(PhoenixAExecutionModule())


def test_duplicate_rejection_does_not_replace_original_entry():
    registry = ExecutionModuleRegistry()
    original = PhoenixAExecutionModule()
    registry.register(original)
    registry.activate("phoenix_a_core_v1")

    duplicate = PhoenixAExecutionModule()
    with pytest.raises(DuplicateModuleError):
        registry.register(duplicate)

    assert registry.resolve("phoenix_a_core_v1") is original


# ---------------------------------------------------------------------
# 3. Unknown module rejection
# ---------------------------------------------------------------------

def test_resolve_unknown_module_id_raises_not_found():
    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleNotFoundError, match="does_not_exist"):
        registry.resolve("does_not_exist")


def test_capabilities_unknown_module_id_raises():
    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleNotFoundError):
        registry.capabilities("does_not_exist")


def test_activate_unknown_module_id_raises_not_found():
    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleNotFoundError, match="not registered"):
        registry.activate("does_not_exist")


def test_fault_unknown_module_id_raises_not_found():
    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleNotFoundError, match="not registered"):
        registry.fault("does_not_exist", "reason")


def test_retire_unknown_module_id_raises_not_found():
    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleNotFoundError, match="not registered"):
        registry.retire("does_not_exist")


# ---------------------------------------------------------------------
# 4. Fault and retire actually block resolve() — the actual point of
#    wiring lifecycle into the registry
# ---------------------------------------------------------------------

def test_faulted_module_cannot_be_resolved():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")

    # Confirm it's resolvable before faulting.
    registry.resolve("phoenix_a_core_v1")

    registry.fault("phoenix_a_core_v1", "post-activation integrity concern")

    with pytest.raises(ModuleNotActiveError, match="FAULTED"):
        registry.resolve("phoenix_a_core_v1")


def test_fault_reason_surfaces_in_resolve_error():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")
    registry.fault("phoenix_a_core_v1", "simulated drift detected")

    with pytest.raises(ModuleNotActiveError, match="simulated drift detected"):
        registry.resolve("phoenix_a_core_v1")


def test_retired_module_cannot_be_resolved():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")

    registry.retire("phoenix_a_core_v1")

    with pytest.raises(ModuleNotActiveError, match="RETIRED"):
        registry.resolve("phoenix_a_core_v1")


def test_fault_on_non_active_module_raises_invalid_transition():
    """
    fault() should only work on an ACTIVE module — this delegates to
    ModuleLifecycleManager's own transition rules, so faulting a
    not-yet-activated REGISTERED module must fail.
    """
    from module_lifecycle import InvalidLifecycleTransitionError

    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    # Never activated.

    with pytest.raises(InvalidLifecycleTransitionError):
        registry.fault("phoenix_a_core_v1", "reason")


def test_retire_is_permanent_no_reactivation():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.activate("phoenix_a_core_v1")
    registry.retire("phoenix_a_core_v1")

    from module_lifecycle import InvalidLifecycleTransitionError
    with pytest.raises(InvalidLifecycleTransitionError):
        registry.activate("phoenix_a_core_v1")


# ---------------------------------------------------------------------
# 5. Replay-safe resolution through the full engine, post-activation
# ---------------------------------------------------------------------

def test_resolution_replay_is_deterministic():
    """
    Given the same registry state, activating and resolving a module by
    ID and running it through the engine twice must produce an identical
    audit chain — not just identical objects at the registry boundary.
    """
    def run():
        registry = ExecutionModuleRegistry()
        registry.register(PhoenixAExecutionModule())
        registry.activate("phoenix_a_core_v1")
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
# 6. Capability verification: registry confirms, doesn't trust
#    (capabilities available regardless of activation state)
# ---------------------------------------------------------------------

def test_verified_registration_produces_confirmed_capabilities():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule(), verify=True)
    # Note: NOT activated — capabilities should still be readable.

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


def test_noncompliant_module_registration_fails():
    """
    A module that violates the contract must fail registration under
    verify=True, not be silently accepted with false capabilities. It
    must also never reach ACTIVE.
    """

    class _NonDeterministicModule:
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
            payload[0] += self._call_count

            return ExecutionResult(
                seq_id=frame.seq_id,
                success=True,
                output_payload=payload,
            )

    registry = ExecutionModuleRegistry()
    with pytest.raises(ModuleComplianceError, match="determinism"):
        registry.register(_NonDeterministicModule())

    assert registry.is_registered("non_deterministic_test_module") is False

    with pytest.raises(ModuleNotFoundError):
        registry.resolve("non_deterministic_test_module")


def test_second_module_capabilities_independent_of_first():
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule(), verify=True)
    registry.register(ExampleExecutionModule(), verify=False)

    phoenix_caps = registry.capabilities("phoenix_a_core_v1")
    example_caps = registry.capabilities("example_doubler_v1")

    assert phoenix_caps.verified is True
    assert example_caps.verified is False


def test_two_modules_activation_states_are_independent():
    """Activating one module must not affect another's activation state."""
    registry = ExecutionModuleRegistry()
    registry.register(PhoenixAExecutionModule())
    registry.register(ExampleExecutionModule())

    registry.activate("phoenix_a_core_v1")

    registry.resolve("phoenix_a_core_v1")  # should succeed

    with pytest.raises(ModuleNotActiveError):
        registry.resolve("example_doubler_v1")  # never activated
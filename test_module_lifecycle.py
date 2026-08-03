"""
Module Lifecycle State Machine Test Suite
(test_module_lifecycle.py)

Verifies ModuleLifecycleManager's transition table (allowed and forbidden
edges), fault-reason handling, and the is_active() query engine dispatch
is meant to rely on.
"""

import pytest

from module_lifecycle import (
    ModuleLifecycleManager,
    ModuleState,
    ModuleLifecycleError,
    InvalidLifecycleTransitionError,
)


# ---------------------------------------------------------------------
# 1. Discovery
# ---------------------------------------------------------------------

def test_discover_creates_record_in_discovered_state():
    manager = ModuleLifecycleManager()
    record = manager.discover("phoenix_a_core")

    assert record.module_id == "phoenix_a_core"
    assert record.state == ModuleState.DISCOVERED
    assert record.fault_reason is None


def test_discover_twice_for_same_module_id_rejected():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")

    with pytest.raises(ModuleLifecycleError, match="already has a lifecycle record"):
        manager.discover("phoenix_a_core")


def test_get_record_for_unknown_module_id_rejected():
    manager = ModuleLifecycleManager()
    with pytest.raises(ModuleLifecycleError, match="No lifecycle record"):
        manager.get_record("does_not_exist")


# ---------------------------------------------------------------------
# 2. Allowed transition sequence, straight through
# ---------------------------------------------------------------------

def test_full_lifecycle_happy_path():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")

    r1 = manager.mark_validated("phoenix_a_core")
    assert r1.state == ModuleState.VALIDATED

    r2 = manager.mark_registered("phoenix_a_core")
    assert r2.state == ModuleState.REGISTERED

    r3 = manager.activate("phoenix_a_core")
    assert r3.state == ModuleState.ACTIVE
    assert manager.is_active("phoenix_a_core") is True

    r4 = manager.retire("phoenix_a_core")
    assert r4.state == ModuleState.RETIRED
    assert manager.is_active("phoenix_a_core") is False


def test_active_module_can_be_faulted_with_reason():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")
    manager.activate("phoenix_a_core")

    record = manager.mark_faulted("phoenix_a_core", "post-activation compliance re-check failed")

    assert record.state == ModuleState.FAULTED
    assert record.fault_reason == "post-activation compliance re-check failed"
    assert manager.is_active("phoenix_a_core") is False


def test_faulted_module_can_be_retired():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")
    manager.activate("phoenix_a_core")
    manager.mark_faulted("phoenix_a_core", "reason")

    record = manager.retire("phoenix_a_core")
    assert record.state == ModuleState.RETIRED


def test_registered_module_can_be_retired_without_ever_activating():
    """A module can be retired directly from REGISTERED — not every
    module has to pass through ACTIVE before retirement."""
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")

    record = manager.retire("phoenix_a_core")
    assert record.state == ModuleState.RETIRED


def test_discovered_module_can_be_retired_directly():
    """A module can be abandoned immediately after discovery — e.g. it
    fails manifest validation and never proceeds further."""
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")

    record = manager.retire("phoenix_a_core")
    assert record.state == ModuleState.RETIRED


def test_validated_module_can_be_retired_directly():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")

    record = manager.retire("phoenix_a_core")
    assert record.state == ModuleState.RETIRED


# ---------------------------------------------------------------------
# 3. Forbidden transitions — explicitly named in the proposal
# ---------------------------------------------------------------------

def test_discovered_to_active_directly_rejected():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")

    with pytest.raises(InvalidLifecycleTransitionError, match="DISCOVERED -> ACTIVE"):
        manager.activate("phoenix_a_core")


def test_faulted_to_active_rejected_no_recovery_path():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")
    manager.activate("phoenix_a_core")
    manager.mark_faulted("phoenix_a_core", "reason")

    with pytest.raises(InvalidLifecycleTransitionError, match="FAULTED -> ACTIVE"):
        manager.activate("phoenix_a_core")


def test_retired_to_active_rejected():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")
    manager.activate("phoenix_a_core")
    manager.retire("phoenix_a_core")

    with pytest.raises(InvalidLifecycleTransitionError, match="RETIRED -> ACTIVE"):
        manager.activate("phoenix_a_core")


def test_retired_is_fully_terminal_no_transitions_allowed():
    """RETIRED must reject every possible destination state, not just ACTIVE."""
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.retire("phoenix_a_core")

    for method, args in [
        (manager.mark_validated, ("phoenix_a_core",)),
        (manager.mark_registered, ("phoenix_a_core",)),
        (manager.activate, ("phoenix_a_core",)),
        (manager.retire, ("phoenix_a_core",)),
    ]:
        with pytest.raises(InvalidLifecycleTransitionError):
            method(*args)


def test_skipping_validated_to_register_directly_rejected():
    """DISCOVERED must go through VALIDATED before REGISTERED — cannot skip."""
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")

    with pytest.raises(InvalidLifecycleTransitionError, match="DISCOVERED -> REGISTERED"):
        manager.mark_registered("phoenix_a_core")


def test_skipping_registered_to_activate_from_validated_rejected():
    """VALIDATED must go through REGISTERED before ACTIVE — cannot skip."""
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")

    with pytest.raises(InvalidLifecycleTransitionError, match="VALIDATED -> ACTIVE"):
        manager.activate("phoenix_a_core")


def test_faulted_cannot_go_back_to_registered_or_validated():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")
    manager.activate("phoenix_a_core")
    manager.mark_faulted("phoenix_a_core", "reason")

    with pytest.raises(InvalidLifecycleTransitionError):
        manager.mark_registered("phoenix_a_core")
    with pytest.raises(InvalidLifecycleTransitionError):
        manager.mark_validated("phoenix_a_core")


# ---------------------------------------------------------------------
# 4. Operating on an unknown module_id at any transition method
# ---------------------------------------------------------------------

@pytest.mark.parametrize("method_name", [
    "mark_validated", "mark_registered", "activate", "retire",
])
def test_transition_on_unknown_module_id_rejected(method_name):
    manager = ModuleLifecycleManager()
    method = getattr(manager, method_name)

    with pytest.raises(ModuleLifecycleError, match="no lifecycle record"):
        method("does_not_exist")


def test_mark_faulted_on_unknown_module_id_rejected():
    manager = ModuleLifecycleManager()
    with pytest.raises(ModuleLifecycleError, match="no lifecycle record"):
        manager.mark_faulted("does_not_exist", "reason")


# ---------------------------------------------------------------------
# 5. Fault reason requirements
# ---------------------------------------------------------------------

def test_mark_faulted_requires_non_empty_reason():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")
    manager.activate("phoenix_a_core")

    with pytest.raises(ModuleLifecycleError, match="non-empty reason"):
        manager.mark_faulted("phoenix_a_core", "")


def test_mark_faulted_rejects_whitespace_only_reason():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")
    manager.activate("phoenix_a_core")

    with pytest.raises(ModuleLifecycleError, match="non-empty reason"):
        manager.mark_faulted("phoenix_a_core", "   ")


# ---------------------------------------------------------------------
# 6. Independence across multiple modules
# ---------------------------------------------------------------------

def test_multiple_modules_have_independent_lifecycle_state():
    manager = ModuleLifecycleManager()
    manager.discover("phoenix_a_core")
    manager.discover("example_doubler")

    manager.mark_validated("phoenix_a_core")
    manager.mark_registered("phoenix_a_core")
    manager.activate("phoenix_a_core")

    # example_doubler should still be sitting at DISCOVERED, untouched.
    record = manager.get_record("example_doubler")
    assert record.state == ModuleState.DISCOVERED

    assert manager.is_active("phoenix_a_core") is True
    assert manager.is_active("example_doubler") is False


def test_one_module_faulting_does_not_affect_another():
    manager = ModuleLifecycleManager()
    for module_id in ("phoenix_a_core", "example_doubler"):
        manager.discover(module_id)
        manager.mark_validated(module_id)
        manager.mark_registered(module_id)
        manager.activate(module_id)

    manager.mark_faulted("phoenix_a_core", "reason")

    assert manager.is_active("phoenix_a_core") is False
    assert manager.is_active("example_doubler") is True
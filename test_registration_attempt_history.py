"""
Registration Attempt History - Integration Tests
(test_registration_attempt_history.py)

Proves the actual gap identified in review: v2.6's atomicity fix
guaranteed failed registrations leave no trace in the OPERATIONAL
registry/lifecycle manager, but said nothing about whether the attempt
itself is observable anywhere. These tests are the missing piece --
they were absent from test_registration_atomicity.py, whose 5 green
tests proved atomicity, not observability.
"""

import pytest

from execution_module_registry import (
    ExecutionModuleRegistry,
    ModuleVersionError,
)
from module_compliance_checks import ModuleComplianceError

# Adjust these imports/helpers to match your actual fixtures --
# mirroring the _bad_manifest / _good_manifest helpers already used in
# test_registration_atomicity.py.
from test_registration_atomicity import (
    PhoenixAExecutionModule,
    _bad_manifest,
    _good_manifest,
)


def test_failed_manifest_registration_is_captured_in_history():
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    with pytest.raises(ModuleVersionError):
        registry.register(module, manifest=_bad_manifest(module.module_id))

    history = registry.registration_history(module.module_id)
    assert len(history) == 1
    assert history[0].success is False
    assert history[0].reason  # non-empty, exact wording not asserted here
    assert registry.is_registered(module.module_id) is False


def test_successful_registration_is_captured_in_history():
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    registry.register(module, manifest=_good_manifest(module.module_id))

    history = registry.registration_history(module.module_id)
    assert len(history) == 1
    assert history[0].success is True
    assert history[0].reason is None
    assert registry.is_registered(module.module_id) is True


def test_failed_then_retried_registration_preserves_full_history():
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    with pytest.raises(ModuleVersionError):
        registry.register(module, manifest=_bad_manifest(module.module_id))

    registry.register(module, manifest=_good_manifest(module.module_id))

    history = registry.registration_history(module.module_id)
    assert len(history) == 2
    assert history[0].success is False
    assert history[1].success is True
    # order preserved -- failure recorded before the successful retry
    assert history[0].attempted_at_ns <= history[1].attempted_at_ns


def test_registration_history_empty_for_untouched_module_id():
    registry = ExecutionModuleRegistry()
    # No register() call was ever made for this module_id.
    history = registry.registration_history("never_touched_module")
    assert history == ()


def test_registration_history_does_not_affect_duplicate_protection():
    """
    Guards against a specific regression: appending to attempt history
    must never be mistaken by the registry for a registered entry.
    Two consecutive failures should both be captured, and the module
    should still be registerable afterward.
    """
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    with pytest.raises(ModuleVersionError):
        registry.register(module, manifest=_bad_manifest(module.module_id))
    with pytest.raises(ModuleVersionError):
        registry.register(module, manifest=_bad_manifest(module.module_id))

    history = registry.registration_history(module.module_id)
    assert len(history) == 2
    assert all(rec.success is False for rec in history)

    # third attempt, this time with a good manifest, should still succeed
    registry.register(module, manifest=_good_manifest(module.module_id))
    assert registry.is_registered(module.module_id) is True
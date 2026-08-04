"""
Registration Atomicity Test Suite
(test_registration_atomicity.py)

Verifies register()'s two-phase structure: a failed registration (bad
manifest or failed compliance) leaves ZERO trace — no lifecycle record,
no registry entry — so the same module_id can be retried freely once the
underlying problem is fixed. This is the property GPT's two-phase
gather/commit split was specifically written to guarantee, replacing the
earlier version where a manifest failure left a permanent, unretryable
DISCOVERED lifecycle record.
"""

import pytest

from execution_module_registry import (
    ExecutionModuleRegistry,
    ModuleVersionError,
    DuplicateModuleError,
)
from execution_module_manifest import ModuleManifest, CURRENT_RUNTIME_API_VERSION, CURRENT_CONTEXT_SCHEMA_VERSION
from module_compliance_checks import ModuleComplianceError
from phoenix_a_execution_module import PhoenixAExecutionModule


def _bad_manifest(module_id: str) -> ModuleManifest:
    """A manifest that will fail check_manifest_compatible() — wrong
    runtime_api version."""
    return ModuleManifest(
        module_id=module_id,
        version="1.0.0",
        runtime_api="0.1",  # deliberately wrong
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
    )


def _good_manifest(module_id: str) -> ModuleManifest:
    return ModuleManifest(
        module_id=module_id,
        version="1.0.0",
        runtime_api=CURRENT_RUNTIME_API_VERSION,
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------
# 1. Failed manifest check leaves zero trace
# ---------------------------------------------------------------------

def test_failed_manifest_check_leaves_no_lifecycle_record():
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    with pytest.raises(ModuleVersionError):
        registry.register(module, manifest=_bad_manifest(module.module_id))

    # Zero trace: not registered, and no lifecycle record exists at all
    # (querying it should raise, not return DISCOVERED).
    assert registry.is_registered(module.module_id) is False

    from module_lifecycle import ModuleLifecycleError
    with pytest.raises(ModuleLifecycleError):
        registry.lifecycle_state(module.module_id)


def test_failed_manifest_check_allows_immediate_retry_with_good_manifest():
    """
    The actual behavior this fix unlocks: register with a bad manifest,
    fail, then register again under the SAME module_id with a corrected
    manifest, and succeed — with no special-case cleanup required.
    """
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    with pytest.raises(ModuleVersionError):
        registry.register(module, manifest=_bad_manifest(module.module_id))

    # Retry, same module_id, same instance, corrected manifest.
    registry.register(module, manifest=_good_manifest(module.module_id))

    assert registry.is_registered(module.module_id) is True
    from module_lifecycle import ModuleState
    assert registry.lifecycle_state(module.module_id) == ModuleState.REGISTERED


# ---------------------------------------------------------------------
# 2. Failed compliance check leaves zero trace
# ---------------------------------------------------------------------

def test_failed_compliance_check_leaves_no_lifecycle_record():
    class _NonDeterministicModule:
        def __init__(self):
            self._call_count = 0

        @property
        def module_id(self) -> str:
            return "non_deterministic_atomicity_test"

        def execute(self, frame, envelope):
            import numpy as np
            from execution_module_contract import ExecutionResult
            self._call_count += 1
            payload = frame.payload.copy()
            payload[0] += self._call_count
            return ExecutionResult(seq_id=frame.seq_id, success=True, output_payload=payload)

    registry = ExecutionModuleRegistry()
    module = _NonDeterministicModule()

    with pytest.raises(ModuleComplianceError):
        registry.register(module)  # default manifest, should pass; compliance should fail

    assert registry.is_registered(module.module_id) is False

    from module_lifecycle import ModuleLifecycleError
    with pytest.raises(ModuleLifecycleError):
        registry.lifecycle_state(module.module_id)


# ---------------------------------------------------------------------
# 3. Successful registration still commits atomically as a whole
# ---------------------------------------------------------------------

def test_successful_registration_commits_full_lifecycle_in_one_call():
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()

    registry.register(module, manifest=_good_manifest(module.module_id))

    from module_lifecycle import ModuleState
    assert registry.lifecycle_state(module.module_id) == ModuleState.REGISTERED
    assert registry.is_registered(module.module_id) is True


# ---------------------------------------------------------------------
# 4. Duplicate check still fires correctly (unaffected by the two-phase
#    restructure — this is a regression guard)
# ---------------------------------------------------------------------

def test_duplicate_registration_after_success_still_rejected():
    registry = ExecutionModuleRegistry()
    module = PhoenixAExecutionModule()
    registry.register(module, manifest=_good_manifest(module.module_id))

    with pytest.raises(DuplicateModuleError):
        registry.register(PhoenixAExecutionModule(), manifest=_good_manifest(module.module_id))
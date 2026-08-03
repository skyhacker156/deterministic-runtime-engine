"""
Manifest Compatibility Test Suite
(test_execution_module_manifest.py)

Verifies ModuleManifest construction validation and runtime compatibility
checking. This deliberately does NOT test registry integration — that
belongs to a separate test once ExecutionModuleRegistry.register() is
wired to require and check a manifest. This file tests the manifest and
compatibility-check logic in isolation.
"""

import pytest

from execution_module_manifest import (
    ModuleManifest,
    ManifestValidationError,
    ModuleVersionIncompatibleError,
    check_manifest_compatible,
    CURRENT_RUNTIME_API_VERSION,
    CURRENT_CONTEXT_SCHEMA_VERSION,
    KNOWN_CAPABILITIES,
)


# ---------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------

def test_valid_manifest_constructs():
    manifest = ModuleManifest(
        module_id="phoenix_a_core",
        version="1.0.0",
        runtime_api=CURRENT_RUNTIME_API_VERSION,
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
        capabilities=("deterministic", "replayable", "audit_safe"),
    )
    assert manifest.module_id == "phoenix_a_core"
    assert manifest.capabilities == ("deterministic", "replayable", "audit_safe")


def test_manifest_with_empty_capabilities_is_valid():
    """A manifest declaring no capabilities is valid — it just claims nothing."""
    manifest = ModuleManifest(
        module_id="minimal_module",
        version="0.1.0",
        runtime_api=CURRENT_RUNTIME_API_VERSION,
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
    )
    assert manifest.capabilities == ()


@pytest.mark.parametrize("bad_module_id", ["", "   ", None])
def test_empty_module_id_rejected(bad_module_id):
    with pytest.raises(ManifestValidationError, match="module_id"):
        ModuleManifest(
            module_id=bad_module_id,
            version="1.0.0",
            runtime_api=CURRENT_RUNTIME_API_VERSION,
            context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
        )


@pytest.mark.parametrize("bad_version", ["", "   ", None])
def test_empty_version_rejected(bad_version):
    with pytest.raises(ManifestValidationError, match="version"):
        ModuleManifest(
            module_id="phoenix_a_core",
            version=bad_version,
            runtime_api=CURRENT_RUNTIME_API_VERSION,
            context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
        )


@pytest.mark.parametrize("bad_api", ["", "   ", None])
def test_empty_runtime_api_rejected(bad_api):
    with pytest.raises(ManifestValidationError, match="runtime_api"):
        ModuleManifest(
            module_id="phoenix_a_core",
            version="1.0.0",
            runtime_api=bad_api,
            context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
        )


@pytest.mark.parametrize("bad_schema", ["", "   ", None])
def test_empty_context_schema_rejected(bad_schema):
    with pytest.raises(ManifestValidationError, match="context_schema"):
        ModuleManifest(
            module_id="phoenix_a_core",
            version="1.0.0",
            runtime_api=CURRENT_RUNTIME_API_VERSION,
            context_schema=bad_schema,
        )


def test_unknown_capability_rejected():
    with pytest.raises(ManifestValidationError, match="Unknown capability"):
        ModuleManifest(
            module_id="phoenix_a_core",
            version="1.0.0",
            runtime_api=CURRENT_RUNTIME_API_VERSION,
            context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
            capabilities=("deterministic", "telekinetic"),
        )


def test_all_known_capabilities_accepted_together():
    manifest = ModuleManifest(
        module_id="phoenix_a_core",
        version="1.0.0",
        runtime_api=CURRENT_RUNTIME_API_VERSION,
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
        capabilities=tuple(sorted(KNOWN_CAPABILITIES)),
    )
    assert set(manifest.capabilities) == KNOWN_CAPABILITIES


# ---------------------------------------------------------------------
# Compatibility checking — exact-match policy
# ---------------------------------------------------------------------

def test_matching_versions_pass_compatibility_check():
    manifest = ModuleManifest(
        module_id="phoenix_a_core",
        version="1.0.0",
        runtime_api=CURRENT_RUNTIME_API_VERSION,
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
    )
    # Should not raise.
    check_manifest_compatible(manifest)


def test_mismatched_runtime_api_rejected():
    manifest = ModuleManifest(
        module_id="phoenix_a_core",
        version="1.0.0",
        runtime_api="0.9",  # older than CURRENT_RUNTIME_API_VERSION
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
    )
    with pytest.raises(ModuleVersionIncompatibleError, match="runtime_api"):
        check_manifest_compatible(manifest)


def test_newer_runtime_api_also_rejected():
    """
    Exact-match policy means a module built for a FUTURE runtime version
    is rejected just as readily as an outdated one — the runtime never
    assumes forward compatibility it hasn't verified.
    """
    manifest = ModuleManifest(
        module_id="phoenix_a_core",
        version="1.0.0",
        runtime_api="2.0",  # newer than CURRENT_RUNTIME_API_VERSION
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
    )
    with pytest.raises(ModuleVersionIncompatibleError, match="runtime_api"):
        check_manifest_compatible(manifest)


def test_mismatched_context_schema_rejected():
    manifest = ModuleManifest(
        module_id="phoenix_a_core",
        version="1.0.0",
        runtime_api=CURRENT_RUNTIME_API_VERSION,
        context_schema="99",
    )
    with pytest.raises(ModuleVersionIncompatibleError, match="context_schema"):
        check_manifest_compatible(manifest)


def test_runtime_api_checked_before_context_schema():
    """
    When both are mismatched, the runtime_api error should surface first
    (documents actual check ordering — useful for anyone debugging a
    double-mismatch, since only one error is raised at a time).
    """
    manifest = ModuleManifest(
        module_id="phoenix_a_core",
        version="1.0.0",
        runtime_api="0.1",
        context_schema="99",
    )
    with pytest.raises(ModuleVersionIncompatibleError, match="runtime_api"):
        check_manifest_compatible(manifest)


def test_error_message_includes_both_declared_and_actual_versions():
    """
    A compatibility error should be immediately diagnosable from the
    message alone — both what the module claimed and what the runtime
    actually requires.
    """
    manifest = ModuleManifest(
        module_id="ancient_module",
        version="0.0.1",
        runtime_api="0.1",
        context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
    )
    with pytest.raises(ModuleVersionIncompatibleError) as exc_info:
        check_manifest_compatible(manifest)

    message = str(exc_info.value)
    assert "ancient_module" in message
    assert "0.1" in message
    assert CURRENT_RUNTIME_API_VERSION in message
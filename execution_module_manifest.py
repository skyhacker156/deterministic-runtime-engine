"""
Execution Module Manifest - Sentinel Framework
(execution_module_manifest.py)

Answers a question the registry alone cannot: not just "is this module
compliant," but "is this module compliant against THIS runtime's current
API and context schema." A manifest is compared against the runtime's own
declared versions at registration time — the module's claim is checked,
never trusted at face value, matching the verification discipline already
established for capabilities in execution_module_registry.py.

Versioning policy (deliberately conservative): exact match required on
both runtime_api and context_schema. A module built against an older or
newer runtime API is rejected outright rather than allowed to register
under an assumed-compatible range. This can be relaxed to range-based
compatibility later, as an explicit, documented change — not as a
default.
"""

from dataclasses import dataclass, field
from typing import Tuple

# The runtime's own current versions. Bump these explicitly, as part of
# the same commit that introduces a breaking change to the engine's
# execution API or to KernelStateEnvelope/CoreExecutionFrame's shape —
# per ARCHITECTURE_FREEZE_v1.5.md Section 7 (amendment rule).
CURRENT_RUNTIME_API_VERSION = "1.0"
CURRENT_CONTEXT_SCHEMA_VERSION = "1"

KNOWN_CAPABILITIES = frozenset({"deterministic", "replayable", "audit_safe"})


class ManifestValidationError(Exception):
    """Raised when a ModuleManifest is malformed."""
    pass


class ModuleVersionIncompatibleError(Exception):
    """Raised when a manifest's runtime_api or context_schema does not
    match the runtime's current versions."""
    pass


@dataclass(frozen=True)
class ModuleManifest:
    """
    Declares what a module claims about itself. This is the module
    author's INPUT to compatibility checking, not the final word — the
    registry (via check_manifest_compatible below) is what actually
    decides whether the claim holds.
    """
    module_id: str
    version: str
    runtime_api: str
    context_schema: str
    capabilities: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or not self.module_id.strip():
            raise ManifestValidationError("module_id must be a non-empty string")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ManifestValidationError("version must be a non-empty string")
        if not isinstance(self.runtime_api, str) or not self.runtime_api.strip():
            raise ManifestValidationError("runtime_api must be a non-empty string")
        if not isinstance(self.context_schema, str) or not self.context_schema.strip():
            raise ManifestValidationError("context_schema must be a non-empty string")

        unknown = set(self.capabilities) - KNOWN_CAPABILITIES
        if unknown:
            raise ManifestValidationError(
                f"Unknown capability declaration(s): {sorted(unknown)}. "
                f"Known capabilities: {sorted(KNOWN_CAPABILITIES)}."
            )


def check_manifest_compatible(manifest: ModuleManifest) -> None:
    """
    Compares a manifest's claimed runtime_api and context_schema against
    the runtime's actual current versions. This is the check — a manifest
    is never trusted just because it exists.

    Raises:
        ModuleVersionIncompatibleError: on any mismatch.
    """
    if manifest.runtime_api != CURRENT_RUNTIME_API_VERSION:
        raise ModuleVersionIncompatibleError(
            f"Module '{manifest.module_id}' declares runtime_api="
            f"'{manifest.runtime_api}', but this runtime is at "
            f"'{CURRENT_RUNTIME_API_VERSION}'. Exact match required."
        )
    if manifest.context_schema != CURRENT_CONTEXT_SCHEMA_VERSION:
        raise ModuleVersionIncompatibleError(
            f"Module '{manifest.module_id}' declares context_schema="
            f"'{manifest.context_schema}', but this runtime is at "
            f"'{CURRENT_CONTEXT_SCHEMA_VERSION}'. Exact match required."
        )
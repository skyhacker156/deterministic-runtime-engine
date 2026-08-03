"""
Execution Module Registry - Sentinel Framework
(execution_module_registry.py)

Responsibility: the engine no longer needs to know how modules exist.
The registry owns registration, lookup, and capability verification, so
"can this module run" is answered before "run this module" is ever asked.

Per execution_module_spec.md and ARCHITECTURE_FREEZE_v1.5.md's extension
rule ("no component reconstructs another component's hash"): a module's
declared capabilities are NOT trusted at face value. By default, a module
must pass the full compliance suite (module_compliance_checks.py — the same
single source of truth test_module_contract_compliance.py runs) at
registration time before its capabilities are accepted. A module registered
with verify=False is explicitly marked unverified — the registry never
silently upgrades an unverified module to a trusted one.

Constraint inherited from module_compliance_checks.py: any module registered
with verify=True must be zero-argument-constructible (module_cls()), since
replay-determinism checking requires building two fully independent
instances.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from execution_module_contract import ExecutionModule


class DuplicateModuleError(Exception):
    """Raised when attempting to register a module_id that already exists."""
    pass


class ModuleNotFoundError(Exception):
    """Raised when resolving an unregistered module_id."""
    pass


class ModuleVersionError(Exception):
    """Raised when a module's declared version is incompatible with the registry."""
    pass


@dataclass(frozen=True)
class ModuleCapabilities:
    """
    Capabilities as CONFIRMED by the registry, not as self-reported by the
    module. Only produced by the registry itself, never constructed
    directly from a module's own claims.
    """
    deterministic: bool
    replayable: bool
    audit_safe: bool
    verified: bool  # False if registered with verify=False


@dataclass(frozen=True)
class RegisteredModuleEntry:
    module: ExecutionModule
    module_id: str
    module_version: str
    capabilities: ModuleCapabilities


class ExecutionModuleRegistry:
    """
    Stateless-per-lookup registry: registration is a one-time administrative
    act (not part of the deterministic execution path itself), but lookup
    is a pure, deterministic function of module_id -> the same registered
    instance every time.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, RegisteredModuleEntry] = {}

    def register(
        self,
        module: ExecutionModule,
        module_version: str = "1.0.0",
        verify: bool = True,
    ) -> None:
        """
        Registers a module under its own module_id.

        Raises:
            DuplicateModuleError: module_id already registered.
            ModuleComplianceError (from module_compliance_checks): verify=True
                and the module fails the shared compliance suite.
        """
        module_id = module.module_id

        if module_id in self._entries:
            raise DuplicateModuleError(
                f"Module ID '{module_id}' is already registered."
            )

        if verify:
            self._run_compliance_check(module)
            capabilities = ModuleCapabilities(
                deterministic=True,
                replayable=True,
                audit_safe=True,
                verified=True,
            )
        else:
            capabilities = ModuleCapabilities(
                deterministic=False,
                replayable=False,
                audit_safe=False,
                verified=False,
            )

        self._entries[module_id] = RegisteredModuleEntry(
            module=module,
            module_id=module_id,
            module_version=module_version,
            capabilities=capabilities,
        )

    def resolve(self, module_id: str) -> ExecutionModule:
        """
        Returns the exact registered module instance for module_id.

        Raises:
            ModuleNotFoundError: module_id is not registered.
        """
        entry = self._entries.get(module_id)
        if entry is None:
            raise ModuleNotFoundError(f"No module registered under ID '{module_id}'.")
        return entry.module

    def capabilities(self, module_id: str) -> ModuleCapabilities:
        """
        Returns the registry-confirmed (or explicitly unverified)
        capabilities for module_id.

        Raises:
            ModuleNotFoundError: module_id is not registered.
        """
        entry = self._entries.get(module_id)
        if entry is None:
            raise ModuleNotFoundError(f"No module registered under ID '{module_id}'.")
        return entry.capabilities

    def is_registered(self, module_id: str) -> bool:
        return module_id in self._entries

    def registered_ids(self) -> tuple:
        """Deterministic (sorted) view of all registered module IDs."""
        return tuple(sorted(self._entries.keys()))

    def _run_compliance_check(self, module: ExecutionModule) -> None:
        """
        Delegates to the shared compliance suite in module_compliance_checks.py
        — the same checks test_module_contract_compliance.py runs, so
        registration-time verification and the standalone test suite can
        never silently drift apart.
        """
        from module_compliance_checks import run_full_compliance_suite
        run_full_compliance_suite(type(module))
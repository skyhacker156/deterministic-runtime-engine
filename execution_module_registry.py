"""
Execution Module Registry - Sentinel Framework
(execution_module_registry.py)

Responsibility: the engine no longer needs to know how modules exist.
The registry owns registration, lookup, and capability verification, so
"can this module run" is answered before "run this module" is ever asked.

Wiring update: resolve() now consults ModuleLifecycleManager before
returning a module. Registry presence alone is no longer sufficient —
a module that exists in the registry but is FAULTED or RETIRED in the
lifecycle manager must not be resolvable for execution. This closes the
gap named when the lifecycle manager was first built: a faulted module
sitting in the registry with no lifecycle check could still be dispatched
to by the engine.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from execution_module_contract import ExecutionModule
from module_lifecycle import ModuleLifecycleManager, ModuleState


class DuplicateModuleError(Exception):
    """Raised when attempting to register a module_id that already exists."""
    pass


class ModuleNotFoundError(Exception):
    """Raised when resolving an unregistered module_id."""
    pass


class ModuleNotActiveError(Exception):
    """Raised when resolving a module that exists in the registry but is
    not currently ACTIVE in the lifecycle manager (e.g. FAULTED, RETIRED,
    or never activated)."""
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
    instance every time, PROVIDED the module is currently ACTIVE in the
    lifecycle manager.

    The registry now owns a ModuleLifecycleManager internally. Registration
    automatically advances a module through DISCOVERED -> VALIDATED ->
    REGISTERED. Activation is a SEPARATE, explicit step (activate()) —
    matching module_lifecycle.py's design that REGISTERED does not imply
    ACTIVE. resolve() only succeeds once a module has been explicitly
    activated.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, RegisteredModuleEntry] = {}
        self._lifecycle = ModuleLifecycleManager()

    def register(
        self,
        module: ExecutionModule,
        module_version: str = "1.0.0",
        verify: bool = True,
    ) -> None:
        """
        Registers a module under its own module_id, advancing it through
        DISCOVERED -> VALIDATED -> REGISTERED in the lifecycle manager.
        Does NOT activate the module — call activate() separately before
        resolve() will succeed.

        Raises:
            DuplicateModuleError: module_id already registered.
            ModuleComplianceError (from module_compliance_checks): verify=True
                and the module fails the shared compliance suite. On failure,
                the module is left in VALIDATED lifecycle state (registration
                did not complete) and is NOT added to the registry's entries.
        """
        module_id = module.module_id

        if module_id in self._entries:
            raise DuplicateModuleError(
                f"Module ID '{module_id}' is already registered."
            )

        self._lifecycle.discover(module_id)
        # NOTE: manifest validation (v1.8) is not yet wired into this
        # transition — mark_validated is currently called unconditionally
        # after discover(). Wiring ModuleManifest/check_manifest_compatible
        # in here is the natural next gap to close, tracked separately.
        self._lifecycle.mark_validated(module_id)

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

        self._lifecycle.mark_registered(module_id)

        self._entries[module_id] = RegisteredModuleEntry(
            module=module,
            module_id=module_id,
            module_version=module_version,
            capabilities=capabilities,
        )

    def activate(self, module_id: str) -> None:
        """
        Explicit administrative action: makes a REGISTERED module eligible
        for resolve(). Matches ModuleLifecycleManager.activate()'s
        semantics exactly — registration passing compliance does not by
        itself grant execution eligibility.

        Raises:
            ModuleNotFoundError: module_id was never registered.
            InvalidLifecycleTransitionError (from module_lifecycle): module
                is not currently in REGISTERED state (e.g. already ACTIVE,
                or FAULTED with no recovery path).
        """
        if module_id not in self._entries:
            raise ModuleNotFoundError(
                f"Cannot activate '{module_id}': not registered."
            )
        self._lifecycle.activate(module_id)

    def fault(self, module_id: str, reason: str) -> None:
        """
        Marks a currently-ACTIVE module as FAULTED, immediately making it
        unresolvable. Use this when a module is found to violate its
        contract after having been activated.

        Raises:
            ModuleNotFoundError: module_id was never registered.
            InvalidLifecycleTransitionError: module is not currently ACTIVE.
        """
        if module_id not in self._entries:
            raise ModuleNotFoundError(
                f"Cannot fault '{module_id}': not registered."
            )
        self._lifecycle.mark_faulted(module_id, reason)

    def retire(self, module_id: str) -> None:
        """
        Explicit, deliberate, terminal retirement. Immediately makes the
        module unresolvable, with no recovery path.

        Raises:
            ModuleNotFoundError: module_id was never registered.
        """
        if module_id not in self._entries:
            raise ModuleNotFoundError(
                f"Cannot retire '{module_id}': not registered."
            )
        self._lifecycle.retire(module_id)

    def resolve(self, module_id: str) -> ExecutionModule:
        """
        Returns the registered module instance for module_id, ONLY if it
        is currently ACTIVE in the lifecycle manager.

        Raises:
            ModuleNotFoundError: module_id is not registered at all.
            ModuleNotActiveError: module_id is registered but not currently
                ACTIVE (e.g. still just REGISTERED and never activated, or
                FAULTED, or RETIRED).
        """
        entry = self._entries.get(module_id)
        if entry is None:
            raise ModuleNotFoundError(f"No module registered under ID '{module_id}'.")

        if not self._lifecycle.is_active(module_id):
            record = self._lifecycle.get_record(module_id)
            raise ModuleNotActiveError(
                f"Module '{module_id}' is registered but not ACTIVE "
                f"(current lifecycle state: {record.state.name}"
                + (f", fault_reason: {record.fault_reason}" if record.fault_reason else "")
                + "). It cannot be resolved for execution."
            )

        return entry.module

    def capabilities(self, module_id: str) -> ModuleCapabilities:
        """
        Returns the registry-confirmed (or explicitly unverified)
        capabilities for module_id. Available regardless of lifecycle
        state — capabilities describe what was confirmed at registration
        time, independent of whether the module is currently eligible to run.

        Raises:
            ModuleNotFoundError: module_id is not registered.
        """
        entry = self._entries.get(module_id)
        if entry is None:
            raise ModuleNotFoundError(f"No module registered under ID '{module_id}'.")
        return entry.capabilities

    def lifecycle_state(self, module_id: str) -> ModuleState:
        """Convenience accessor for the module's current lifecycle state."""
        return self._lifecycle.get_record(module_id).state

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
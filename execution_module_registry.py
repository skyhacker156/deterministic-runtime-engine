"""
Execution Module Registry - Sentinel Framework
(execution_module_registry.py)

v2.7: registration attempt telemetry.

The v2.6 two-phase register() (Phase 1: gather evidence with zero
mutation; Phase 2: commit only once every check has passed) is
UNCHANGED by this revision. That model is correct and is proven by
test_registration_atomicity.py:
    - failed registration leaves no lifecycle record, no registry entry
    - the same module_id can be retried immediately after a failure
    - successful registration is atomic (all-or-nothing)
    - duplicate protection survives retries

What v2.6 did NOT do is record that a failed attempt ever happened.
Nothing about the "leave no trace" guarantee requires that -- "no trace
in the operational registry / lifecycle manager" and "no trace
anywhere at all" are two different properties, and only the first one
is actually load-bearing for the atomicity invariant.

v2.7 adds a separate, append-only history of registration attempts
(ModuleRegistrationAttemptRecord, from module_registration_audit.py)
that is populated on every register() call -- success or failure --
without touching self._lifecycle or self._entries semantics at all.
This is deliberately NOT ExecutionAuditRecord: that type requires
frame-execution fields (sequence_id, input_hash, prior_state_hash,
output_hash) that have no real referent at registration time, and
forcing a registration attempt through that schema would mean
inventing stub values for fields that don't apply -- exactly the kind
of placeholder-as-real-data pattern flagged elsewhere in this corpus
as a problem, not a solution.

Net effect:
    Safety:        FAILED registration never enters the operational
                    registry or lifecycle manager (unchanged from v2.6).
    Observability:  FAILED registration is never silently discarded --
                    it is captured as a ModuleRegistrationAttemptRecord,
                    queryable via registration_history(module_id).

ModuleComplianceError note: that class is defined in
module_compliance_checks.py and inherits from ModuleRegistrationError
AT ITS OWN DEFINITION SITE there (imported from this module). It is NOT
re-parented here at runtime -- an earlier version of this file tried
ModuleComplianceError.__bases__ = (ModuleRegistrationError,) and that
raises TypeError, because CPython rejects a __bases__ reassignment
when the new base has a different instance layout than the old one.
"""

import hashlib
import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from execution_module_contract import ExecutionModule
from module_lifecycle import ModuleLifecycleManager, ModuleState
from execution_module_manifest import (
    ModuleManifest,
    check_manifest_compatible,
    ModuleVersionIncompatibleError,
    CURRENT_RUNTIME_API_VERSION,
    CURRENT_CONTEXT_SCHEMA_VERSION,
)
from module_registration_audit import ModuleRegistrationAttemptRecord


class DuplicateModuleError(Exception):
    pass


class ModuleNotFoundError(Exception):
    pass


class ModuleNotActiveError(Exception):
    pass


class ModuleRegistrationError(Exception):
    """
    Shared base for Phase-1 registration failure modes (manifest
    incompatibility, compliance failure). ModuleVersionError (below)
    and ModuleComplianceError (defined in module_compliance_checks.py)
    both inherit from this, so register()'s Phase 1 can catch any
    registration failure with a single except clause. Callers that only
    ever caught the two concrete types are unaffected.
    """
    pass


class ModuleVersionError(ModuleRegistrationError):
    pass


@dataclass(frozen=True)
class ModuleCapabilities:
    """Capabilities as CONFIRMED by the registry, never self-reported."""
    deterministic: bool
    replayable: bool
    audit_safe: bool
    verified: bool

    capability_hash: bytes = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_hash", self._compute_hash())

    def _compute_hash(self) -> bytes:
        flags = (
            (int(self.deterministic) << 3)
            | (int(self.replayable) << 2)
            | (int(self.audit_safe) << 1)
            | int(self.verified)
        )
        return hashlib.sha256(struct.pack(">BB", 1, flags)).digest()


@dataclass(frozen=True)
class RegisteredModuleEntry:
    module: ExecutionModule
    module_id: str
    module_version: str
    capabilities: ModuleCapabilities
    manifest: ModuleManifest


class ExecutionModuleRegistry:
    """
    Registration is a one-time administrative act. Lookup (resolve) is a
    pure, deterministic function of module_id -> the same registered
    instance every time, PROVIDED the module is currently ACTIVE in the
    lifecycle manager.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, RegisteredModuleEntry] = {}
        self._lifecycle = ModuleLifecycleManager()
        self._registration_attempts: List[ModuleRegistrationAttemptRecord] = []

    def _default_manifest(self, module: ExecutionModule) -> ModuleManifest:
        return ModuleManifest(
            module_id=module.module_id,
            version="1.0.0",
            runtime_api=CURRENT_RUNTIME_API_VERSION,
            context_schema=CURRENT_CONTEXT_SCHEMA_VERSION,
        )

    def _record_attempt(
        self,
        module_id: str,
        success: bool,
        reason: Optional[str],
        manifest_hash: Optional[bytes],
    ) -> None:
        self._registration_attempts.append(
            ModuleRegistrationAttemptRecord(
                module_id=module_id,
                attempted_at_ns=time.time_ns(),
                success=success,
                reason=reason,
                manifest_hash=manifest_hash,
            )
        )

    def register(
        self,
        module: ExecutionModule,
        manifest: Optional[ModuleManifest] = None,
        verify: bool = True,
    ) -> None:
        """
        Raises:
            DuplicateModuleError: module_id already registered.
            ModuleVersionError: identity mismatch or manifest incompatible.
            ModuleComplianceError: verify=True and compliance suite fails.
            (both ModuleVersionError and ModuleComplianceError subclass
            ModuleRegistrationError)

        On ANY Phase-1 failure, self._lifecycle and self._entries are
        left completely untouched -- no partial state, no leftover
        lifecycle record. The same module_id may be retried immediately.
        This guarantee is unchanged from v2.6.

        Separately -- new in v2.7 -- every attempt, success or failure,
        is appended to self._registration_attempts. This does not affect
        is_registered(), lifecycle_state(), or resolve() in any way; it
        is a pure side-channel for observability. See
        registration_history().
        """
        module_id = module.module_id

        if module_id in self._entries:
            raise DuplicateModuleError(
                f"Module ID '{module_id}' is already registered."
            )

        # ---- Phase 1: gather evidence. No mutation of self._lifecycle
        # or self._entries below this point until Phase 2 begins. ----

        effective_manifest = manifest if manifest is not None else self._default_manifest(module)
        manifest_hash = hashlib.sha256(
            f"{effective_manifest.module_id}|{effective_manifest.version}|"
            f"{effective_manifest.runtime_api}|{effective_manifest.context_schema}"
            .encode("utf-8")
        ).digest()

        try:
            if effective_manifest.module_id != module_id:
                raise ModuleVersionError(
                    f"Manifest module_id '{effective_manifest.module_id}' does not "
                    f"match module.module_id '{module_id}'."
                )

            try:
                check_manifest_compatible(effective_manifest)
            except ModuleVersionIncompatibleError as e:
                raise ModuleVersionError(str(e)) from e

            if verify:
                self._run_compliance_check(module)  # raises ModuleComplianceError on failure
                capabilities = ModuleCapabilities(
                    deterministic=True, replayable=True, audit_safe=True, verified=True,
                )
            else:
                capabilities = ModuleCapabilities(
                    deterministic=False, replayable=False, audit_safe=False, verified=False,
                )

        except ModuleRegistrationError as e:
            self._record_attempt(
                module_id=module_id,
                success=False,
                reason=str(e),
                manifest_hash=manifest_hash,
            )
            raise

        entry = RegisteredModuleEntry(
            module=module,
            module_id=module_id,
            module_version=effective_manifest.version,
            capabilities=capabilities,
            manifest=effective_manifest,
        )

        # ---- Phase 2: commit. Every check above already passed; this
        # phase only performs state transitions and dict insertion.
        # Unchanged from v2.6. ----

        self._lifecycle.discover(module_id)
        self._lifecycle.mark_validated(module_id)
        self._lifecycle.mark_registered(module_id)
        self._entries[module_id] = entry

        self._record_attempt(
            module_id=module_id,
            success=True,
            reason=None,
            manifest_hash=manifest_hash,
        )

    def registration_history(self, module_id: str) -> tuple:
        """
        Returns every recorded registration attempt (success or
        failure) for this module_id, in the order they occurred.
        Read-only, append-only -- returns an empty tuple if no attempt
        was ever made under this module_id (this is NOT an error, unlike
        the other module_id lookups on this class, since asking about
        attempt history for a module that was never touched is a
        perfectly ordinary query, not a caller mistake).
        """
        return tuple(
            rec for rec in self._registration_attempts if rec.module_id == module_id
        )

    def activate(self, module_id: str) -> None:
        if module_id not in self._entries:
            raise ModuleNotFoundError(f"Cannot activate '{module_id}': not registered.")
        self._lifecycle.activate(module_id)

    def fault(self, module_id: str, reason: str) -> None:
        if module_id not in self._entries:
            raise ModuleNotFoundError(f"Cannot fault '{module_id}': not registered.")
        self._lifecycle.mark_faulted(module_id, reason)

    def retire(self, module_id: str) -> None:
        if module_id not in self._entries:
            raise ModuleNotFoundError(f"Cannot retire '{module_id}': not registered.")
        self._lifecycle.retire(module_id)

    def resolve(self, module_id: str) -> ExecutionModule:
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
        entry = self._entries.get(module_id)
        if entry is None:
            raise ModuleNotFoundError(f"No module registered under ID '{module_id}'.")
        return entry.capabilities

    def manifest(self, module_id: str) -> ModuleManifest:
        entry = self._entries.get(module_id)
        if entry is None:
            raise ModuleNotFoundError(f"No module registered under ID '{module_id}'.")
        return entry.manifest

    def lifecycle_state(self, module_id: str) -> ModuleState:
        return self._lifecycle.get_record(module_id).state

    def is_registered(self, module_id: str) -> bool:
        return module_id in self._entries

    def registered_ids(self) -> tuple:
        return tuple(sorted(self._entries.keys()))

    def _run_compliance_check(self, module: ExecutionModule) -> None:
        from module_compliance_checks import run_full_compliance_suite
        run_full_compliance_suite(type(module))
"""
Module Lifecycle State Machine - Sentinel Framework
(module_lifecycle.py)

Applies the same invariant philosophy already proven in
execution_kernel_state.py (KernelStateMachine) to module lifecycle: illegal
transitions are rejected outright, and every transition is tied to a
specific, checkable event — never inferred from context.

Lifecycle is intentionally separate from ExecutionModuleRegistry. The
registry answers "does this module exist and is it compliant." The
lifecycle manager answers "is this module currently ALLOWED to execute
right now" — a module can exist in the registry while being FAULTED or
RETIRED in the lifecycle manager, and the engine must consult lifecycle
state, not registry presence alone, before dispatching to a module.

v2 (2026-08-06): ModuleState moved to module_state.py -- see that
module's own docstring for why (test_verifier_runtime_isolation.py
caught causal_history_verifier.py, via ExecutionPolicyDecision's own
type dependency, transitively importing this entire file --
ModuleLifecycleManager included -- merely to get the ModuleState enum
type). Imported here instead of defined here -- ModuleLifecycleManager's
own behavior is completely unchanged; only the enum's location moved,
and it is re-exported here so every existing
`from module_lifecycle import ModuleState` import continues to work
without modification.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

from module_state import ModuleState


class ModuleLifecycleError(Exception):
    """Base exception for module lifecycle violations."""
    pass


class InvalidLifecycleTransitionError(ModuleLifecycleError):
    """Raised when an illegal lifecycle transition is attempted."""
    pass


# Explicit adjacency map, mirroring KernelStateMachine.VALID_TRANSITIONS.
VALID_TRANSITIONS: Dict[ModuleState, FrozenSet[ModuleState]] = {
    ModuleState.DISCOVERED: frozenset({ModuleState.VALIDATED, ModuleState.RETIRED}),
    ModuleState.VALIDATED: frozenset({ModuleState.REGISTERED, ModuleState.RETIRED}),
    ModuleState.REGISTERED: frozenset({ModuleState.ACTIVE, ModuleState.RETIRED}),
    ModuleState.ACTIVE: frozenset({ModuleState.FAULTED, ModuleState.RETIRED}),
    ModuleState.FAULTED: frozenset({ModuleState.RETIRED}),  # no automatic recovery
    ModuleState.RETIRED: frozenset(),  # terminal, no exceptions
}


@dataclass(frozen=True)
class ModuleLifecycleRecord:
    """Immutable snapshot of a single module's lifecycle state."""
    module_id: str
    state: ModuleState
    fault_reason: Optional[str] = None


class ModuleLifecycleManager:
    """
    Tracks lifecycle state per module_id. Every transition is an explicit
    method call tied to a specific triggering event — there is no generic
    "set state" method, matching KernelStateMachine's design: the caller
    names *why* a transition is happening, not just *what* the new state is.
    """

    def __init__(self) -> None:
        self._states: Dict[str, ModuleState] = {}
        self._fault_reasons: Dict[str, Optional[str]] = {}

    def discover(self, module_id: str) -> ModuleLifecycleRecord:
        """A module becomes known to the lifecycle manager. Idempotent
        entry point — first time seeing this module_id."""
        if module_id in self._states:
            raise ModuleLifecycleError(
                f"Module '{module_id}' already has a lifecycle record; "
                f"discover() may only be called once per module_id."
            )
        self._states[module_id] = ModuleState.DISCOVERED
        self._fault_reasons[module_id] = None
        return self.get_record(module_id)

    def mark_validated(self, module_id: str) -> ModuleLifecycleRecord:
        """
        Call after ModuleManifest construction + check_manifest_compatible
        both succeed for this module.
        """
        return self._transition(module_id, ModuleState.VALIDATED)

    def mark_registered(self, module_id: str) -> ModuleLifecycleRecord:
        """
        Call after run_full_compliance_suite passes for this module
        (i.e., ExecutionModuleRegistry.register(verify=True) succeeded).
        """
        return self._transition(module_id, ModuleState.REGISTERED)

    def activate(self, module_id: str) -> ModuleLifecycleRecord:
        """
        Explicit administrative action: a REGISTERED module becomes
        eligible for dispatch. Deliberately not automatic — registration
        compliance-passing does not itself grant execution eligibility;
        that is a separate, named decision.
        """
        return self._transition(module_id, ModuleState.ACTIVE)

    def mark_faulted(self, module_id: str, reason: str) -> ModuleLifecycleRecord:
        """
        Call when an ACTIVE module is found to violate its contract after
        having been activated — e.g., a re-run compliance check fails, or
        an external signal (not a per-frame ExecutionResult failure, which
        faults the KERNEL per ARCHITECTURE_FREEZE_v1.5.md Section 1, not
        the module) indicates this module should no longer be trusted.
        """
        if not reason or not reason.strip():
            raise ModuleLifecycleError("mark_faulted requires a non-empty reason.")
        record = self._transition(module_id, ModuleState.FAULTED)
        self._fault_reasons[module_id] = reason
        return self.get_record(module_id)

    def retire(self, module_id: str) -> ModuleLifecycleRecord:
        """Explicit, deliberate administrative retirement. Terminal."""
        return self._transition(module_id, ModuleState.RETIRED)

    def is_active(self, module_id: str) -> bool:
        """The one question the engine should actually ask before dispatch."""
        return self._states.get(module_id) == ModuleState.ACTIVE

    def get_record(self, module_id: str) -> ModuleLifecycleRecord:
        if module_id not in self._states:
            raise ModuleLifecycleError(f"No lifecycle record for module '{module_id}'.")
        return ModuleLifecycleRecord(
            module_id=module_id,
            state=self._states[module_id],
            fault_reason=self._fault_reasons[module_id],
        )

    def _transition(self, module_id: str, new_state: ModuleState) -> ModuleLifecycleRecord:
        if module_id not in self._states:
            raise ModuleLifecycleError(
                f"Module '{module_id}' has no lifecycle record. Call discover() first."
            )

        current_state = self._states[module_id]
        allowed = VALID_TRANSITIONS.get(current_state, frozenset())

        if new_state not in allowed:
            raise InvalidLifecycleTransitionError(
                f"Illegal lifecycle transition for '{module_id}': "
                f"{current_state.name} -> {new_state.name}. "
                f"Allowed from {current_state.name}: "
                f"{sorted(s.name for s in allowed) if allowed else 'none (terminal)'}."
            )

        self._states[module_id] = new_state
        return self.get_record(module_id)

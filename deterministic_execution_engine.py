"""
Deterministic Execution Engine & State Evolution Operator - Sentinel Framework
Implements Step 2 of Phase 2 (Execution Semantics): f(S_t, Frame_k) -> (S_{t+1}, ExecutionResult_k)

v2.4: Optional authorization gate inserted into the existing causal chain.

Hard invariant: this module imports NOTHING from execution_policy.py,
execution_policy_state.py, or execution_authorizer.py. The authorizer is
treated as an opaque collaborator via duck typing (mirroring how
ExecutionModule.execute() is called without the engine knowing anything
about a module's internal transform logic) — the engine only ever calls
authorizer.authorize(module_id) and authorizer.record_execution(decision),
and only ever reads decision.allowed. It has no knowledge of policy rules,
invocation counts, policy_hash, or decision_hash construction. Those
remain entirely below the authorizer boundary.

Insertion point: the authorization check happens after frame integrity
verification (so a corrupt frame fails on integrity grounds, not
authorization grounds) but BEFORE the kernel transitions to PROCESSING and
BEFORE record_frame_execution() advances the sequence counter. A denied
frame therefore leaves kernel state completely untouched — the kernel
remains exactly as it was before process_frame() was called, as if the
frame was never seen. This means a denied frame's seq_id is NOT consumed
and may be legitimately retried later (e.g. after a policy change) without
violating monotonic sequencing.

Denial is signaled by raising AuthorizationDeniedError, not by fabricating
an ExecutionResult. A fabricated ExecutionResult would imply the module
was dispatched and reported failure, which is false — the module was
never called. This mirrors StateIntegrityError's existing pattern: a
distinct, specific exception type for a distinct causal event, carrying
enough information (the full ExecutionPolicyDecision) for the caller to
inspect why.

Audit-record expansion for denials (i.e. whether a denial gets a
permanent audit-chain entry) is explicitly deferred — see v2.4 design
discussion. Denials are currently visible only via the raised exception,
not via engine.audit_log.
"""

from typing import Any, List, Optional, Tuple

from execution_kernel_state import (
    KernelState,
    KernelStateMachine,
    KernelStateEnvelope,
    InvalidStateTransitionError,
    StateMachineError,
)
from execution_kernel_contract import CoreExecutionFrame
from execution_module_contract import ExecutionModule, ExecutionResult
from execution_audit_contract import ExecutionAuditRecord


class ExecutionEngineError(Exception):
    """Base exception for deterministic execution engine failures."""
    pass


class StateIntegrityError(ExecutionEngineError):
    """Raised when incoming frame provenance verification fails."""
    pass


class AuthorizationDeniedError(ExecutionEngineError):
    """
    Raised when an injected authorizer denies execution for a frame.

    Carries the full decision object (opaque to the engine beyond
    .allowed, .module_id, .reason — read here purely for error message
    construction, never inspected for policy internals) so the caller can
    examine why the request was denied without the engine needing any
    knowledge of what the decision object actually contains.

    Kernel state is left completely untouched when this is raised — see
    module docstring.
    """

    def __init__(self, decision: Any) -> None:
        self.decision = decision
        module_id = getattr(decision, "module_id", "<unknown>")
        reason = getattr(decision, "reason", "<no reason provided>")
        super().__init__(
            "Execution denied for module '" + str(module_id) + "': " + str(reason)
        )


class DeterministicExecutionEngine:
    def __init__(
        self,
        module: Optional[ExecutionModule] = None,
        authorizer: Optional[Any] = None,
    ) -> None:
        """
        authorizer: optional, opaque collaborator. If provided, must
        expose:
            authorize(module_id: str) -> object with a truthy/falsy
                `.allowed` attribute, a `.module_id` attribute, and a
                `.reason` attribute.
            record_execution(decision) -> Any (return value ignored by
                the engine).
        Defaults to None for full backward compatibility — every existing
        caller that never passes authorizer behaves exactly as before
        v2.4, with zero authorization checks performed.
        """
        self._state_machine = KernelStateMachine(initial_state=KernelState.UNINITIALIZED)
        self._module = module
        self._authorizer = authorizer
        self._audit_log: List[ExecutionAuditRecord] = []

    @property
    def state_machine(self) -> KernelStateMachine:
        return self._state_machine

    @property
    def module(self) -> Optional[ExecutionModule]:
        return self._module

    @property
    def authorizer(self) -> Optional[Any]:
        return self._authorizer

    @property
    def audit_log(self) -> Tuple[ExecutionAuditRecord, ...]:
        return tuple(self._audit_log)

    def initialize(self) -> KernelStateEnvelope:
        self._state_machine.transition_to(KernelState.INITIALIZING)
        return self._state_machine.transition_to(KernelState.READY)

    def process_frame(self, frame: CoreExecutionFrame) -> Tuple[KernelStateEnvelope, Optional[ExecutionResult]]:
        current_state = self._state_machine.current_state

        if current_state not in (KernelState.READY, KernelState.PROCESSING):
            raise ExecutionEngineError(
                "Cannot process frame in state " + current_state.name + ". Must be in READY or PROCESSING."
            )

        # 1. Frame integrity — unchanged from pre-v2.4. A corrupt frame
        # fails here regardless of authorization state.
        try:
            frame.verify_integrity()
        except ValueError as ve:
            if self._state_machine.current_state != KernelState.FAULTED:
                try:
                    self._state_machine.transition_to(
                        KernelState.FAULTED,
                        reason="PROVENANCE_FAILURE: Frame " + str(frame.seq_id) + " failed integrity verification."
                    )
                except InvalidStateTransitionError:
                    pass
            raise StateIntegrityError(
                "Frame " + str(frame.seq_id) + " failed provenance hash verification."
            ) from ve

        prior_envelope = self._state_machine.get_envelope()

        # 2. Authorization gate — v2.4 insertion point. Deliberately
        # placed BEFORE the PROCESSING transition and BEFORE
        # record_frame_execution(), so a denial leaves kernel state
        # completely untouched and does not consume this frame's seq_id.
        decision = None
        if self._authorizer is not None and self._module is not None:
            decision = self._authorizer.authorize(self._module.module_id)
            if not decision.allowed:
                raise AuthorizationDeniedError(decision)

        # 3. Existing PROCESSING transition and sequence tracking —
        # unchanged, now only reached once authorization (if any) has
        # already passed.
        if current_state == KernelState.READY:
            self._state_machine.transition_to(KernelState.PROCESSING)

        try:
            self._state_machine.record_frame_execution(frame.seq_id)

            result = None
            if self._module is not None:
                result = self._module.execute(frame, prior_envelope)

                # --- Audit emission: unchanged from Step 2 ---
                audit_record = ExecutionAuditRecord.from_execution(
                    sequence_id=frame.seq_id,
                    input_hash=frame.provenance_hash,
                    prior_state_hash=prior_envelope.state_hash,
                    frame_timestamp_ns=frame.timestamp_ns,
                    module_id=self._module.module_id,
                    result=result,
                )
                self._audit_log.append(audit_record)
                # --- end audit emission ---

                # 4. record_execution — called once dispatch has actually
                # occurred, regardless of the module's reported outcome
                # (Option A, locked in at v2.3: failures consume quota
                # the same as successes, so a module cannot evade rate
                # limiting by failing on purpose). Called BEFORE the
                # success check below, so it always fires for any frame
                # that reached this point, whether the module ultimately
                # succeeds or fails.
                if self._authorizer is not None and decision is not None:
                    self._authorizer.record_execution(decision)

                if not result.success:
                    if self._state_machine.current_state != KernelState.FAULTED:
                        try:
                            self._state_machine.transition_to(
                                KernelState.FAULTED,
                                reason=str(result.error_message)
                            )
                        except InvalidStateTransitionError:
                            pass
                    raise ExecutionEngineError(
                        "Module execution failed on seq_id " + str(frame.seq_id) + ": " + str(result.error_message)
                    )

            post_envelope = self._state_machine.transition_to(KernelState.READY)
            return post_envelope, result

        except StateMachineError:
            if self._state_machine.current_state != KernelState.FAULTED:
                try:
                    self._state_machine.transition_to(
                        KernelState.FAULTED,
                        reason="SEQUENCE_VIOLATION: seq_id " + str(frame.seq_id)
                    )
                except InvalidStateTransitionError:
                    pass
            raise

        except ExecutionEngineError:
            raise

        except Exception as err:
            if self._state_machine.current_state != KernelState.FAULTED:
                try:
                    self._state_machine.transition_to(
                        KernelState.FAULTED,
                        reason="EXECUTION_FAILURE: " + str(err)
                    )
                except InvalidStateTransitionError:
                    pass
            raise ExecutionEngineError("Execution failed on seq_id " + str(frame.seq_id) + ": " + str(err)) from err
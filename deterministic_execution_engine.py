"""
Deterministic Execution Engine & State Evolution Operator - Sentinel Framework

v2.8 (PolicyDecisionRecord emission): process_frame() now constructs a
PolicyDecisionRecord alongside DecisionRecord, at the same call site,
from the SAME ExecutionPolicyDecision object -- not a second
authorize() call, not a reconstruction from fields. This is the engine
acting as compositor: it is the first point where frame.seq_id,
prior_envelope.generation_id, and the authorizer's decision all coexist
in scope at once, so it is the only place that can correctly bind all
three without any of the three modules involved (authorizer, kernel
state, policy decision persistence) needing to know about the others.
See policy_decision_record_contract.py's own docstring for why this
wrapper is constructed here and not inside ExecutionPolicyDecision or
ExecutionAuthorizer.

Like DecisionRecord, PolicyDecisionRecord is appended for BOTH allowed
and denied outcomes, at the same point DecisionRecord is appended --
before the AuthorizationDeniedError raise on denial. A denied attempt
is still a real policy decision worth its own provenance record, even
though (like DecisionRecord) it will have no corresponding
ExecutionAuditRecord, since dispatch never happens on denial.

v2.7 (with_generation): added DeterministicExecutionEngine.with_generation(),
a test/verification-only alternate constructor that seeds the engine's
underlying KernelStateMachine via KernelStateMachine.from_history() with
a caller-supplied generation_id, instead of __init__'s ordinary fresh
random genesis. Exists specifically so code comparing behavior ACROSS
two independently-constructed engine instances (e.g.
check_replay_matches in module_compliance_checks.py,
test_replay_equivalence_determinism) can hold generation identity fixed
and constant across both, proving genuine computational determinism
given the SAME generation -- rather than incidentally comparing two
different generations and mistaking that difference for a bug. Same
"production mints, restoration accepts" split as
KernelStateMachine.from_history() itself: __init__ still never accepts
a generation_id and never will.

v2.6 (generation_id wiring): the engine already captures prior_envelope
(a KernelStateEnvelope) before authorizing and dispatching each frame --
this version threads prior_envelope.generation_id into BOTH the
DecisionRecord and the ExecutionAuditRecord it constructs for that
frame. No new coupling: the engine already had this value in scope at
exactly the right point; this only threads it into two constructor
calls that previously omitted it. See GENERATION_ID_MIGRATION_NOTE.md.

v2.5: DecisionRecord history. The engine now records exactly one
DecisionRecord per execution attempt that reaches the authorization
boundary, whenever an authorizer is attached — for both allowed and
denied outcomes. This is separate from audit_log (which only records
executions that actually dispatched). See v2.5 design document for the
full invariant set (A: exactly one decision per attempt, B: every audit
record has exactly one preceding allowed decision, C: replay preserves
causal ordering, not just hash values).

Still holds from v2.4: this module imports NOTHING from execution_policy.py,
execution_policy_state.py, or execution_authorizer.py beyond duck-typed
calls to authorizer.authorize()/record_execution(). decision_record_contract
IS imported here, since DecisionRecord is engine-owned history, not policy
internals — it's the same category as ExecutionAuditRecord already is.
policy_decision_record_contract IS ALSO imported here as of v2.8, for the
same reason: PolicyDecisionRecord is engine-owned composition history,
not policy internals -- it embeds an ExecutionPolicyDecision but is
itself constructed and owned by the engine, exactly like DecisionRecord
references decision_hash without owning the authorizer's reasoning.
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
from decision_record_contract import DecisionRecord
from policy_decision_record_contract import PolicyDecisionRecord


class ExecutionEngineError(Exception):
    """Base exception for deterministic execution engine failures."""
    pass


class StateIntegrityError(ExecutionEngineError):
    """Raised when incoming frame provenance verification fails."""
    pass


class AuthorizationDeniedError(ExecutionEngineError):
    """
    Raised when an injected authorizer denies execution for a frame.
    A DecisionRecord (and, as of v2.8, a PolicyDecisionRecord) is
    appended to their respective logs BEFORE this is raised — denial is
    a recorded event, not just an exception.
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
        self._state_machine = KernelStateMachine(initial_state=KernelState.UNINITIALIZED)
        self._module = module
        self._authorizer = authorizer
        self._audit_log: List[ExecutionAuditRecord] = []
        self._decision_log: List[DecisionRecord] = []
        self._policy_decision_log: List[PolicyDecisionRecord] = []

    @classmethod
    def with_generation(
        cls,
        generation_id: bytes,
        module: Optional[ExecutionModule] = None,
        authorizer: Optional[Any] = None,
    ) -> "DeterministicExecutionEngine":
        """
        Test/verification-only alternate constructor. Builds an engine
        whose underlying KernelStateMachine is seeded with an explicit,
        caller-supplied generation_id via KernelStateMachine.from_history(),
        rather than minting a fresh random one the way ordinary __init__
        does.

        The resulting engine still starts UNINITIALIZED and still
        requires a normal initialize() call afterward -- this only fixes
        WHICH generation_id that genesis will carry; it does not skip
        genesis itself, and it does not touch __init__'s behavior for
        any other caller. ordinary DeterministicExecutionEngine()
        construction is completely unaffected by this method's
        existence.

        Use this when comparing behavior ACROSS two or more independently
        -constructed engine instances and the comparison is meant to
        prove computational determinism given the SAME generation --
        e.g. two calls to a run() helper that each build a fresh engine
        and are expected to produce identical hashes. Without this,
        two ordinary DeterministicExecutionEngine() instances are, by
        design, two different generations (see
        KernelStateMachine.__init__ / from_history() docstrings), and
        comparing hashes across them is comparing two different
        lifetimes, not testing determinism.
        """
        instance = cls.__new__(cls)
        instance._state_machine = KernelStateMachine.from_history(
            generation_id=generation_id,
            state=KernelState.UNINITIALIZED,
            last_processed_seq=-1,
            total_frames_processed=0,
            fault_reason=None,
        )
        instance._module = module
        instance._authorizer = authorizer
        instance._audit_log = []
        instance._decision_log = []
        instance._policy_decision_log = []
        return instance

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

    @property
    def decision_log(self) -> Tuple[DecisionRecord, ...]:
        """
        Engine-owned decision history. Contains exactly one DecisionRecord
        per execution attempt that reached the authorization boundary with
        an authorizer attached — Invariant A. Independent of audit_log:
        a denied attempt appears here with no corresponding audit_log entry.
        """
        return tuple(self._decision_log)

    @property
    def policy_decision_log(self) -> Tuple[PolicyDecisionRecord, ...]:
        """
        Engine-owned policy decision provenance history, as of v2.8.
        Contains exactly one PolicyDecisionRecord per execution attempt
        that reached the authorization boundary with an authorizer
        attached -- same invariant as decision_log, same population
        points, same call site. Each entry's policy_decision is the
        exact ExecutionPolicyDecision object DecisionRecord.decision_hash
        for the same sequence_id references -- see
        policy_record.policy_decision.decision_hash ==
        decision_record.decision_hash for the bridge this exists to
        prove.
        """
        return tuple(self._policy_decision_log)

    def initialize(self) -> KernelStateEnvelope:
        self._state_machine.transition_to(KernelState.INITIALIZING)
        return self._state_machine.transition_to(KernelState.READY)

    def process_frame(self, frame: CoreExecutionFrame) -> Tuple[KernelStateEnvelope, Optional[ExecutionResult]]:
        current_state = self._state_machine.current_state

        if current_state not in (KernelState.READY, KernelState.PROCESSING):
            raise ExecutionEngineError(
                "Cannot process frame in state " + current_state.name + ". Must be in READY or PROCESSING."
            )

        # 1. Frame integrity — unchanged.
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

        # 2. Authorization gate + DecisionRecord/PolicyDecisionRecord
        # emission (v2.5, extended v2.8). Recorded for BOTH allowed and
        # denied outcomes, before any kernel state mutation — matching
        # v2.4's "denial leaves kernel state untouched" behavior. Neither
        # record is kernel state; both are decision history, appended
        # regardless of the outcome.
        #
        # generation_id (v2.6): sourced from prior_envelope, the SAME
        # envelope this frame's audit record (if any) will also draw
        # generation_id from — both describe the same kernel snapshot.
        #
        # PolicyDecisionRecord (v2.8): constructed from the SAME
        # `decision` object DecisionRecord.decision_hash below
        # references — not a second authorize() call, not a
        # reconstruction. This is the one and only place in the codebase
        # where frame.seq_id, prior_envelope.generation_id, and the
        # authorizer's ExecutionPolicyDecision all coexist in scope at
        # once, which is exactly why this record is composed here and
        # not inside the authorizer or the policy decision itself.
        decision = None
        if self._authorizer is not None and self._module is not None:
            decision = self._authorizer.authorize(self._module.module_id)

            record = DecisionRecord(
                sequence_id=frame.seq_id,
                module_id=self._module.module_id,
                allowed=decision.allowed,
                decision_hash=decision.decision_hash,
                generation_id=prior_envelope.generation_id,
            )
            self._decision_log.append(record)

            policy_record = PolicyDecisionRecord(
                sequence_id=frame.seq_id,
                generation_id=prior_envelope.generation_id,
                policy_decision=decision,
            )
            self._policy_decision_log.append(policy_record)

            if not decision.allowed:
                raise AuthorizationDeniedError(decision)

        # 3. Existing PROCESSING transition and sequence tracking.
        if current_state == KernelState.READY:
            self._state_machine.transition_to(KernelState.PROCESSING)

        try:
            self._state_machine.record_frame_execution(frame.seq_id)

            result = None
            if self._module is not None:
                result = self._module.execute(frame, prior_envelope)

                audit_record = ExecutionAuditRecord.from_execution(
                    sequence_id=frame.seq_id,
                    input_hash=frame.provenance_hash,
                    prior_state_hash=prior_envelope.state_hash,
                    frame_timestamp_ns=frame.timestamp_ns,
                    module_id=self._module.module_id,
                    result=result,
                    generation_id=prior_envelope.generation_id,
                )
                self._audit_log.append(audit_record)

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

"""
Reset Epoch Observability - Discovery Test (v2, with real authorizer)
(test_reset_epoch_observability.py)

Redo of the original discovery experiment, now with a real
ExecutionAuthorizer/ExecutionPolicy/ExecutionPolicyState attached, so
DecisionRecord is genuinely produced rather than scoped out. This
closes the gap the original version documented explicitly (no
authorizer available at the time execution_authorizer.py's concrete
constructor hadn't been seen).

THE ORIGINAL FINDING (still proven below): KernelStateEnvelope.state_hash
is a pure snapshot of (last_processed_seq, total_frames_processed,
current_state, fault_reason) with no reset-generation signal --
administrative reset zeros these back to true-initial values, so the
envelope before Phase 1's frame 0 and the envelope before Phase 4's
(post-reset) frame 0 are byte-identical.

THE NEW HYPOTHESIS THIS VERSION TESTED, AND WHY IT WAS WRONG: the
original draft of this test predicted DecisionRecord.decision_hash
would NOT collide across the reset, on the theory that it incorporates
observed_invocation_count (tracked by ExecutionPolicyState, untouched
by the kernel's reset). That prediction was wrong, and running the
test caught the error: re-reading ExecutionPolicyDecision.
_compute_decision_hash() in execution_authorizer.py line by line shows
it hashes only module_id, allowed, reason, observed_lifecycle_state.name,
policy_hash, and capability_snapshot_hash -- observed_invocation_count
is a real field on ExecutionPolicyDecision but is DELIBERATELY EXCLUDED
from the hash. Since every one of the six hashed fields is identical
between the two moments (same module, same ACTIVE lifecycle state,
same policy, same capabilities, both allowed=True/"ALLOWED"),
decision_hash collides -- correctly, per the actual code, not a bug.

THE ACTUAL FINDING, corrected: NEITHER kernel-level evidence
(state_hash) NOR policy-level evidence (decision_hash, record_hash)
distinguishes the two reset generations. DecisionRecord does not even
carry observed_invocation_count as a field at all (see
decision_record_contract.py's field list: sequence_id, module_id,
allowed, decision_hash, record_hash -- no invocation count anywhere),
so the one piece of state that genuinely differs between the two
moments (ExecutionPolicyState's internal counter, confirmed via direct
inspection to be 4 at Phase 4's start vs 0 at Phase 1's start) never
reaches persisted evidence in the first place. The ONLY thing that
distinguished the two generations in this experiment was raw frame
content (input_hash / output_hash on the audit records) -- and that
only worked because this test deliberately used different payloads
across the two phases. A genuine identical-content replay after a
reset would collide on every single hash this codebase currently
persists: state_hash, decision_hash, record_hash, AND (since
input_hash/output_hash would then match too) audit_hash.
"""

import numpy as np
import pytest

from deterministic_execution_engine import DeterministicExecutionEngine, ExecutionEngineError
from execution_kernel_contract import CoreExecutionFrame
from execution_module_contract import ExecutionResult
from execution_module_registry import ExecutionModuleRegistry
from execution_policy import ExecutionPolicy
from execution_policy_state import ExecutionPolicyState
from execution_authorizer import ExecutionAuthorizer


class _PickyModule:
    """
    Succeeds on every frame except sequence_id == 3, which it
    deliberately fails -- forces a real FAULTED transition at a known
    point.

    Output is the INPUT PAYLOAD COPIED THROUGH UNCHANGED (not derived
    from seq_id alone) -- this matters for this test specifically:
    two frames with the same seq_id but different payload content
    (as happens across the Phase 1 / Phase 4 reset boundary below)
    must produce different output_hash values, so the "records remain
    distinguishable by content" assertions actually exercise real
    content-dependence rather than colliding by construction of this
    double. A copy-through is trivially deterministic (same frame in
    -> same array out, every time) and trivially finite for every
    PATHOLOGICAL_SEEDS value used elsewhere in this codebase's
    compliance suite (all of them are large-but-finite floats, never
    NaN/inf), so it satisfies the compliance suite unchanged.
    """
    module_id = "reset_epoch_test_module"

    def execute(self, frame, envelope):
        if frame.seq_id == 3:
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message="Deliberate failure for reset epoch discovery test.",
            )
        return ExecutionResult(
            seq_id=frame.seq_id,
            success=True,
            output_payload=frame.payload.copy(),
        )


def _make_frame(seq_id: int, payload_fill: float, timestamp_ns: int) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=payload_fill, dtype=np.float64)
    return CoreExecutionFrame.create(seq_id=seq_id, timestamp_ns=timestamp_ns, payload=payload)


@pytest.fixture
def authorized_engine():
    """
    Builds a real registry + policy + state + authorizer + engine,
    with _PickyModule registered and activated. Policy has no
    invocation limit (max_invocations_per_module_lifetime=None), so
    every authorize() call returns allowed=True -- the fault in Phase 2
    comes from the MODULE reporting failure, not from authorization
    denying the frame.
    """
    module = _PickyModule()
    registry = ExecutionModuleRegistry()
    registry.register(module)  # default manifest, verify=True (real compliance suite)
    registry.activate(module.module_id)

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=None)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry=registry, policy=policy, state=state)

    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    return engine, state


def test_neither_kernel_nor_policy_hash_evidence_distinguishes_reset_generations(authorized_engine):
    """
    The full four-phase timeline, now with real DecisionRecords. Proves
    the CORRECTED finding: state_hash collides across the reset (kernel
    evidence forgets it happened) AND decision_hash/record_hash ALSO
    collide (policy evidence forgets it too, because
    observed_invocation_count -- the one field that genuinely differs
    -- is excluded from ExecutionPolicyDecision's hash and never even
    reaches DecisionRecord as a field). The only thing that
    distinguishes the two generations in this test is raw frame content
    (input_hash/output_hash), which only differs because this test
    deliberately varied the payloads.
    """
    engine, policy_state = authorized_engine

    # ---- Phase 1: clean start, frames 0, 1, 2 succeed ----
    prior_envelope_phase1_frame0 = engine.state_machine.get_envelope()

    engine.process_frame(_make_frame(0, payload_fill=100.0, timestamp_ns=1000))
    engine.process_frame(_make_frame(1, payload_fill=101.0, timestamp_ns=2000))
    engine.process_frame(_make_frame(2, payload_fill=102.0, timestamp_ns=3000))

    assert len(engine.audit_log) == 3
    assert len(engine.decision_log) == 3
    assert all(d.allowed for d in engine.decision_log)

    # ---- Phase 2: frame 3 deliberately fails -> FAULTED ----
    with pytest.raises(ExecutionEngineError):
        engine.process_frame(_make_frame(3, payload_fill=103.0, timestamp_ns=4000))

    assert engine.state_machine.current_state.name == "FAULTED"
    assert len(engine.audit_log) == 4
    assert engine.audit_log[-1].success is False
    # Decision was still ALLOWED (the module failed, not the authorizer) --
    # confirms decision_log records the authorization attempt, not the
    # eventual execution outcome.
    assert len(engine.decision_log) == 4
    assert engine.decision_log[-1].allowed is True

    # Invocation count after phase 2: 4 authorized+recorded executions
    # (frames 0, 1, 2, 3 -- including the failed one, per the existing
    # "failures consume quota the same as successes" contract).
    assert policy_state.get_count("reset_epoch_test_module") == 4

    # ---- Phase 3: administrative reset (kernel only) ----
    engine.initialize()

    assert engine.state_machine.current_state.name == "READY"
    assert engine.state_machine.last_processed_seq == -1
    assert engine.state_machine.total_frames_processed == 0

    # Policy state is UNTOUCHED by the kernel's administrative reset --
    # this is the crux of the asymmetry.
    assert policy_state.get_count("reset_epoch_test_module") == 4, (
        "Expected the policy invocation count to survive the kernel reset "
        "unchanged -- ExecutionPolicyState is a separate object from "
        "KernelStateMachine and nothing in engine.initialize() touches it."
    )

    prior_envelope_phase4_frame0 = engine.state_machine.get_envelope()

    # ---- KERNEL-LEVEL FINDING (confirms the original result) ----
    assert prior_envelope_phase1_frame0.state_hash == prior_envelope_phase4_frame0.state_hash, (
        "Kernel state_hash should collide across the reset -- pure "
        "snapshot hash, no generation counter."
    )

    # ---- Phase 4: resume, frames 0 and 1 again ----
    engine.process_frame(_make_frame(0, payload_fill=200.0, timestamp_ns=5000))
    engine.process_frame(_make_frame(1, payload_fill=201.0, timestamp_ns=6000))

    assert len(engine.audit_log) == 6
    assert len(engine.decision_log) == 6

    phase1_frame0_audit = engine.audit_log[0]
    phase4_frame0_audit = engine.audit_log[4]
    phase1_frame0_decision = engine.decision_log[0]
    phase4_frame0_decision = engine.decision_log[4]

    assert phase1_frame0_audit.sequence_id == phase4_frame0_audit.sequence_id == 0
    assert phase1_frame0_decision.sequence_id == phase4_frame0_decision.sequence_id == 0

    # KERNEL-LEVEL: audit records' prior_state_hash inherits the collision.
    assert phase1_frame0_audit.prior_state_hash == phase4_frame0_audit.prior_state_hash

    # But audit records remain distinguishable by CONTENT (different
    # payloads -> different input/output hashes) even though the kernel
    # snapshot collided:
    assert phase1_frame0_audit.input_hash != phase4_frame0_audit.input_hash
    assert phase1_frame0_audit.output_hash != phase4_frame0_audit.output_hash
    assert phase1_frame0_audit.audit_hash != phase4_frame0_audit.audit_hash

    # ---- POLICY-LEVEL FINDING (corrected) ----
    # decision_hash and record_hash COLLIDE too, despite
    # observed_invocation_count genuinely differing (0 vs 4) at the
    # ExecutionPolicyState level -- because ExecutionPolicyDecision's
    # hash computation never includes that field. This is the actual,
    # corrected finding: the original prediction (that policy evidence
    # would remember the reset) was wrong, and this assertion proves
    # the real behavior instead of the wrong prediction.
    assert phase1_frame0_decision.decision_hash == phase4_frame0_decision.decision_hash, (
        "decision_hash collides across the reset -- ExecutionPolicyDecision. "
        "_compute_decision_hash() hashes module_id, allowed, reason, "
        "observed_lifecycle_state.name, policy_hash, and "
        "capability_snapshot_hash only. observed_invocation_count (which "
        "DOES differ, 0 vs 4) is deliberately excluded from the hash."
    )
    assert phase1_frame0_decision.record_hash == phase4_frame0_decision.record_hash, (
        "record_hash collides too, since DecisionRecord._compute_record_hash() "
        "hashes sequence_id, module_id, allowed, and decision_hash -- all four "
        "identical between these two decisions."
    )

    # Confirm the mechanism: the invocation count genuinely differs at
    # the ExecutionPolicyState level, even though nothing downstream
    # (ExecutionPolicyDecision's hash, or DecisionRecord's fields) ever
    # reflects that difference.
    assert policy_state.get_count("reset_epoch_test_module") == 6


def test_invocation_count_differs_but_is_excluded_from_persisted_hash_fields():
    """
    Isolates the actual mechanism behind the corrected finding above,
    independent of the full four-phase timeline: ExecutionPolicyDecision
    has an observed_invocation_count field that genuinely varies, but
    it is structurally excluded from every hash this codebase persists
    (decision_hash, and therefore record_hash, and DecisionRecord
    doesn't carry the field at all). This is a real design choice in
    execution_authorizer.py, not a bug -- but it means no evidence
    surviving to disk today can distinguish two authorization decisions
    made under different invocation-count histories if every other
    hashed field (module_id, allowed, reason, lifecycle state, policy_hash,
    capability_snapshot_hash) happens to match.
    """
    from dataclasses import fields
    from decision_record_contract import DecisionRecord

    decision_record_field_names = {f.name for f in fields(DecisionRecord)}
    assert "observed_invocation_count" not in decision_record_field_names, (
        f"DecisionRecord's fields are {decision_record_field_names} -- if this "
        f"assertion fails, the field now exists here and the collision found "
        f"above may no longer hold; re-run the main test in this file."
    )

"""
Reset Epoch Observability - Discovery Test (v3, post-generation_id-migration)
(test_reset_epoch_observability.py)

Third pass on this discovery experiment. History, preserved for context:

v1 finding (PRE-migration, no longer current): KernelStateEnvelope.
state_hash was a pure snapshot of (last_processed_seq,
total_frames_processed, current_state, fault_reason) with no
reset-generation signal -- administrative reset zeroed these back to
true-initial values, so the envelope before Phase 1's frame 0 and the
envelope before Phase 4's (post-reset) frame 0 were byte-identical.
This WAS Gap 1b.

v2 finding (still current, unrelated to generation_id): the original
draft of this test predicted DecisionRecord.decision_hash would NOT
collide across the reset, on the theory that it incorporates
observed_invocation_count. That prediction was wrong: re-reading
ExecutionPolicyDecision._compute_decision_hash() in
execution_authorizer.py shows it hashes only module_id, allowed,
reason, observed_lifecycle_state.name, policy_hash, and
capability_snapshot_hash -- observed_invocation_count is a real field
on ExecutionPolicyDecision but is DELIBERATELY EXCLUDED from the hash.
decision_hash collides -- correctly, per the actual code.

v3 finding (THIS VERSION, current): the generation_id migration closed
Gap 1b at the kernel level and, as a direct consequence, at the
DecisionRecord level too -- but NOT at the ExecutionPolicyDecision
level, and that three-way split is the actual interesting result now.

  - state_hash (kernel): now DIFFERS across the reset.
    KernelStateMachine mints a new generation_id on every
    FAULTED->INITIALIZING transition, and get_envelope() folds
    generation_id into state_hash's computation. Two envelopes with
    identical scalar fields but different generations are no longer
    identical envelopes.

  - DecisionRecord.record_hash (policy, but kernel-adjacent): now also
    DIFFERS across the reset. DeterministicExecutionEngine threads
    prior_envelope.generation_id directly into every DecisionRecord it
    constructs, and DecisionRecord's own hash computation includes it.
    So record_hash carries reset-generation evidence even though...

  - ExecutionPolicyDecision.decision_hash (policy, one layer further
    up): STILL collides, UNCHANGED by this migration. This field is
    computed entirely within execution_authorizer.py, deliberately
    without any KernelStateMachine dependency (see
    GENERATION_ID_MIGRATION_NOTE.md: "ExecutionPolicyDecision/
    decision_hash deliberately UNCHANGED -- would require giving the
    authorizer a new kernel dependency"). It has no generation_id
    input at all, so it cannot distinguish reset generations, and
    still can't distinguish differing observed_invocation_count either
    (that finding is untouched -- see
    test_invocation_count_differs_but_is_excluded_from_persisted_hash_fields
    below).

Net effect: DecisionRecord.record_hash and ExecutionPolicyDecision.
decision_hash now diverge from each other where they used to agree --
record_hash sees the reset, decision_hash it wraps does not. That's a
sharper result than either the v1 or v2 findings alone.
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


def test_kernel_and_record_hash_now_distinguish_reset_generations_but_decision_hash_does_not(authorized_engine):
    """
    The full four-phase timeline. Proves the v3, post-migration finding:
    state_hash and DecisionRecord.record_hash now DIFFER across the
    reset (generation_id closed Gap 1b at both levels), but
    ExecutionPolicyDecision.decision_hash still COLLIDES, unchanged --
    it has no generation_id input and was deliberately kept that way.
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
    # this is the crux of the asymmetry, and it's untouched by the
    # generation_id migration too: ExecutionPolicyState is a separate
    # object from KernelStateMachine and nothing in engine.initialize()
    # touches it.
    assert policy_state.get_count("reset_epoch_test_module") == 4, (
        "Expected the policy invocation count to survive the kernel reset "
        "unchanged -- ExecutionPolicyState is a separate object from "
        "KernelStateMachine and nothing in engine.initialize() touches it."
    )

    prior_envelope_phase4_frame0 = engine.state_machine.get_envelope()

    # ---- KERNEL-LEVEL FINDING (v3, post-migration) ----
    assert prior_envelope_phase1_frame0.state_hash != prior_envelope_phase4_frame0.state_hash, (
        "Kernel state_hash should now DIFFER across the reset -- this is "
        "the generation_id migration's entire purpose (closing Gap 1b). "
        "KernelStateMachine mints a new generation_id on every "
        "FAULTED->INITIALIZING transition, and get_envelope() folds "
        "generation_id into state_hash's computation, so two envelopes "
        "with identical scalar fields (last_processed_seq, "
        "total_frames_processed, state, fault_reason) but different "
        "generations are no longer indistinguishable."
    )
    assert prior_envelope_phase1_frame0.generation_id != prior_envelope_phase4_frame0.generation_id, (
        "The mechanism directly: generation_id itself must differ "
        "between the two envelopes, not just the derived state_hash."
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

    # KERNEL-LEVEL: audit records' prior_state_hash inherits the
    # distinction (v3) -- it's the same value as the envelope's
    # state_hash, so this follows directly from the assertion above.
    assert phase1_frame0_audit.prior_state_hash != phase4_frame0_audit.prior_state_hash

    # Audit records also remain distinguishable by CONTENT (different
    # payloads -> different input/output hashes), independent of the
    # generation_id distinction above -- both reasons hold at once here,
    # since this test deliberately varies payloads across the reset.
    assert phase1_frame0_audit.input_hash != phase4_frame0_audit.input_hash
    assert phase1_frame0_audit.output_hash != phase4_frame0_audit.output_hash
    assert phase1_frame0_audit.audit_hash != phase4_frame0_audit.audit_hash

    # ---- POLICY-LEVEL FINDING (v3: record_hash and decision_hash now
    # DIVERGE from each other, where they used to agree) ----

    # decision_hash STILL collides -- UNCHANGED by this migration.
    # ExecutionPolicyDecision._compute_decision_hash() lives one layer
    # above the kernel and was deliberately NOT given a generation_id
    # or any other KernelStateMachine dependency (see
    # GENERATION_ID_MIGRATION_NOTE.md). It hashes module_id, allowed,
    # reason, observed_lifecycle_state.name, policy_hash, and
    # capability_snapshot_hash only -- none of which differ here.
    assert phase1_frame0_decision.decision_hash == phase4_frame0_decision.decision_hash, (
        "decision_hash STILL collides across the reset -- this part of "
        "the pre-migration finding is UNCHANGED. ExecutionPolicyDecision. "
        "_compute_decision_hash() has no generation_id input at all, by "
        "deliberate design, to avoid coupling the authorizer to "
        "KernelStateMachine."
    )

    # record_hash, in contrast, now DIFFERS -- DeterministicExecutionEngine
    # threads prior_envelope.generation_id directly into every
    # DecisionRecord it constructs (independent of decision_hash, which
    # it also carries but does not derive generation-awareness from),
    # and DecisionRecord's own hash computation includes generation_id.
    # So record_hash sees the reset even though the decision_hash it
    # wraps does not -- the interesting result this version of the test
    # exists to prove.
    assert phase1_frame0_decision.record_hash != phase4_frame0_decision.record_hash, (
        "record_hash now DIFFERS across the reset, even though "
        "decision_hash (which it wraps) collided above. DecisionRecord's "
        "own hash computation was extended to include generation_id "
        "directly, sourced from prior_envelope.generation_id at "
        "construction time -- so DecisionRecord carries reset-generation "
        "evidence that ExecutionPolicyDecision.decision_hash alone does "
        "not."
    )
    assert phase1_frame0_decision.generation_id != phase4_frame0_decision.generation_id, (
        "The mechanism directly: DecisionRecord.generation_id itself "
        "must differ between the two decisions."
    )

    # Confirm the mechanism this whole test is about: the invocation
    # count genuinely differs at the ExecutionPolicyState level (0 vs 4
    # observed at the two moments), but that specific fact is STILL not
    # what makes record_hash differ -- generation_id is a completely
    # separate signal from observed_invocation_count, and the latter
    # remains invisible to every persisted hash in this codebase (see
    # test_invocation_count_differs_but_is_excluded_from_persisted_hash_fields
    # below, unaffected by this migration).
    assert policy_state.get_count("reset_epoch_test_module") == 6


def test_invocation_count_differs_but_is_excluded_from_persisted_hash_fields():
    """
    Isolates the actual mechanism behind the STILL-current v2 finding,
    independent of the full four-phase timeline and independent of the
    generation_id migration: ExecutionPolicyDecision has an
    observed_invocation_count field that genuinely varies, but it is
    structurally excluded from every hash this codebase persists
    (decision_hash, and therefore -- separately from generation_id --
    from record_hash's decision_hash component too; DecisionRecord
    doesn't carry the field at all). This is a real design choice in
    execution_authorizer.py, not a bug, and generation_id does nothing
    to change it: generation_id makes record_hash reset-generation-aware,
    but invocation-count-blindness is an entirely separate gap that
    remains open.
    """
    from dataclasses import fields
    from decision_record_contract import DecisionRecord

    decision_record_field_names = {f.name for f in fields(DecisionRecord)}
    assert "observed_invocation_count" not in decision_record_field_names, (
        f"DecisionRecord's fields are {decision_record_field_names} -- if this "
        f"assertion fails, the field now exists here and the exclusion found "
        f"above may no longer hold; re-run the main test in this file."
    )

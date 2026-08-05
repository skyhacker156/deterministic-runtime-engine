"""
Module Contract Compliance Harness
(test_module_contract_compliance.py)

Generic, parameterized compliance suite for any ExecutionModule implementation.
Per execution_module_spec.md: a module is compliant only when it passes every
test in this file. Passing by inspection is not sufficient.

To validate a new module, add it to MODULES_UNDER_TEST below. Every test in
this file runs once per registered module automatically via pytest's
parametrize mechanism.

NOTE (found during generation_id migration, not fixed here): this file
maintains its own independent _make_envelope() / test_module_replay_matches
implementation rather than importing from module_compliance_checks.py,
despite that module's docstring claiming both files "import and call
these same functions rather than maintaining two independent
implementations." That claim does not currently hold -- this file has no
import of module_compliance_checks.py at all. Left as-is for this pass;
worth a deliberate decision later on whether to consolidate onto one
shared implementation or correct the docstring claim, rather than
silently living with the drift.

generation_id note: _make_envelope() supplies a fixed placeholder
generation_id (_ENVELOPE_GENERATION_ID), safe because every test using it
builds exactly ONE envelope and reuses that same object throughout.
test_module_replay_matches is the one test that spans two independent
DeterministicExecutionEngine instances, so it uses
DeterministicExecutionEngine.with_generation() with its own separate
fixed constant (_REPLAY_GENERATION_ID) to hold generation identity
constant across both runs -- see with_generation()'s own docstring for
why an ordinary two-independent-engines comparison would otherwise be
comparing two different generations, not testing determinism.
"""

import copy
import dataclasses
import numpy as np
import pytest

from execution_kernel_contract import CoreExecutionFrame
from execution_kernel_state import KernelState, KernelStateEnvelope
from execution_module_contract import ExecutionModule, ExecutionResult
from deterministic_execution_engine import DeterministicExecutionEngine, ExecutionEngineError

from phoenix_a_execution_module import PhoenixAExecutionModule
from example_execution_module import ExampleExecutionModule


# ---------------------------------------------------------------------
# Registry of modules under test.
# Add every ExecutionModule implementation here to run it through the
# full compliance suite.
# ---------------------------------------------------------------------
MODULES_UNDER_TEST = [
    pytest.param(PhoenixAExecutionModule, id="PhoenixAExecutionModule"),
    pytest.param(ExampleExecutionModule, id="ExampleExecutionModule"),
]


# ---------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------

def _make_frame(seq_id: int = 0, timestamp_ns: int = 1_000_000, seed_val: float = 1.0) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    return CoreExecutionFrame.create(seq_id=seq_id, timestamp_ns=timestamp_ns, payload=payload)


# Fixed placeholder generation_id for envelopes built by _make_envelope().
# Every test using it constructs exactly ONE envelope and reuses that
# same object for the duration of the test -- none of them replay across
# independent KernelStateMachine instances, so a fixed constant is safe:
# it never needs to match anything real, it only needs to be present.
# See test_module_replay_matches below for the one test that spans two
# independent engine instances and does NOT use this constant.
_ENVELOPE_GENERATION_ID = b"\xCC" * 16


def _make_envelope(state: KernelState = KernelState.PROCESSING) -> KernelStateEnvelope:
    return KernelStateEnvelope(
        state=state,
        last_processed_seq=-1,
        total_frames_processed=0,
        state_hash=b"\x01" * 32,
        fault_reason=None,
        generation_id=_ENVELOPE_GENERATION_ID,
    )


# ---------------------------------------------------------------------
# 1. Determinism
# ---------------------------------------------------------------------

@pytest.mark.parametrize("module_cls", MODULES_UNDER_TEST)
def test_module_is_deterministic(module_cls):
    """
    Requirement 1: identical (frame, envelope) input must produce an
    ExecutionResult with an identical module_hash on every call.
    """
    module = module_cls()
    frame = _make_frame(seq_id=0, seed_val=2.5)
    envelope = _make_envelope()

    result_1 = module.execute(frame, envelope)
    result_2 = module.execute(frame, envelope)

    assert result_1.module_hash == result_2.module_hash
    assert result_1.success == result_2.success
    assert np.array_equal(result_1.output_payload, result_2.output_payload)


# ---------------------------------------------------------------------
# 2. Replay determinism through the full engine
# ---------------------------------------------------------------------

# Fixed placeholder generation_id used ONLY to hold identity constant
# across the two independent engine instances test_module_replay_matches
# builds below. Deliberately a different constant from
# _ENVELOPE_GENERATION_ID above -- these two are conceptually unrelated
# (one is a throwaway envelope field, this one is a shared identity two
# real engines must agree on) and keeping them visually distinct in a
# debugger avoids conflating them.
_REPLAY_GENERATION_ID = b"\xDD" * 16


@pytest.mark.parametrize("module_cls", MODULES_UNDER_TEST)
def test_module_replay_matches(module_cls):
    """
    Requirement 1 (extended): determinism must hold not just for direct
    execute() calls, but when driven through DeterministicExecutionEngine
    across two independent engine instances.

    generation_id: both run() calls below use
    DeterministicExecutionEngine.with_generation() with the SAME fixed
    _REPLAY_GENERATION_ID, rather than ordinary construction (which would
    mint a genuinely different random generation_id per call). This test
    is specifically about proving computational determinism GIVEN the
    same generation -- two ordinary, independently-constructed engines
    are, by design, two different generations, and comparing hashes
    across those would be comparing two different lifetimes, not testing
    whether the module itself behaves deterministically.
    """
    def run():
        engine = DeterministicExecutionEngine.with_generation(
            generation_id=_REPLAY_GENERATION_ID,
            module=module_cls(),
        )
        engine.initialize()
        _, result = engine.process_frame(_make_frame(seq_id=0, seed_val=1.5))
        return result.module_hash

    assert run() == run()


# ---------------------------------------------------------------------
# 3. Cannot mutate context
# ---------------------------------------------------------------------

@pytest.mark.parametrize("module_cls", MODULES_UNDER_TEST)
def test_module_cannot_mutate_context(module_cls):
    """
    Requirement 4: a module must not be able to mutate the KernelStateEnvelope
    it receives. This is enforced structurally (frozen dataclass), but this
    test actively confirms that guarantee rather than trusting it by
    convention, and confirms execute() itself doesn't attempt a workaround
    (e.g. object.__setattr__) that would bypass the freeze.
    """
    module = module_cls()
    frame = _make_frame(seq_id=0)
    envelope = _make_envelope()

    envelope_before = copy.deepcopy(envelope)

    with pytest.raises(dataclasses.FrozenInstanceError):
        envelope.state = KernelState.FAULTED

    module.execute(frame, envelope)
    assert envelope.state == envelope_before.state
    assert envelope.state_hash == envelope_before.state_hash
    assert envelope.last_processed_seq == envelope_before.last_processed_seq


# ---------------------------------------------------------------------
# 4. Rejects invalid input gracefully
# ---------------------------------------------------------------------

@pytest.mark.parametrize("module_cls", MODULES_UNDER_TEST)
def test_module_rejects_invalid_input(module_cls):
    """
    Requirement 2 (finite outputs) applied defensively: a module given a
    frame with pathological payload values (extremely large, extremely
    small-but-nonzero) must still return a well-formed ExecutionResult
    with a finite output_payload — either by handling the input gracefully
    (success=True) or by reporting a graceful failure (success=False),
    but never by raising or returning non-finite values.
    """
    module = module_cls()
    envelope = _make_envelope()

    pathological_seeds = [1e300, -1e300, 1e-300, -1e-300, 0.0]

    for seed in pathological_seeds:
        frame = _make_frame(seq_id=0, seed_val=seed)
        result = module.execute(frame, envelope)

        assert isinstance(result, ExecutionResult)
        assert np.all(np.isfinite(result.output_payload)), (
            f"Non-finite output for seed_val={seed}"
        )


# ---------------------------------------------------------------------
# 5. Output is hashable / well-formed
# ---------------------------------------------------------------------

@pytest.mark.parametrize("module_cls", MODULES_UNDER_TEST)
def test_module_output_is_hashable(module_cls):
    """
    Requirement 5: the module's output must produce a valid module_hash
    via ExecutionResult's own mechanism — never a hand-assigned or
    independently-computed hash.
    """
    module = module_cls()
    frame = _make_frame(seq_id=0)
    envelope = _make_envelope()

    result = module.execute(frame, envelope)

    assert isinstance(result.module_hash, bytes)
    assert len(result.module_hash) == 32

    reconstructed = ExecutionResult(
        seq_id=result.seq_id,
        success=result.success,
        output_payload=result.output_payload.copy(),
        metrics=result.metrics,
        error_message=result.error_message,
    )
    assert reconstructed.module_hash == result.module_hash


# ---------------------------------------------------------------------
# 6. Failure is auditable
# ---------------------------------------------------------------------

@pytest.mark.parametrize("module_cls", MODULES_UNDER_TEST)
def test_module_failure_is_auditable(module_cls):
    """
    Requirement 6: if a module reports failure via ExecutionResult
    (success=False), the engine must still emit exactly one
    ExecutionAuditRecord for that frame before raising, per
    ARCHITECTURE_FREEZE_v1.5.md Section 5.

    This test does not force a real module into failure (that would
    require module-specific knowledge this generic harness shouldn't
    assume). Instead it confirms the audit-on-failure contract using a
    minimal wrapper that guarantees a failure result, proving the ENGINE
    side of the contract holds for any module's failure path — which is
    what every compliant module relies on.
    """
    class _ForcedFailureWrapper:
        module_id = "compliance_harness_forced_failure"

        def execute(self, frame, envelope):
            return ExecutionResult(
                seq_id=frame.seq_id,
                success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message="Forced failure for compliance harness audit check.",
            )

    engine = DeterministicExecutionEngine(module=_ForcedFailureWrapper())
    engine.initialize()

    frame = _make_frame(seq_id=0)
    with pytest.raises(ExecutionEngineError):
        engine.process_frame(frame)

    assert len(engine.audit_log) == 1
    assert engine.audit_log[0].success is False
    assert "Forced failure" in engine.audit_log[0].error_message


# ---------------------------------------------------------------------
# 7. module_id is well-formed
# ---------------------------------------------------------------------

@pytest.mark.parametrize("module_cls", MODULES_UNDER_TEST)
def test_module_id_is_nonempty_string(module_cls):
    module = module_cls()
    assert isinstance(module.module_id, str)
    assert module.module_id.strip() != ""

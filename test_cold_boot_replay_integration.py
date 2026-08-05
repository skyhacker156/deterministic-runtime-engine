"""
Cold Boot Replay Extension - Integration Tests
(test_cold_boot_replay_integration.py)

End-to-end: build a real registry/policy/authorizer/engine, process
real frames, persist all three logs to disk, then run
reconstruct_cold_boot_with_replay() against those logs. Confirms the
passive verifier and the kernel replay verifier agree when the history
is clean, and confirms the KernelStateVerifier interface is genuinely
pluggable (not hardwired to SequentialReplayKernelVerifier).

Explicitly does NOT modify or re-test cold_boot_reconstruction.py or
causal_history_verifier.py -- those are exercised here only through
their existing, unchanged public API, per this session's instruction
to keep the passive verifier unchanged.
"""

import hashlib
import os
import tempfile

import numpy as np
import pytest

from execution_module_registry import ExecutionModuleRegistry
from execution_policy import ExecutionPolicy
from execution_policy_state import ExecutionPolicyState
from execution_authorizer import ExecutionAuthorizer
from deterministic_execution_engine import DeterministicExecutionEngine
from execution_kernel_contract import CoreExecutionFrame
from execution_module_contract import ExecutionResult

from module_registration_audit_log import append_record as append_registration_record
from decision_record_log import append_decision_record
from execution_audit_log import append_audit_record

from cold_boot_replay_extension import reconstruct_cold_boot_with_replay, ColdBootReplayResult
from kernel_state_replay import KernelStateVerifier, KernelReplayReport


class _AlwaysSucceeds:
    module_id = "integration_test_module"

    def execute(self, frame, envelope):
        return ExecutionResult(
            seq_id=frame.seq_id, success=True,
            output_payload=frame.payload.copy(),
        )


def _make_frame(seq_id, fill, timestamp_ns):
    return CoreExecutionFrame.create(
        seq_id=seq_id, timestamp_ns=timestamp_ns,
        payload=np.full(256, fill_value=fill, dtype=np.float64),
    )


@pytest.fixture
def three_log_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield {
            "registration": os.path.join(tmpdir, "registration.jsonl"),
            "decision": os.path.join(tmpdir, "decision.jsonl"),
            "audit": os.path.join(tmpdir, "audit.jsonl"),
        }


def _run_real_engine_and_persist(paths, num_frames=3):
    """
    Builds the full real stack (registry, policy, authorizer, engine),
    runs it for real, and persists every resulting record to the three
    logs -- mirroring what a real deployment would do, not a shortcut.
    """
    module = _AlwaysSucceeds()
    registry = ExecutionModuleRegistry()
    registry.register(module)
    registry.activate(module.module_id)

    policy = ExecutionPolicy(max_invocations_per_module_lifetime=None)
    state = ExecutionPolicyState()
    authorizer = ExecutionAuthorizer(registry=registry, policy=policy, state=state)

    engine = DeterministicExecutionEngine(module=module, authorizer=authorizer)
    engine.initialize()

    for i in range(num_frames):
        engine.process_frame(_make_frame(i, float(i), 1000 * (i + 1)))

    # Persist registration attempt.
    for attempt in registry.registration_history(module.module_id):
        append_registration_record(paths["registration"], attempt)

    # Persist decision and audit records in original order.
    for d in engine.decision_log:
        append_decision_record(paths["decision"], d)
    for a in engine.audit_log:
        append_audit_record(paths["audit"], a)

    return engine


# ---------------------------------------------------------------------
# 1. Clean end-to-end: passive and replay both fully verify
# ---------------------------------------------------------------------

def test_clean_end_to_end_history_is_fully_verified(three_log_paths):
    engine = _run_real_engine_and_persist(three_log_paths, num_frames=3)

    result = reconstruct_cold_boot_with_replay(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert isinstance(result, ColdBootReplayResult)
    assert result.passive.reconstruction_valid is True
    assert result.kernel_replay.fully_verified is True
    assert result.fully_verified is True

    assert len(result.passive.execution_history) == 3
    assert result.kernel_replay.total_records == 3
    assert result.kernel_replay.verified_count == 3


# ---------------------------------------------------------------------
# 2. Passive reconstruction is untouched -- same result whether or not
#    replay is layered on top
# ---------------------------------------------------------------------

def test_passive_reconstruction_result_identical_with_or_without_replay(three_log_paths):
    from cold_boot_reconstruction import reconstruct_cold_boot

    _run_real_engine_and_persist(three_log_paths, num_frames=2)

    passive_only = reconstruct_cold_boot(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )
    combined = reconstruct_cold_boot_with_replay(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert passive_only.reconstruction_valid == combined.passive.reconstruction_valid
    assert passive_only.registration_history == combined.passive.registration_history
    assert passive_only.authorization_history == combined.passive.authorization_history
    assert passive_only.execution_history == combined.passive.execution_history


# ---------------------------------------------------------------------
# 3. Interface is genuinely pluggable
# ---------------------------------------------------------------------

class _StubVerifierThatAlwaysFails(KernelStateVerifier):
    """
    A fake KernelStateVerifier that always reports total failure,
    regardless of input. Used only to prove
    reconstruct_cold_boot_with_replay() actually calls whatever
    verifier it's given, rather than being hardwired to
    SequentialReplayKernelVerifier.
    """

    def verify(self, execution_history):
        return KernelReplayReport(
            total_records=len(execution_history),
            verified_count=0,
            failures=["stub verifier always fails"],
        )


def test_kernel_verifier_is_genuinely_substitutable(three_log_paths):
    _run_real_engine_and_persist(three_log_paths, num_frames=2)

    result = reconstruct_cold_boot_with_replay(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"],
        kernel_verifier=_StubVerifierThatAlwaysFails(),
    )

    # The passive side is unaffected by which kernel_verifier was used --
    assert result.passive.reconstruction_valid is True
    # -- but the kernel replay result reflects the STUB's behavior, not
    # SequentialReplayKernelVerifier's, proving the substitution worked.
    assert result.kernel_replay.failures == ["stub verifier always fails"]
    assert result.fully_verified is False


# ---------------------------------------------------------------------
# 4. Missing logs still propagate as real errors through the combined path
# ---------------------------------------------------------------------

def test_missing_log_raises_through_combined_entry_point(three_log_paths):
    with pytest.raises(FileNotFoundError):
        reconstruct_cold_boot_with_replay(
            three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
        )
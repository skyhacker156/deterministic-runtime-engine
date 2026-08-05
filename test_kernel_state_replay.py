"""
Kernel State Hash Replay - Tests
(test_kernel_state_replay.py)

Tests build a REAL DeterministicExecutionEngine, process real frames,
extract the real resulting audit_log, and feed it to
replay_and_verify_state_hashes -- not synthetic/hand-built records.
This is deliberate: the whole point of Path (b) is that replay through
the actual state machine reproduces the actual engine's behavior, so
the test data should come from that actual engine, not from records
constructed to look plausible.
"""

import hashlib

import numpy as np
import pytest

from deterministic_execution_engine import DeterministicExecutionEngine, ExecutionEngineError
from execution_kernel_contract import CoreExecutionFrame
from execution_module_contract import ExecutionResult
from execution_audit_contract import ExecutionAuditRecord
from kernel_state_replay import replay_and_verify_state_hashes


class _SimpleModule:
    """Succeeds on every frame except sequence_id == 2, which it fails."""
    module_id = "replay_test_module"

    def execute(self, frame, envelope):
        if frame.seq_id == 2:
            return ExecutionResult(
                seq_id=frame.seq_id, success=False,
                output_payload=np.zeros(256, dtype=np.float64),
                error_message="Deliberate failure for replay test.",
            )
        return ExecutionResult(
            seq_id=frame.seq_id, success=True,
            output_payload=frame.payload.copy(),
        )


class _AlwaysSucceeds:
    module_id = "clean_module"

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


# ---------------------------------------------------------------------
# 1. Clean history: full replay succeeds
# ---------------------------------------------------------------------

def test_clean_history_fully_verified():
    engine = DeterministicExecutionEngine(module=_AlwaysSucceeds())
    engine.initialize()
    engine.process_frame(_make_frame(0, 1.0, 1000))
    engine.process_frame(_make_frame(1, 2.0, 2000))
    engine.process_frame(_make_frame(2, 3.0, 3000))

    report = replay_and_verify_state_hashes(engine.audit_log)

    assert report.fully_verified is True
    assert report.total_records == 3
    assert report.verified_count == 3
    assert report.failures == []
    assert report.stopped_at_fault_index is None
    assert report.unverified_after_fault_count == 0


# ---------------------------------------------------------------------
# 2. Longer clean run -- confirms this isn't a small-N coincidence
# ---------------------------------------------------------------------

def test_replayed_hashes_match_original_engine_exactly_over_more_frames():
    engine = DeterministicExecutionEngine(module=_AlwaysSucceeds())
    engine.initialize()
    for i in range(5):
        engine.process_frame(_make_frame(i, float(i), 1000 * (i + 1)))

    report = replay_and_verify_state_hashes(engine.audit_log)

    assert report.fully_verified is True
    assert len(engine.audit_log) == 5
    assert report.verified_count == 5


# ---------------------------------------------------------------------
# 3. Fault truncation: replay stops at the fault, reports what's unverified
# ---------------------------------------------------------------------

def test_fault_terminated_history_with_nothing_after_it_is_fully_verified():
    """
    Corrected expectation: a history that legitimately ENDS at a fault
    -- with every record present, including the fault frame itself,
    successfully replayed and matched, and nothing known to be
    missing afterward -- IS fully_verified. The original version of
    this test asserted False here, on the theory that any fault
    should disqualify full verification. That was wrong: it punished
    the report for a fault occurring at all, not for any actual
    evidence of missing or unverifiable data. unverified_after_fault_count
    already captures the real risk (records that exist but couldn't be
    checked); stopped_at_fault_index alone is informational, not
    disqualifying.
    """
    engine = DeterministicExecutionEngine(module=_SimpleModule())
    engine.initialize()
    engine.process_frame(_make_frame(0, 1.0, 1000))
    engine.process_frame(_make_frame(1, 2.0, 2000))
    with pytest.raises(ExecutionEngineError):
        engine.process_frame(_make_frame(2, 3.0, 3000))  # _SimpleModule fails seq 2

    assert len(engine.audit_log) == 3  # frames 0, 1 succeeded, 2 failed but was audited

    report = replay_and_verify_state_hashes(engine.audit_log)

    assert report.fully_verified is True  # nothing left unchecked -- correct
    assert report.stopped_at_fault_index == 2
    assert report.unverified_after_fault_count == 0
    assert report.verified_count == 3
    assert report.failures == []


def test_records_appended_after_a_fault_are_marked_unverified_not_guessed():
    """
    Simulates what the log would look like if a reset+resume happened
    after the fault -- manually appending a post-fault record. The
    point here is narrower than a full reset scenario: replay must NOT
    silently continue past the fault and misverify these -- it must
    recognize it cannot proceed and report the count as unverified.
    """
    class _FailsOnSecondFrame:
        module_id = "fails_on_second_module"

        def execute(self, frame, envelope):
            if frame.seq_id == 1:
                return ExecutionResult(
                    seq_id=frame.seq_id, success=False,
                    output_payload=np.zeros(256, dtype=np.float64),
                    error_message="Deliberate failure on second frame.",
                )
            return ExecutionResult(
                seq_id=frame.seq_id, success=True,
                output_payload=frame.payload.copy(),
            )

    engine = DeterministicExecutionEngine(module=_FailsOnSecondFrame())
    engine.initialize()
    engine.process_frame(_make_frame(0, 1.0, 1000))
    with pytest.raises(ExecutionEngineError):
        engine.process_frame(_make_frame(1, 2.0, 2000))  # contiguous seq_id, faults here

    assert len(engine.audit_log) == 2  # frame 0 succeeded, frame 1 failed but was audited

    def h(seed):
        return hashlib.sha256(seed).digest()

    fabricated_post_reset_records = (
        ExecutionAuditRecord(
            sequence_id=0, input_hash=h(b"a"), prior_state_hash=h(b"b"),
            output_hash=h(b"c"), module_id="fails_on_second_module",
            success=True, frame_timestamp_ns=9000, error_message=None,
            generation_id=engine.state_machine.generation_id,
        ),
    )
    full_history = tuple(engine.audit_log) + fabricated_post_reset_records

    report = replay_and_verify_state_hashes(full_history)

    assert report.stopped_at_fault_index == 1  # index of the fault record
    assert report.unverified_after_fault_count == 1  # the fabricated record
    assert report.fully_verified is False  # correctly disqualified: something IS unverified
    assert report.total_records == 3


# ---------------------------------------------------------------------
# 4. Tampering detection: a corrupted prior_state_hash is caught
# ---------------------------------------------------------------------

def test_tampered_prior_state_hash_is_detected():
    engine = DeterministicExecutionEngine(module=_AlwaysSucceeds())
    engine.initialize()
    engine.process_frame(_make_frame(0, 1.0, 1000))
    engine.process_frame(_make_frame(1, 2.0, 2000))

    original = engine.audit_log

    tampered_second = ExecutionAuditRecord(
        sequence_id=original[1].sequence_id,
        input_hash=original[1].input_hash,
        prior_state_hash=hashlib.sha256(b"tampered").digest(),  # corrupted
        output_hash=original[1].output_hash,
        module_id=original[1].module_id,
        success=original[1].success,
        frame_timestamp_ns=original[1].frame_timestamp_ns,
        error_message=original[1].error_message,
        generation_id=original[1].generation_id,
    )
    tampered_history = (original[0], tampered_second)

    report = replay_and_verify_state_hashes(tampered_history)

    assert report.fully_verified is False
    assert len(report.failures) == 1
    assert "Record index 1" in report.failures[0]
    assert report.verified_count == 1  # only the first record matched


# ---------------------------------------------------------------------
# 5. Empty history
# ---------------------------------------------------------------------

def test_empty_history_is_trivially_fully_verified():
    report = replay_and_verify_state_hashes(())
    assert report.fully_verified is True
    assert report.total_records == 0
    assert report.verified_count == 0

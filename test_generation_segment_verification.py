"""
Generation Segment Verification - Tests
(test_generation_segment_verification.py)

Phase 2 of REPLAY_GENERATION_MODEL.md's Mode B decomposition. Test
data here is NOT fabricated hash bytes -- replay_and_verify_state_hashes()
constructs its own real KernelStateMachine and genuinely recomputes
hashes, so a "clean" test case has to come from a REAL engine run
(via DeterministicExecutionEngine.with_generation(), the same pattern
test_engine_policy_decision_emission.py already established this
session) rather than hand-built ExecutionAuditRecord objects with
made-up hash values -- those would simply fail to verify, correctly,
since they wouldn't match what a real KernelStateMachine derives.

Two categories: clean multi-segment verification (built from two real,
independently-constructed single-generation engine runs), and the
load-bearing cross-check's failure mode, deliberately triggered by
hand-constructing a GenerationSegment whose records actually span two
real generations -- something Phase 1's own segmentation could never
produce, but worth proving verify_segments() correctly flags if it's
ever handed corrupted input directly.
"""

import numpy as np
import pytest

from execution_kernel_contract import CoreExecutionFrame
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule
from generation_segmentation import GenerationSegment, segment_by_generation
from generation_segment_verification import verify_segments


_GEN_A = b"\xAA" * 16
_GEN_B = b"\xBB" * 16


def _make_frame(seq_id: int, seed_val: float = 1.0) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    return CoreExecutionFrame.create(seq_id=seq_id, timestamp_ns=1_000_000 + seq_id, payload=payload)


def _run_real_generation(generation_id: bytes, frame_count: int = 3):
    """
    Drives a real DeterministicExecutionEngine, seeded with an explicit
    generation_id via with_generation(), through frame_count real
    process_frame() calls. Returns the resulting engine.audit_log --
    genuinely hash-chained ExecutionAuditRecord objects, not fabricated
    ones. No authorizer needed; this is purely about producing a real,
    replayable audit trail.
    """
    engine = DeterministicExecutionEngine.with_generation(
        generation_id=generation_id, module=PhoenixAExecutionModule()
    )
    engine.initialize()
    for seq_id in range(frame_count):
        engine.process_frame(_make_frame(seq_id, seed_val=float(seq_id) + 1.0))
    return engine.audit_log


# ---------------------------------------------------------------------
# 1. Clean multi-segment verification
# ---------------------------------------------------------------------

def test_single_real_generation_segment_is_fully_verified():
    audit_log = _run_real_generation(_GEN_A, frame_count=4)

    segments = segment_by_generation(list(audit_log))
    results = verify_segments(segments)

    assert len(results) == 1
    assert results[0].generation_id == _GEN_A
    assert results[0].fully_verified is True
    assert results[0].unexpectedly_crosses_generation_boundary is False


def test_two_real_generations_both_independently_fully_verified():
    """
    The core Phase 1 + Phase 2 composition proof: two genuinely
    separate, real engine runs (different generation_id each),
    concatenated into one "log" the way they'd appear on disk after
    two lifetimes, segmented by Phase 1, then each segment
    independently verified by Phase 2. Both must come back fully
    verified, and -- the load-bearing cross-check -- NEITHER should
    report a generation boundary, since each segment is internally
    single-generation by construction.
    """
    gen_a_log = _run_real_generation(_GEN_A, frame_count=3)
    gen_b_log = _run_real_generation(_GEN_B, frame_count=3)

    combined_log = list(gen_a_log) + list(gen_b_log)
    segments = segment_by_generation(combined_log)
    assert len(segments) == 2  # sanity: Phase 1 actually split them

    results = verify_segments(segments)

    assert len(results) == 2
    for result in results:
        assert result.fully_verified is True
        assert result.unexpectedly_crosses_generation_boundary is False

    assert results[0].generation_id == _GEN_A
    assert results[1].generation_id == _GEN_B


def test_verify_segments_returns_one_result_per_segment_in_order():
    gen_a_log = _run_real_generation(_GEN_A, frame_count=2)
    gen_b_log = _run_real_generation(_GEN_B, frame_count=2)

    segments = segment_by_generation(list(gen_a_log) + list(gen_b_log))
    results = verify_segments(segments)

    assert [r.generation_id for r in results] == [s.generation_id for s in segments]
    assert [r.sequence_id_range for r in results] == [s.sequence_id_range for s in segments]


def test_empty_segment_list_returns_empty_result_list():
    assert verify_segments([]) == []


# ---------------------------------------------------------------------
# 2. The load-bearing cross-check's failure mode
# ---------------------------------------------------------------------

def test_segment_spanning_two_real_generations_is_flagged_not_silently_passed():
    """
    Phase 1's own segmentation could never produce this -- a segment
    is single-generation by construction. This hand-builds exactly the
    corrupted case Phase 2's contract says must never be silently
    accepted: a GenerationSegment CLAIMING one generation_id but whose
    records actually include a frame from a different real generation.
    Proves verify_segments() surfaces this via
    unexpectedly_crosses_generation_boundary, rather than either
    crashing uninformatively or -- worse -- reporting fully_verified
    on data that was never actually single-generation.
    """
    gen_a_log = _run_real_generation(_GEN_A, frame_count=2)
    gen_b_log = _run_real_generation(_GEN_B, frame_count=2)

    corrupted_segment = GenerationSegment(
        generation_id=_GEN_A,  # claims A
        records=tuple(gen_a_log) + (gen_b_log[0],),  # but includes a real B record
    )

    results = verify_segments([corrupted_segment])

    assert len(results) == 1
    assert results[0].unexpectedly_crosses_generation_boundary is True
    assert results[0].fully_verified is False
    assert results[0].replay_report.generation_boundary_index is not None

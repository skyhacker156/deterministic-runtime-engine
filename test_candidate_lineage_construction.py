"""
Candidate Lineage Construction - Tests
(test_candidate_lineage_construction.py)

Phase 3 of REPLAY_GENERATION_MODEL.md's Mode B decomposition. Same
"real data, not fabricated" discipline as Phase 2's tests -- edges are
only meaningful when built from genuinely Phase-2-verified segments,
so these tests drive real engine runs via
DeterministicExecutionEngine.with_generation(), same pattern as
test_generation_segment_verification.py.

AlwaysFailExecutionModule, defined below, exists specifically so the
fault_record_precedes_boundary=True test does not depend on
PhoenixAExecutionModule's own numerical guard behavior. An earlier
version of this test used an all-zero payload attempting to trigger
PhoenixAExecutionModule's near-zero-norm guard, on the assumption that
"guard" meant "rejects this input." It does not -- ExecutionResult's
own __post_init__ (execution_module_contract.py) enforces
np.all(np.isfinite(output_payload)) unconditionally, even for
success=False results, so a guard against near-zero norm almost
certainly exists to AVOID ever producing a non-finite payload, not to
force failure. That test failed loudly (DID NOT RAISE) rather than
silently passing wrong, which is what surfaced the bad assumption.
AlwaysFailExecutionModule replaces the guess entirely: it is
deterministic by construction, decoupling this file's tests from any
other module's internal numerical behavior. Phase 3's tests should
only be able to fail because of a bug in candidate_lineage_construction.py,
never because of what does or doesn't make Phoenix A's guard trigger.
"""

import numpy as np
import pytest

from execution_kernel_contract import CoreExecutionFrame
from execution_module_contract import ExecutionResult
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule
from generation_segmentation import segment_by_generation
from generation_segment_verification import verify_segments
from candidate_lineage_construction import construct_candidate_lineage


_GEN_A = b"\xAA" * 16
_GEN_B = b"\xBB" * 16


class AlwaysFailExecutionModule:
    """
    Test-only ExecutionModule (structural Protocol match -- see
    execution_module_contract.py) that deterministically fails every
    frame it's given. Used only where a test needs a genuine
    execution failure and must not depend on any other module's
    specific implementation details to get one.
    """

    @property
    def module_id(self) -> str:
        return "always_fail_test_module"

    def execute(self, frame: CoreExecutionFrame, envelope) -> ExecutionResult:
        return ExecutionResult(
            seq_id=frame.seq_id,
            success=False,
            output_payload=np.zeros(256, dtype=np.float64),  # finite; satisfies ExecutionResult's own validation
            metrics={},
            error_message="AlwaysFailExecutionModule: deterministic test failure",
        )


def _make_frame(seq_id: int, seed_val: float = 1.0) -> CoreExecutionFrame:
    payload = np.full(256, fill_value=seed_val, dtype=np.float64)
    return CoreExecutionFrame.create(seq_id=seq_id, timestamp_ns=1_000_000 + seq_id, payload=payload)


def _run_real_generation(generation_id: bytes, frame_count: int = 3):
    engine = DeterministicExecutionEngine.with_generation(
        generation_id=generation_id, module=PhoenixAExecutionModule()
    )
    engine.initialize()
    for seq_id in range(frame_count):
        engine.process_frame(_make_frame(seq_id, seed_val=float(seq_id) + 1.0))
    return engine.audit_log


def _run_generation_with_single_failing_frame(generation_id: bytes):
    """
    A one-record segment whose only record failed -- deterministic via
    AlwaysFailExecutionModule, no numerical guessing. Sufficient for
    what this test actually needs: _last_record_is_fault() only
    inspects the segment's LAST record, so a single-frame segment
    exercises exactly that property without needing several successful
    frames first.
    """
    engine = DeterministicExecutionEngine.with_generation(
        generation_id=generation_id, module=AlwaysFailExecutionModule()
    )
    engine.initialize()
    with pytest.raises(Exception):
        engine.process_frame(_make_frame(0))
    return engine.audit_log


# ---------------------------------------------------------------------
# 1. Clean two-segment edge construction
# ---------------------------------------------------------------------

def test_two_verified_generations_produce_one_edge():
    gen_a_log = _run_real_generation(_GEN_A, frame_count=3)
    gen_b_log = _run_real_generation(_GEN_B, frame_count=3)

    segments = segment_by_generation(list(gen_a_log) + list(gen_b_log))
    results = verify_segments(segments)
    graph = construct_candidate_lineage(segments, results)

    assert len(graph.verified_segments) == 2
    assert len(graph.edges) == 1
    assert graph.coverage_is_partial is False

    edge = graph.edges[0]
    assert edge.from_generation_id == _GEN_A
    assert edge.to_generation_id == _GEN_B
    assert "PLAUSIBLE, not proven" in edge.continuity_caveat
    assert "candidate" in edge.explanation().lower() or "Candidate" in edge.explanation()


def test_single_verified_generation_produces_no_edges():
    gen_a_log = _run_real_generation(_GEN_A, frame_count=4)

    segments = segment_by_generation(list(gen_a_log))
    results = verify_segments(segments)
    graph = construct_candidate_lineage(segments, results)

    assert len(graph.verified_segments) == 1
    assert len(graph.edges) == 0
    assert graph.coverage_is_partial is False


def test_three_verified_generations_produce_two_edges_in_order():
    _GEN_C = b"\xCC" * 16
    gen_a_log = _run_real_generation(_GEN_A, frame_count=2)
    gen_b_log = _run_real_generation(_GEN_B, frame_count=2)
    gen_c_log = _run_real_generation(_GEN_C, frame_count=2)

    combined = list(gen_a_log) + list(gen_b_log) + list(gen_c_log)
    segments = segment_by_generation(combined)
    results = verify_segments(segments)
    graph = construct_candidate_lineage(segments, results)

    assert len(graph.edges) == 2
    assert graph.edges[0].from_generation_id == _GEN_A
    assert graph.edges[0].to_generation_id == _GEN_B
    assert graph.edges[1].from_generation_id == _GEN_B
    assert graph.edges[1].to_generation_id == _GEN_C


# ---------------------------------------------------------------------
# 2. Partial coverage -- excluded segments never silently bridged
# ---------------------------------------------------------------------

def test_unverified_segment_is_excluded_and_no_edge_bridges_across_it():
    """
    Simulates Phase 2 reporting one segment as NOT fully verified (via
    a hand-corrupted segment claiming gen A but containing a real gen B
    record, same technique as
    test_segment_spanning_two_real_generations_is_flagged_not_silently_passed).
    Confirms: the corrupted segment is excluded, coverage_is_partial is
    True, and NO edge is built connecting the segment before it to the
    segment after it -- bridging across unverified data would be
    exactly the false continuity claim Phase 3 must never make.
    """
    from generation_segmentation import GenerationSegment

    gen_a_log = _run_real_generation(_GEN_A, frame_count=2)
    gen_b_log = _run_real_generation(_GEN_B, frame_count=2)
    _GEN_C = b"\xCC" * 16
    gen_c_log = _run_real_generation(_GEN_C, frame_count=2)

    corrupted_middle_segment = GenerationSegment(
        generation_id=_GEN_B,
        records=tuple(gen_b_log) + (gen_c_log[0],),  # smuggled-in real C record
    )

    segments = [
        GenerationSegment(generation_id=_GEN_A, records=tuple(gen_a_log)),
        corrupted_middle_segment,
        GenerationSegment(generation_id=_GEN_C, records=tuple(gen_c_log)),
    ]
    results = verify_segments(segments)
    assert results[1].fully_verified is False  # sanity: corruption detected by Phase 2

    graph = construct_candidate_lineage(segments, results)

    assert graph.coverage_is_partial is True
    assert len(graph.excluded_segments) == 1
    assert graph.excluded_segments[0].generation_id == _GEN_B
    # No edge at all should span across the excluded middle segment --
    # A and C are not adjacent in the original order once B is
    # excluded, and this function never reconnects around a gap.
    assert len(graph.edges) == 0


# ---------------------------------------------------------------------
# 3. Misuse guard
# ---------------------------------------------------------------------

def test_mismatched_length_inputs_raise_value_error():
    gen_a_log = _run_real_generation(_GEN_A, frame_count=2)
    segments = segment_by_generation(list(gen_a_log))
    results = verify_segments(segments)

    with pytest.raises(ValueError, match="same length"):
        construct_candidate_lineage(segments, results + results)  # deliberately mismatched


# ---------------------------------------------------------------------
# 4. Fault-record corroboration -- True and False cases
# ---------------------------------------------------------------------

def test_edge_without_preceding_fault_record_is_not_marked_suspicious():
    gen_a_log = _run_real_generation(_GEN_A, frame_count=3)  # ends success=True
    gen_b_log = _run_real_generation(_GEN_B, frame_count=3)

    segments = segment_by_generation(list(gen_a_log) + list(gen_b_log))
    results = verify_segments(segments)
    graph = construct_candidate_lineage(segments, results)

    edge = graph.edges[0]
    assert edge.fault_record_precedes_boundary is False
    assert "NOT suspicious" in edge.explanation()


def test_edge_with_preceding_fault_record_is_noted_as_corroborating_not_proof():
    """
    Uses AlwaysFailExecutionModule -- deterministic, no dependency on
    PhoenixAExecutionModule's actual numerical behavior. See module
    docstring for why the original version of this test (an all-zero
    payload guess) was replaced.
    """
    gen_a_log = _run_generation_with_single_failing_frame(_GEN_A)
    gen_b_log = _run_real_generation(_GEN_B, frame_count=2)

    assert gen_a_log[-1].success is False  # sanity: deterministic by construction, but still checked

    segments = segment_by_generation(list(gen_a_log) + list(gen_b_log))
    results = verify_segments(segments)
    assert results[0].fully_verified is True  # a trailing fault with nothing after IS fully_verified

    graph = construct_candidate_lineage(segments, results)

    edge = graph.edges[0]
    assert edge.fault_record_precedes_boundary is True
    explanation = edge.explanation()
    assert "consistent with" in explanation
    assert "not proof" in explanation


# ---------------------------------------------------------------------
# 3. Adjacent same-generation segments -- found via adversarial review
#    (highest-information untested cell in the campaign matrix)
# ---------------------------------------------------------------------

def test_adjacent_segments_sharing_a_generation_id_raise_value_error():
    """
    Phase 1's segment_by_generation() structurally guarantees adjacent
    segments always have different generation_ids -- that is what
    makes them separate segments in the first place. This function
    itself never verified that precondition, even though it already
    defends the comparably load-bearing length-match precondition with
    a raise (test_mismatched_length_inputs_raise_value_error).

    This hand-constructs exactly the malformed input Phase 1 could
    never produce: two REAL, independently-verified segments (both
    genuinely hash-chained, both fully_verified) that happen to share
    one generation_id, assembled as adjacent list entries -- bypassing
    segment_by_generation() entirely. Before this fix, this would have
    silently produced a CandidateLineageEdge with
    from_generation_id == to_generation_id -- not a malformed length,
    a "boundary" that doesn't represent any real transition at all.
    """
    from generation_segmentation import GenerationSegment

    gen_a_log_1 = _run_real_generation(_GEN_A, frame_count=2)
    gen_a_log_2 = _run_real_generation(_GEN_A, frame_count=2)

    malformed_segments = [
        GenerationSegment(generation_id=_GEN_A, records=tuple(gen_a_log_1)),
        GenerationSegment(generation_id=_GEN_A, records=tuple(gen_a_log_2)),
    ]
    results = verify_segments(malformed_segments)
    assert results[0].fully_verified is True and results[1].fully_verified is True

    with pytest.raises(ValueError, match="same generation_id"):
        construct_candidate_lineage(malformed_segments, results)


def test_mismatched_segment_and_verification_result_pair_raises_value_error():
    """
    MB-004's Omission finding: segments and verification_results are
    two SEPARATE parameters. Before this fix, nothing verified that
    verification_results[i] was genuinely computed FROM segments[i] --
    a caller supplying a mismatched pair would get an edge whose
    reported identity (from verification_results[i].generation_id) and
    whose fault-evidence (from segments[i]'s ACTUAL records, via
    _last_record_is_fault) came from two different, uncorrelated
    generations.

    Built entirely from real, genuinely valid objects -- segment A and
    result B are each individually completely legitimate, exactly as
    verify_segments() would produce. The violation is purely in how
    they're paired.
    """
    gen_a_log = _run_real_generation(_GEN_A, frame_count=2)
    gen_b_log = _run_real_generation(_GEN_B, frame_count=2)

    segments_a = segment_by_generation(list(gen_a_log))
    segments_b = segment_by_generation(list(gen_b_log))
    results_a = verify_segments(segments_a)
    results_b = verify_segments(segments_b)

    # segments_a[0] is genuinely generation A's real segment. results_b[0]
    # is genuinely generation B's real, valid verification result. Neither
    # is malformed on its own -- only the pairing is wrong.
    with pytest.raises(ValueError, match="does not match"):
        construct_candidate_lineage(segments_a, results_b)

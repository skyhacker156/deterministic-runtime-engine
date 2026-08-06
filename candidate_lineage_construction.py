"""
Candidate Lineage Construction - Sentinel Framework
(candidate_lineage_construction.py)

Implements Phase 3 of REPLAY_GENERATION_MODEL.md's Mode B
decomposition: constructs the candidate lineage graph from Phase 2's
independently-verified segments. "Candidate," never "the" -- this
module's entire naming and documentation deliberately avoids implying
proof, per Phase 3's own SHALL NOT clause:

    "SHALL NOT describe its output as 'connecting' or 'the lineage,'
    unqualified... Output, documentation, and any future UI surfacing
    this graph should say 'candidate lineage' or 'inferred lineage,'
    not 'the lineage' or 'reconstructed history.'"

NO UNIQUENESS CLAIM, same discipline as Phases 1 and 2, restated here
because Phase 3 is the one phase where the temptation to make this
claim is real: this module constructs A candidate graph consistent
with the evidence. It does not claim, check, or have any way of
checking whether that candidate is the ONLY graph consistent with the
evidence. See REPLAY_GENERATION_MODEL.md's single-instance-continuity
caveat for why uniqueness is not just unbuilt here but likely
unprovable under the current schema without additional persisted
evidence (the deliberately-deferred GenerationTransitionRecord
question).

WHAT AN EDGE ACTUALLY ASSERTS: adjacency between two independently
verified segments in Phase 1's output order. It does NOT assert that
the two segments come from the same kernel instance -- nothing in the
current schema distinguishes a genuine reset-continuation from a
coincidental fresh-instance collision sharing a boundary (see
kernel_state_replay.py's own docstring, limitation 1). Every
CandidateLineageEdge carries this caveat explicitly, via
continuity_caveat, so it travels with the artifact rather than living
only in this docstring.

FAULT-RECORD CORROBORATION, not proof: an edge may note whether the
segment immediately before it ends in a record with success=False --
consistent with (but not proof of) an administrative reset. Per
REPLAY_GENERATION_MODEL.md's own caveat, some fault paths trip FAULTED
before an audit record is ever constructed for the triggering frame,
so a reset caused by a corrupted or out-of-order frame can leave NO
fault record at all. fault_record_precedes_boundary being False must
never be treated as suspicious for that reason -- see
CandidateLineageEdge.explanation() for how this is worded to avoid
that misreading.

COVERAGE, EXPLICIT: any segment Phase 2 did not fully verify is
excluded from the candidate graph entirely -- never silently bridged
around. CandidateLineageGraph.coverage_is_partial exists specifically
so a caller cannot accidentally treat a graph missing segments as
complete.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from generation_segmentation import GenerationSegment
from generation_segment_verification import SegmentVerificationResult


@dataclass(frozen=True)
class CandidateLineageEdge:
    """
    One inferred, unproven connection between two adjacent,
    independently-verified segments. See module docstring for what
    this does and does not assert.
    """
    from_generation_id: bytes
    to_generation_id: bytes
    fault_record_precedes_boundary: bool

    @property
    def continuity_caveat(self) -> str:
        return (
            "This edge asserts causal continuity is PLAUSIBLE, not proven. "
            "Adjacency in the persisted log does not prove these two segments "
            "belong to the same kernel instance -- nothing in the current "
            "schema distinguishes a genuine reset-continuation from a "
            "coincidental fresh-instance collision."
        )

    def explanation(self) -> str:
        if self.fault_record_precedes_boundary:
            evidence_note = (
                "The segment immediately preceding this boundary ends in a "
                "record with success=False -- consistent with an "
                "administrative reset, but not proof of one."
            )
        else:
            evidence_note = (
                "The segment immediately preceding this boundary does NOT "
                "end in a fault record. This is NOT suspicious -- the "
                "schema does not guarantee a fault record exists for every "
                "real reset."
            )
        return (
            f"Candidate edge: generation {self.from_generation_id.hex()} -> "
            f"{self.to_generation_id.hex()}. {evidence_note} {self.continuity_caveat}"
        )


@dataclass(frozen=True)
class CandidateLineageGraph:
    """
    The candidate lineage -- the graph that best fits the evidence
    from independently Phase-2-verified segments, in Phase 1's
    original order. Never "the lineage" in any documentation or
    output derived from this type.
    """
    verified_segments: Tuple[SegmentVerificationResult, ...]
    edges: Tuple[CandidateLineageEdge, ...]
    excluded_segments: Tuple[SegmentVerificationResult, ...]

    @property
    def coverage_is_partial(self) -> bool:
        """
        True if any segment from Phase 1's output was excluded from
        this candidate graph because Phase 2 did not fully verify it.
        A caller MUST check this before treating the graph as covering
        the complete history -- per Phase 3's SHALL NOT clause, full
        lineage verification must never be claimed on partial coverage.
        """
        return len(self.excluded_segments) > 0


def _last_record_is_fault(segment: GenerationSegment) -> bool:
    """
    Whether the last record in this segment has success=False.
    Corroborating evidence only -- see module docstring's "FAULT-RECORD
    CORROBORATION" section for why False must never be read as
    suspicious.
    """
    if not segment.records:
        return False
    return not segment.records[-1].success


def construct_candidate_lineage(
    segments: List[GenerationSegment],
    verification_results: List[SegmentVerificationResult],
) -> CandidateLineageGraph:
    """
    Builds the candidate lineage graph. segments and verification_results
    MUST be the same length, in the same order -- exactly what
    generation_segment_verification.verify_segments(segments) already
    guarantees when called as verify_segments(segments).

    Only segments Phase 2 fully verified are included in the graph.
    Edges are built only between segments that are BOTH fully verified
    AND consecutive in the original Phase 1 order -- an edge is never
    built bridging across an excluded segment, since that would assert
    continuity through a gap of unknown, unverified data. A run of
    excluded segments simply breaks the candidate graph into
    disconnected pieces at that point; this function does not attempt
    to reconnect around them.
    """
    if len(segments) != len(verification_results):
        raise ValueError(
            f"segments and verification_results must be the same length "
            f"and in the same order (got {len(segments)} segments, "
            f"{len(verification_results)} results) -- expected "
            f"verification_results = verify_segments(segments)."
        )

    verified_results = [r for r in verification_results if r.fully_verified]
    excluded_results = [r for r in verification_results if not r.fully_verified]

    edges: List[CandidateLineageEdge] = []
    for i in range(len(segments) - 1):
        current_segment, current_result = segments[i], verification_results[i]
        next_result = verification_results[i + 1]

        if current_result.fully_verified and next_result.fully_verified:
            edges.append(CandidateLineageEdge(
                from_generation_id=current_result.generation_id,
                to_generation_id=next_result.generation_id,
                fault_record_precedes_boundary=_last_record_is_fault(current_segment),
            ))

    return CandidateLineageGraph(
        verified_segments=tuple(verified_results),
        edges=tuple(edges),
        excluded_segments=tuple(excluded_results),
    )

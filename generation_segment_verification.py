"""
Generation Segment Verification - Sentinel Framework
(generation_segment_verification.py)

Implements Phase 2 of REPLAY_GENERATION_MODEL.md's Mode B
decomposition: independent verification of each GenerationSegment
(Phase 1's output, generation_segmentation.py) via
kernel_state_replay.py's EXISTING, UNMODIFIED
replay_and_verify_state_hashes() / SequentialReplayKernelVerifier.

Per Phase 2's own SHALL clauses:

    "SHALL verify each segment using kernel_state_replay.py's existing
    replay_and_verify_state_hashes(), unmodified, seeded via
    KernelStateMachine.from_history() with that segment's own
    generation_id."

This is satisfied automatically, not by anything this module does
itself: SequentialReplayKernelVerifier.verify() constructs its own
fresh KernelStateMachine via from_history(generation_id=
execution_history[0].generation_id, ...) internally, on every call --
see kernel_state_replay.py's own source. Since a GenerationSegment's
records all share one generation_id by construction
(generation_segmentation.py's segment_by_generation() guarantees
this), calling .verify(segment.records) automatically seeds the
replay with that segment's own generation_id. This module adds no new
seeding logic of its own.

    "SHALL treat each segment's verification as fully independent of
    every other segment's."

Also automatic: each call to .verify() constructs its own machine
internally; nothing in this module shares a KernelStateMachine,
verifier instance state, or any other object across segments. One
segment, one .verify() call, one fresh machine.

THE LOAD-BEARING CROSS-CHECK, restated as executable code:

    If Phase 1 segmented correctly, every Phase 2 replay of a single
    segment must report generation_boundary_index is None.

SegmentVerificationResult.unexpectedly_crosses_generation_boundary
below is exactly this check, made queryable per segment. If it is ever
True for a segment Phase 1 itself produced, that is a bug in Phase 1's
segmentation or evidence the underlying data was more tangled than a
clean single-lineage history (see REPLAY_GENERATION_MODEL.md's own
account of what such a finding would mean) -- NOT a normal outcome to
route around silently.

NO UNIQUENESS CLAIM, same discipline as Phase 1: a fully-verified
segment means its OWN hash chain replays and matches, nothing more.
This module makes no claim about whether the segmentation itself is
the only one consistent with the evidence -- that question belongs to
Phase 3, if addressed at all, and remains explicitly out of scope
here.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from generation_segmentation import GenerationSegment
from kernel_state_replay import (
    KernelStateVerifier,
    SequentialReplayKernelVerifier,
    KernelReplayReport,
)


@dataclass(frozen=True)
class SegmentVerificationResult:
    """
    One segment's independent replay result, paired with the
    identifying information from the GenerationSegment it came from --
    so a caller working through a list of these doesn't need to zip
    them back against the original segments to know which is which.
    """
    generation_id: bytes
    sequence_id_range: Tuple[int, int]
    replay_report: KernelReplayReport

    @property
    def fully_verified(self) -> bool:
        return self.replay_report.fully_verified

    @property
    def unexpectedly_crosses_generation_boundary(self) -> bool:
        """
        The load-bearing cross-check from REPLAY_GENERATION_MODEL.md's
        Phase 2 contract, made directly queryable. True here for a
        segment Phase 1 itself produced means Phase 1 mis-segmented,
        or the data was more tangled than a clean single-lineage
        history (e.g. two generations' records interleaved by
        sequence_id rather than cleanly partitioned). Phase 1's own
        SHALL clause is supposed to catch and reject genuinely
        tangled input before it reaches here -- so this being True
        for Phase-1-produced input is itself a signal something in
        that rejection has a gap.
        """
        return self.replay_report.generation_boundary_index is not None


def verify_segments(
    segments: List[GenerationSegment],
    verifier: Optional[KernelStateVerifier] = None,
) -> List[SegmentVerificationResult]:
    """
    Verifies each segment independently, in order, via the given
    KernelStateVerifier (defaults to SequentialReplayKernelVerifier(),
    the existing Path B implementation). Accepts any KernelStateVerifier
    implementation -- same substitutability
    reconstruct_cold_boot_with_replay() already established, so a
    future Path A implementation (persisted-field recomputation,
    should a schema change ever add the raw derivation inputs) could
    be substituted here without this function changing.

    Does not aggregate, connect, or compare segments against each
    other -- that is Phase 3's job, if built. This function's only
    contract is: N segments in, N independent SegmentVerificationResults
    out, one per segment, in the same order.

    SEGMENT LABEL MUST MATCH ITS OWN RECORDS (NEW, 2026-08-08 --
    Boundary Crossing finding from the adversarial campaign):
    GenerationSegment is a plain frozen dataclass with no validation
    of its own -- nothing enforces that generation_id (the external
    label) actually matches what its records field contains.
    replay_and_verify_state_hashes() (Phase 2's underlying verifier)
    independently derives its OWN reference generation_id from
    execution_history[0].generation_id and checks every record against
    THAT -- but it has no parameter for an externally-claimed label to
    cross-check against, and this function was previously trusting
    segment.generation_id wholesale when constructing
    SegmentVerificationResult, never comparing it to what the records
    themselves actually attest to. segment_by_generation() (Phase 1)
    always derives generation_id FROM the records, so this mismatch
    can never occur via the real pipeline -- but a caller constructing
    GenerationSegment directly bypasses that guarantee entirely. Now
    checked explicitly, before any result is built.
    """
    if verifier is None:
        verifier = SequentialReplayKernelVerifier()

    results: List[SegmentVerificationResult] = []
    for segment in segments:
        if segment.records and segment.generation_id != segment.records[0].generation_id:
            raise ValueError(
                f"GenerationSegment.generation_id ({segment.generation_id.hex()}) does "
                f"not match its own records' actual generation_id "
                f"({segment.records[0].generation_id.hex()}) -- this segment's external "
                f"label does not describe the data it actually contains. "
                f"segment_by_generation() derives generation_id FROM the records "
                f"themselves and would never produce this mismatch; a caller "
                f"constructing GenerationSegment directly bypassed that guarantee."
            )
        report = verifier.verify(segment.records)
        results.append(SegmentVerificationResult(
            generation_id=segment.generation_id,
            sequence_id_range=segment.sequence_id_range,
            replay_report=report,
        ))
    return results

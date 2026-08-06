"""
Generation Segmentation - Sentinel Framework
(generation_segmentation.py)

Implements Phase 1 of REPLAY_GENERATION_MODEL.md's Mode B decomposition
-- and only Phase 1. Pure generation-boundary discovery over an
already-reconstructed ExecutionAuditRecord history:

    Generation 1
    Frames 1-84

    Generation 2
    Frames 85-141

    Generation 3
    Frames 142-...

Nothing here replays anything, verifies any hash, or constructs a
KernelStateMachine -- this is graph discovery over the existing
generation_id field, matching Phase 1's own SHALL NOT clauses in
REPLAY_GENERATION_MODEL.md exactly:

    "SHALL NOT construct a KernelStateMachine, call from_history(), or
    perform any hash verification. Phase 1 is a pure function over
    already-persisted generation_id values."

Scoped to ExecutionAuditRecord specifically, not made generic over
every record type carrying generation_id: kernel_state_replay.py's
replay_and_verify_state_hashes() (Phase 2) operates on
List[ExecutionAuditRecord] (see cold_boot_replay_extension.py's
execution_history), so that is the concrete, demonstrated shape Phase
1's output needs to feed. Genericizing this to DecisionRecord or
PolicyDecisionRecord segmentation is a natural future extension IF a
real consumer needs it -- not built preemptively, same "reserved
extension point" discipline already applied to the verification
pipeline's dispatcher question in VERIFICATION_PIPELINE_MODEL.md.

NO UNIQUENESS CLAIM, deliberately: this module (and Phase 1 generally)
makes no claim about whether a given segmentation is the only one
consistent with the evidence -- it is a straightforward, deterministic
grouping of records by their own persisted generation_id field. The
uniqueness question belongs to Phase 3, if it is ever addressed at
all, and REPLAY_GENERATION_MODEL.md's Phase 3 explicitly disclaims it
("constructs the graph that best fits the evidence," never "the only
possible lineage"). This module does not raise or resolve that
question in either direction.
"""

from dataclasses import dataclass
from typing import List, Tuple

from execution_audit_contract import ExecutionAuditRecord


class UnsegmentableHistoryError(Exception):
    """
    Raised when a generation_id that was already seen and left behind
    reappears after a later, different generation_id was already
    witnessed. Per Phase 1's own SHALL clause in
    REPLAY_GENERATION_MODEL.md: this is not a valid single-lineage
    history -- it indicates either data corruption or multiple
    interleaved engine instances sharing one log (see
    kernel_state_replay.py's own docstring, limitation 1, "SINGLE
    kernel/engine run only"). Segmentation refuses to guess which; it
    flags the history as unsegmentable rather than silently producing
    a segmentation that ignores the inconsistency.
    """
    pass


@dataclass(frozen=True)
class GenerationSegment:
    """
    One contiguous range of ExecutionAuditRecords sharing a single
    generation_id, in the order given to segment_by_generation().
    Immutable, independently inspectable per Phase 1's own SHALL
    clause: generation_id, the record range, and boundary positions
    are all directly readable without Phase 2 or Phase 3 ever running.
    """
    generation_id: bytes
    records: Tuple[ExecutionAuditRecord, ...]

    @property
    def sequence_id_range(self) -> Tuple[int, int]:
        """(first sequence_id, last sequence_id) in this segment, as
        given -- not independently re-sorted or validated for
        monotonicity here. Sequence ordering within a segment is
        causal_history_verifier.py's Check 2's concern, a different
        layer; this property just reports what's present."""
        return (self.records[0].sequence_id, self.records[-1].sequence_id)


def segment_by_generation(records: List[ExecutionAuditRecord]) -> List[GenerationSegment]:
    """
    Groups records into contiguous GenerationSegments by generation_id,
    preserving the input order. A boundary is any point where
    consecutive records show a generation_id change -- the same signal
    kernel_state_replay.py already checks for a single boundary; this
    checks for every boundary instead of stopping at the first.

    Raises UnsegmentableHistoryError if a generation_id that was
    already closed out reappears later -- see that exception's
    docstring.

    Empty input returns an empty list. A single-generation input
    (the common case today, since Mode B multi-generation lineages
    don't yet exist in practice) returns a list of exactly one segment
    containing every record.
    """
    if not records:
        return []

    segments: List[GenerationSegment] = []
    seen_generations = set()
    current_generation = records[0].generation_id
    current_batch: List[ExecutionAuditRecord] = []

    for record in records:
        if record.generation_id != current_generation:
            segments.append(GenerationSegment(
                generation_id=current_generation,
                records=tuple(current_batch),
            ))
            seen_generations.add(current_generation)

            if record.generation_id in seen_generations:
                raise UnsegmentableHistoryError(
                    f"generation_id {record.generation_id.hex()} reappears after "
                    f"a later, different generation was already witnessed -- not "
                    f"a valid single-lineage history. This indicates data "
                    f"corruption or multiple interleaved engine instances "
                    f"sharing one log."
                )

            current_generation = record.generation_id
            current_batch = [record]
        else:
            current_batch.append(record)

    segments.append(GenerationSegment(
        generation_id=current_generation,
        records=tuple(current_batch),
    ))

    return segments

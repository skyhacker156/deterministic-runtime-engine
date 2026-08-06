"""
Generation Segmentation - Tests
(test_generation_segmentation.py)

Phase 1 of REPLAY_GENERATION_MODEL.md's Mode B decomposition. Three
categories: clean segmentation (0, 1, 2, and 3+ generations), the
reappearance/corruption case, and a structural check that this module
genuinely never touches KernelStateMachine or hash verification --
Phase 1's own SHALL NOT clauses, checked, not just trusted.
"""

import hashlib
import inspect

import pytest

from execution_audit_contract import ExecutionAuditRecord
from generation_segmentation import (
    GenerationSegment,
    UnsegmentableHistoryError,
    segment_by_generation,
)


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


def make_record(sequence_id, generation_id, module_id="phoenix_a_core_v1", success=True):
    return ExecutionAuditRecord(
        sequence_id=sequence_id,
        input_hash=_hash32(f"in_{sequence_id}".encode()),
        prior_state_hash=_hash32(f"prior_{sequence_id}".encode()),
        output_hash=_hash32(f"out_{sequence_id}".encode()),
        module_id=module_id,
        success=success,
        frame_timestamp_ns=1000 + sequence_id,
        generation_id=generation_id,
        error_message=None,
    )


_GEN_A = b"\xAA" * 16
_GEN_B = b"\xBB" * 16
_GEN_C = b"\xCC" * 16


# ---------------------------------------------------------------------
# 1. Clean segmentation
# ---------------------------------------------------------------------

def test_empty_history_returns_empty_list():
    assert segment_by_generation([]) == []


def test_single_generation_returns_one_segment():
    records = [make_record(i, _GEN_A) for i in range(5)]

    segments = segment_by_generation(records)

    assert len(segments) == 1
    assert segments[0].generation_id == _GEN_A
    assert len(segments[0].records) == 5
    assert segments[0].sequence_id_range == (0, 4)


def test_two_generations_produce_two_ordered_segments():
    gen_a_records = [make_record(i, _GEN_A) for i in range(3)]      # seq 0,1,2
    gen_b_records = [make_record(i, _GEN_B) for i in range(3, 6)]   # seq 3,4,5

    segments = segment_by_generation(gen_a_records + gen_b_records)

    assert len(segments) == 2
    assert segments[0].generation_id == _GEN_A
    assert segments[0].sequence_id_range == (0, 2)
    assert segments[1].generation_id == _GEN_B
    assert segments[1].sequence_id_range == (3, 5)


def test_three_generations_produce_three_segments():
    records = (
        [make_record(i, _GEN_A) for i in range(2)]
        + [make_record(i, _GEN_B) for i in range(2, 5)]
        + [make_record(i, _GEN_C) for i in range(5, 7)]
    )

    segments = segment_by_generation(records)

    assert len(segments) == 3
    assert [s.generation_id for s in segments] == [_GEN_A, _GEN_B, _GEN_C]
    assert segments[0].sequence_id_range == (0, 1)
    assert segments[1].sequence_id_range == (2, 4)
    assert segments[2].sequence_id_range == (5, 6)


def test_segment_records_preserve_original_objects_and_order():
    """
    Phase 1 groups; it does not reconstruct, re-derive, or re-hash
    anything. The exact same ExecutionAuditRecord objects passed in
    come back out, in order, inside their segment.
    """
    original_records = [make_record(i, _GEN_A) for i in range(4)]

    segments = segment_by_generation(original_records)

    assert list(segments[0].records) == original_records
    for original, segmented in zip(original_records, segments[0].records):
        assert original is segmented  # same object, not a copy or reconstruction


# ---------------------------------------------------------------------
# 2. Reappearance / corruption case
# ---------------------------------------------------------------------

def test_generation_reappearing_after_a_later_generation_is_unsegmentable():
    """
    Gen A, then Gen B, then Gen A again -- not a valid single-lineage
    history. Must raise, not silently produce a 3-segment result that
    pretends this is fine.
    """
    records = (
        [make_record(i, _GEN_A) for i in range(2)]        # seq 0,1
        + [make_record(i, _GEN_B) for i in range(2, 4)]    # seq 2,3
        + [make_record(4, _GEN_A)]                          # seq 4 -- A reappears
    )

    with pytest.raises(UnsegmentableHistoryError, match="reappears"):
        segment_by_generation(records)


def test_reappearance_error_names_the_reappearing_generation():
    records = [
        make_record(0, _GEN_A),
        make_record(1, _GEN_B),
        make_record(2, _GEN_A),
    ]

    with pytest.raises(UnsegmentableHistoryError, match=_GEN_A.hex()):
        segment_by_generation(records)


# ---------------------------------------------------------------------
# 3. Structural check: Phase 1's SHALL NOT clauses actually hold
# ---------------------------------------------------------------------

def test_module_never_imports_kernel_state_machine_or_hashlib():
    """
    Phase 1's own SHALL NOT clause: "SHALL NOT construct a
    KernelStateMachine, call from_history(), or perform any hash
    verification." Checked via AST-based import inspection, mirroring
    test_cold_boot_reconstruction.py's own
    test_shall_5_module_never_reimplements_hash_computation and
    test_shall_5_state_hash_is_unavailable_kernel_state_never_imported
    -- NOT a raw substring search, which would false-positive on this
    module's own docstring (it explicitly names KernelStateMachine and
    hashlib while explaining they are NOT used, exactly the same trap
    those two existing tests were built to avoid). Checking the parsed
    import statements directly avoids it.
    """
    import ast
    import generation_segmentation

    tree = ast.parse(inspect.getsource(generation_segmentation))
    imported_names = set()
    imported_members = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)
            imported_members.update(alias.name for alias in node.names)

    assert "hashlib" not in imported_names, (
        f"generation_segmentation.py actually imports hashlib -- this "
        f"violates Phase 1's 'no hash verification' constraint. "
        f"Imports found: {imported_names}"
    )
    assert "execution_kernel_state" not in imported_names, (
        f"generation_segmentation.py actually imports execution_kernel_state -- "
        f"this violates Phase 1's 'no KernelStateMachine construction' "
        f"constraint. Imports found: {imported_names}"
    )
    assert "kernel_state_replay" not in imported_names, (
        f"generation_segmentation.py actually imports kernel_state_replay -- "
        f"Phase 1 must not depend on Phase 2's replay machinery at all. "
        f"Imports found: {imported_names}"
    )
    assert "KernelStateMachine" not in imported_members
    assert "from_history" not in imported_members

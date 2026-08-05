"""
Integration Tests - Full Pipeline Replay with Audit Chain Verification
(test_replay_engine_audit_chain.py)

Verifies Step 3: replay_engine.py's execute_full_pipeline_replay and
verify_causal_chain_determinism correctly drive real telemetry through
adapter -> bridge -> kernel engine, and that the full audit_hash chain
(not just final output) reproduces identically across independent passes.
"""

import os
import tempfile
import uuid
import pytest

from replay_engine import (
    ReplayEngine,
    BinaryTelemetryLogWriter,
    FullPipelineReplaySummary,
)
from phoenix_a_execution_module import PhoenixAExecutionModule


@pytest.fixture
def small_dataset_file():
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, "replay_audit_test_stream.bin")

    packets = ReplayEngine.generate_synthetic_dataset(num_records=10, seed=777)
    BinaryTelemetryLogWriter.write_dataset_to_file(filepath, packets)

    yield filepath

    if os.path.exists(filepath):
        os.remove(filepath)
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)


@pytest.fixture
def larger_dataset_file():
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, "replay_audit_test_stream_large.bin")

    packets = ReplayEngine.generate_synthetic_dataset(num_records=30, seed=2024)
    BinaryTelemetryLogWriter.write_dataset_to_file(filepath, packets)

    yield filepath

    if os.path.exists(filepath):
        os.remove(filepath)
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)


def test_full_pipeline_replay_produces_summary(small_dataset_file):
    summary = ReplayEngine.execute_full_pipeline_replay(
        small_dataset_file, PhoenixAExecutionModule()
    )

    assert isinstance(summary, FullPipelineReplaySummary)
    assert summary.total_frames_processed == 10
    assert len(summary.audit_hashes) == 10
    assert len(summary.final_kernel_state_hash) == 32


def test_full_pipeline_replay_audit_hashes_are_well_formed(small_dataset_file):
    summary = ReplayEngine.execute_full_pipeline_replay(
        small_dataset_file, PhoenixAExecutionModule()
    )

    for h in summary.audit_hashes:
        assert isinstance(h, bytes)
        assert len(h) == 32


def test_full_pipeline_replay_audit_hashes_are_distinct_across_frames(small_dataset_file):
    summary = ReplayEngine.execute_full_pipeline_replay(
        small_dataset_file, PhoenixAExecutionModule()
    )

    assert len(set(summary.audit_hashes)) == len(summary.audit_hashes)


def test_causal_chain_determinism_true_for_identical_dataset(small_dataset_file):
    result = ReplayEngine.verify_causal_chain_determinism(
        small_dataset_file,
        module_factory=lambda: PhoenixAExecutionModule(),
    )
    assert result is True


def test_causal_chain_determinism_holds_for_larger_dataset(larger_dataset_file):
    result = ReplayEngine.verify_causal_chain_determinism(
        larger_dataset_file,
        module_factory=lambda: PhoenixAExecutionModule(),
    )
    assert result is True


def test_two_independent_replay_passes_produce_identical_audit_hashes(small_dataset_file):
    """
    generation_id is held fixed across both calls below, for the same
    reason verify_causal_chain_determinism does: two ordinary
    independently-constructed engines are, by design, two different
    kernel generations, so comparing audit hashes across them would be
    comparing two different lifetimes rather than proving determinism
    given the same one.
    """
    shared_generation_id = uuid.uuid4().bytes

    summary_1 = ReplayEngine.execute_full_pipeline_replay(
        small_dataset_file, PhoenixAExecutionModule(), generation_id=shared_generation_id
    )
    summary_2 = ReplayEngine.execute_full_pipeline_replay(
        small_dataset_file, PhoenixAExecutionModule(), generation_id=shared_generation_id
    )

    assert summary_1.total_frames_processed == summary_2.total_frames_processed
    assert summary_1.audit_hashes == summary_2.audit_hashes
    assert summary_1.final_kernel_state_hash == summary_2.final_kernel_state_hash


def test_different_datasets_produce_different_audit_chains():
    """
    Negative control: if two different datasets produced the same audit
    chain, the hash chain would be worthless as a verification tool.
    This confirms the audit chain is actually sensitive to input content.

    Note: final_kernel_state_hash is intentionally NOT checked here — it is
    a structural/positional fingerprint (sequence position, frame count,
    kernel state) rather than a content hash, so two equal-length runs
    ending in the same kernel state will always match there by design.
    Content sensitivity is the audit chain's job, verified via
    audit_hashes below.
    """
    temp_dir = tempfile.mkdtemp()
    path_a = os.path.join(temp_dir, "stream_a.bin")
    path_b = os.path.join(temp_dir, "stream_b.bin")

    try:
        packets_a = ReplayEngine.generate_synthetic_dataset(num_records=10, seed=111)
        packets_b = ReplayEngine.generate_synthetic_dataset(num_records=10, seed=222)

        BinaryTelemetryLogWriter.write_dataset_to_file(path_a, packets_a)
        BinaryTelemetryLogWriter.write_dataset_to_file(path_b, packets_b)

        summary_a = ReplayEngine.execute_full_pipeline_replay(path_a, PhoenixAExecutionModule())
        summary_b = ReplayEngine.execute_full_pipeline_replay(path_b, PhoenixAExecutionModule())

        assert summary_a.audit_hashes != summary_b.audit_hashes

    finally:
        for p in (path_a, path_b):
            if os.path.exists(p):
                os.remove(p)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


def test_bridge_level_replay_still_works_unchanged(small_dataset_file):
    summary, frames = ReplayEngine.execute_replay_pass(small_dataset_file)

    assert summary.total_frames == 10
    assert len(frames) == 10
    assert summary.first_hash != ""
    assert summary.last_hash != ""

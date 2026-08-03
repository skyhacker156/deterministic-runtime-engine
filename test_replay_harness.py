"""
test_replay_harness.py - Hardened Replay Harness Test Suite
"""

import os
import tempfile
import pytest

from replay_engine import ReplayEngine, BinaryTelemetryLogWriter, BinaryTelemetryLogReader


@pytest.fixture
def temp_dataset_file():
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, "test_telemetry_stream.bin")
    
    packets = ReplayEngine.generate_synthetic_dataset(num_records=150, seed=1337)
    BinaryTelemetryLogWriter.write_dataset_to_file(filepath, packets)
    
    yield filepath
    
    if os.path.exists(filepath):
        os.remove(filepath)
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)


def test_binary_log_serialization_roundtrip():
    """
    Verifies that packets written to binary log deserialize with identical values
    (tightened float value comparison).
    """
    packets = ReplayEngine.generate_synthetic_dataset(num_records=5, seed=42)
    
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        filepath = tmp.name

    try:
        BinaryTelemetryLogWriter.write_dataset_to_file(filepath, packets)
        read_packets = list(BinaryTelemetryLogReader.stream_dataset(filepath))

        assert len(read_packets) == len(packets)
        for original, restored in zip(packets, read_packets):
            assert original.batch_id == restored.batch_id
            assert original.timestamp == pytest.approx(restored.timestamp)
            
            # Tightened: Compare actual float reading arrays within precision threshold
            assert original.temperature_readings == pytest.approx(restored.temperature_readings, abs=1e-8)
            assert original.seismic_amplitude == pytest.approx(restored.seismic_amplitude, abs=1e-8)
            assert original.chemical_pH == pytest.approx(restored.chemical_pH, abs=1e-8)
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


def test_cross_pass_stream_hash_determinism(temp_dataset_file):
    summary_1, frames_1 = ReplayEngine.execute_replay_pass(temp_dataset_file)
    summary_2, frames_2 = ReplayEngine.execute_replay_pass(temp_dataset_file)

    assert summary_1.total_frames == 150
    assert summary_2.total_frames == 150

    assert summary_1.cumulative_stream_hash == summary_2.cumulative_stream_hash
    assert summary_1.first_hash == summary_2.first_hash
    assert summary_1.last_hash == summary_2.last_hash

    for f1, f2 in zip(frames_1, frames_2):
        assert f1.frame_id == f2.frame_id
        assert f1.provenance_hash == f2.provenance_hash
        assert f1.ph_slice == f2.ph_slice
        assert f1.seismic_slice == f2.seismic_slice
        assert f1.temp_slice == f2.temp_slice


def test_invalid_magic_header_rejection():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"BADHEADER12345")
        filepath = tmp.name

    try:
        with pytest.raises(ValueError, match="Invalid dataset magic header"):
            list(BinaryTelemetryLogReader.stream_dataset(filepath))
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
"""
test_pipeline_integration.py - End-to-End Surface-to-Bridge Integration Suite
"""

import pytest
from hypothesis import given, strategies as st, settings
from vent_adapter_contract import (
    VentAdapterContract, 
    RawVentTelemetryPacket, 
    SanitizedEngineBatch, 
    EXPECTED_TENSOR_DIM
)
from bridge_integrator_contract import BridgeIntegrator, IntegrityError, SensorStagnationFault


@st.composite
def valid_dynamic_packet(draw):
    batch_id = draw(st.text(min_size=1, max_size=10).map(lambda s: f"BATCH-{s}"))
    timestamp = draw(st.floats(min_value=1e9, max_value=2e9, allow_nan=False))
    
    base_temp = draw(st.floats(min_value=10.0, max_value=500.0, allow_nan=False))
    delta_temp = draw(st.floats(min_value=1.0, max_value=50.0, allow_nan=False))
    temps = [base_temp] * 5 + [base_temp + delta_temp] * 5

    base_seismic = draw(st.floats(min_value=0.1, max_value=50.0, allow_nan=False))
    delta_seismic = draw(st.floats(min_value=0.5, max_value=10.0, allow_nan=False))
    seismic = [base_seismic] * 5 + [base_seismic + delta_seismic] * 5

    base_ph = draw(st.floats(min_value=1.0, max_value=14.0, allow_nan=False))
    delta_ph = draw(st.floats(min_value=0.5, max_value=2.0, allow_nan=False))
    pH = [base_ph] * 5 + [base_ph + delta_ph] * 5
    
    return RawVentTelemetryPacket(
        batch_id=batch_id,
        timestamp=timestamp,
        temperature_readings=temps,
        seismic_amplitude=seismic,
        chemical_pH=pH
    )


@settings(max_examples=500)
@given(packet=valid_dynamic_packet())
def test_end_to_end_handshake_and_slice_preservation(packet):
    adapter = VentAdapterContract()
    batch, log_record = adapter.process_raw_packet(packet)
    
    assert log_record.qa_passed is True
    assert batch is not None
    
    frame = BridgeIntegrator.verify_and_transform(batch)
    
    total_elements = len(frame.ph_slice) + len(frame.seismic_slice) + len(frame.temp_slice)
    assert total_elements == EXPECTED_TENSOR_DIM
    
    assert len(frame.ph_slice) == 86
    assert len(frame.seismic_slice) == 85
    assert len(frame.temp_slice) == 85

    reconstructed = frame.ph_slice + frame.seismic_slice + frame.temp_slice
    assert reconstructed == batch.data_tensor


def test_tamper_detection_triggers_integrity_error():
    packet = RawVentTelemetryPacket(
        batch_id="TAMPER-TEST",
        timestamp=1700000000.0,
        temperature_readings=[100.0, 150.0] * 5,
        seismic_amplitude=[5.0, 10.0, 15.0] * 5,
        chemical_pH=[7.0, 8.5] * 5
    )
    
    adapter = VentAdapterContract()
    batch, _ = adapter.process_raw_packet(packet)
    
    tampered_tensor = list(batch.data_tensor)
    tampered_tensor[42] = tampered_tensor[42] + 0.0001
    
    tampered_batch = SanitizedEngineBatch(
        batch_id=batch.batch_id,
        timestamp=batch.timestamp,
        data_tensor=tuple(tampered_tensor),
        provenance_hash=batch.provenance_hash
    )
    
    with pytest.raises(IntegrityError, match="Provenance Hash Mismatch"):
        BridgeIntegrator.verify_and_transform(tampered_batch)


def test_flatline_signal_triggers_sensor_stagnation():
    flat_packet = RawVentTelemetryPacket(
        batch_id="STAGNANT-TEST",
        timestamp=1700000000.0,
        temperature_readings=[200.0] * 20,
        seismic_amplitude=[200.0] * 20,
        chemical_pH=[200.0] * 20
    )
    
    adapter = VentAdapterContract()
    batch, _ = adapter.process_raw_packet(flat_packet)
    
    with pytest.raises(SensorStagnationFault, match="Sensor Stagnation Detected"):
        BridgeIntegrator.verify_and_transform(batch)


def test_deterministic_replay_across_runs():
    packet = RawVentTelemetryPacket(
        batch_id="REPLAY-TEST-001",
        timestamp=1700000000.123456,
        temperature_readings=[150.0, 250.0, 350.0] * 10,
        seismic_amplitude=[1.2, 4.5, 9.8] * 10,
        chemical_pH=[6.8, 7.2, 7.5] * 10
    )

    adapter_1 = VentAdapterContract()
    batch_1, log_1 = adapter_1.process_raw_packet(packet)
    assert log_1.qa_passed is True
    frame_1 = BridgeIntegrator.verify_and_transform(batch_1)

    adapter_2 = VentAdapterContract()
    batch_2, log_2 = adapter_2.process_raw_packet(packet)
    assert log_2.qa_passed is True
    frame_2 = BridgeIntegrator.verify_and_transform(batch_2)

    assert frame_1.provenance_hash == frame_2.provenance_hash

    reconstructed_1 = frame_1.ph_slice + frame_1.seismic_slice + frame_1.temp_slice
    reconstructed_2 = frame_2.ph_slice + frame_2.seismic_slice + frame_2.temp_slice
    assert reconstructed_1 == batch_1.data_tensor
    assert reconstructed_2 == batch_2.data_tensor
    assert reconstructed_1 == reconstructed_2

    assert frame_1.ph_slice == frame_2.ph_slice
    assert frame_1.seismic_slice == frame_2.seismic_slice
    assert frame_1.temp_slice == frame_2.temp_slice
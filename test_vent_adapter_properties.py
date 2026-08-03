"""
test_vent_adapter_properties.py - Property-Based Suite for VentAdapter
Classification: Safe / Surface Layer Verification

Uses Hypothesis to fuzz RawVentTelemetryPacket across randomized channel lengths,
mismatched arrays, NaN densities, and floating-point boundaries.
"""

import math
from hypothesis import given, strategies as st, settings
import pytest
from vent_adapter_contract import (
    VentAdapterContract,
    RawVentTelemetryPacket,
    StratifiedTensorPacker,
    EXPECTED_TENSOR_DIM,
)


# =====================================================================
# 1. Hypothesis Strategy Generators
# =====================================================================
finite_float_strategy = st.floats(
    min_value=-1e5, 
    max_value=1e5, 
    allow_nan=False, 
    allow_infinity=False
)

special_float_strategy = st.sampled_from([
    float('nan'), 
    float('inf'), 
    float('-inf'), 
    0.0, 
    -0.0
])

float_strategy = st.one_of(finite_float_strategy, special_float_strategy)


@st.composite
def random_vent_packet(draw):
    """Generates random telemetry packets with wildly varying channel lengths and values."""
    batch_id = draw(st.text(min_size=1, max_size=10).map(lambda s: f"BATCH-{s}"))
    timestamp = draw(st.floats(min_value=1e9, max_value=2e9, allow_nan=False))
    
    # Generate mismatched lengths across channels (0 to 300 elements)
    temps = draw(st.lists(float_strategy, min_size=0, max_size=300))
    seismic = draw(st.lists(float_strategy, min_size=0, max_size=300))
    pH = draw(st.lists(float_strategy, min_size=0, max_size=300))
    
    return RawVentTelemetryPacket(
        batch_id=batch_id,
        timestamp=timestamp,
        temperature_readings=temps,
        seismic_amplitude=seismic,
        chemical_pH=pH
    )


# Strategy specifically for populated non-zero channels (to test representation equity)
@st.composite
def populated_vent_packet(draw):
    batch_id = draw(st.text(min_size=1, max_size=10).map(lambda s: f"BATCH-{s}"))
    timestamp = draw(st.floats(min_value=1e9, max_value=2e9, allow_nan=False))
    
    # Guarantee at least 1 valid finite number per channel
    temps = draw(st.lists(st.floats(min_value=10.0, max_value=500.0, allow_nan=False), min_size=5, max_size=100))
    seismic = draw(st.lists(st.floats(min_value=0.1, max_value=10.0, allow_nan=False), min_size=5, max_size=100))
    pH = draw(st.lists(st.floats(min_value=1.0, max_value=14.0, allow_nan=False), min_size=5, max_size=100))
    
    return RawVentTelemetryPacket(
        batch_id=batch_id,
        timestamp=timestamp,
        temperature_readings=temps,
        seismic_amplitude=seismic,
        chemical_pH=pH
    )


# =====================================================================
# 2. Fuzzing Property Tests
# =====================================================================

@settings(max_examples=1000)
@given(packet=random_vent_packet())
def test_property_shape_and_bounds_invariants(packet):
    """Property 1 & 2: Tensor shape is strictly 256 and all elements are bounded in [0.0, 1.0]."""
    adapter = VentAdapterContract()
    batch, log = adapter.process_raw_packet(packet)
    
    if batch is not None:
        assert len(batch.data_tensor) == EXPECTED_TENSOR_DIM
        for idx, val in enumerate(batch.data_tensor):
            assert 0.0 <= val <= 1.0
            assert math.isfinite(val)


@settings(max_examples=500)
@given(packet=random_vent_packet())
def test_property_determinism(packet):
    """Property 3: Determinism Invariant. Same input yields identical tensor bytes & hashes."""
    adapter = VentAdapterContract()
    batch1, _ = adapter.process_raw_packet(packet)
    batch2, _ = adapter.process_raw_packet(packet)
    
    if batch1 is not None and batch2 is not None:
        assert batch1.data_tensor == batch2.data_tensor
        assert batch1.provenance_hash == batch2.provenance_hash


@settings(max_examples=500)
@given(packet=populated_vent_packet())
def test_property_channel_equity(packet):
    """
    Property 4: Channel Equity Invariant.
    Verifies that when all input streams contain valid data, stratified packing 
    allocates non-zero representation across all designated tensor slices.
    """
    adapter = VentAdapterContract()
    batch, _ = adapter.process_raw_packet(packet)
    
    assert batch is not None, "Valid populated packet failed processing!"
    
    # 256 / 3 channels = 85 slots per channel
    quota = EXPECTED_TENSOR_DIM // 3
    
    # Slice tensor by channel quotas (sorted order: pH -> seismic -> temperature)
    ph_slice = batch.data_tensor[0 : quota]
    seismic_slice = batch.data_tensor[quota : 2 * quota]
    temp_slice = batch.data_tensor[2 * quota : 3 * quota]
    
    assert any(x > 0.0 for x in ph_slice), "pH channel was truncated or unrepresented!"
    assert any(x > 0.0 for x in seismic_slice), "Seismic channel was truncated or unrepresented!"
    assert any(x > 0.0 for x in temp_slice), "Temperature channel was truncated or unrepresented!"


def test_zero_division_guard_clause():
    """Property 5: Edge Case Protection against >256 channels."""
    too_many_channels = {f"ch_{i}": [1.0, 2.0] for i in range(300)}
    with pytest.raises(ValueError, match=r"Number of channels.*exceeds target tensor dimension"):
        StratifiedTensorPacker.pack_channels_stratified(too_many_channels, target_dim=256)
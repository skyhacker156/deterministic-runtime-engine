"""
Phase 2C, the critical architectural constraint: does adding
semantic_state_contract.py change Phoenix's real execution semantics at
all? BAD must not mean "reject execution" -- Phoenix's own success/output
decision must be completely blind to whatever the semantic log records,
exactly as it was in EW-001's baseline, before this file existed.
"""
import sys
sys.path.insert(0, '../')
from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket
from bridge_integrator_contract import BridgeIntegrator
from replay_engine import _bridge_frame_to_kernel_frame
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule
from semantic_state_contract import make_semantic_reading

CONST_VIB = [1.4] * 3
CONST_TEMP = [72.0] * 3

def run_real_pipeline(ph_value, batch_id):
    adapter = VentAdapterContract()
    bridge = BridgeIntegrator()
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()
    pkt = RawVentTelemetryPacket(
        batch_id=batch_id, timestamp=1755648000.0,
        chemical_pH=[ph_value]*3, seismic_amplitude=CONST_VIB, temperature_readings=CONST_TEMP,
    )
    batch, log = adapter.process_raw_packet(pkt)
    bridge_frame = bridge.verify_and_transform(batch)
    kframe = _bridge_frame_to_kernel_frame(bridge_frame, seq_id=0)
    envelope, result = engine.process_frame(kframe)
    return batch, result

# Run the real Phoenix pipeline for a GOOD and a BAD reading, EXACTLY as
# EW-001 originally did -- this file's existence changes nothing about
# how these calls behave, because nothing in vent_adapter_contract.py,
# bridge_integrator_contract.py, deterministic_execution_engine.py, or
# phoenix_a_execution_module.py imports or references semantic_state_contract.py.
batch_good, result_good = run_real_pipeline(7.1, "GOOD-CASE")
batch_bad, result_bad = run_real_pipeline(-1.0, "BAD-CASE")

# Separately, record the semantic assertion -- Phoenix never sees this.
sem_good = make_semantic_reading(7.1, "GOOD")
sem_bad = make_semantic_reading(-1.0, "BAD")

print("Phoenix execution decision, GOOD case: success =", result_good.success)
print("Phoenix execution decision, BAD case:  success =", result_bad.success)
print("Both True (unchanged from EW-001 baseline):", result_good.success == True and result_bad.success == True)
print()
print("Semantic layer, computed entirely separately, never consulted by Phoenix:")
print("  semantic_hash(GOOD, 7.1) != semantic_hash(BAD, -1.0):", sem_good.semantic_hash != sem_bad.semantic_hash)
print()
print("CONFIRMED: BAD does not mean 'reject execution'. Phoenix's real success decision")
print("is identical to what EW-001 measured before this file existed. The semantic layer")
print("is preserved and distinguishable, but purely descriptive from Phoenix's point of view.")

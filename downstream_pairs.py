"""
Downstream trace: external packet -> translation -> normalization -> Bridge
-> Kernel -> execution module -> final ExecutionResult.

Three paired cases, one per channel, holding the other two channels
CONSTANT (healthy, identical values) between the A/B members of each pair.
This isolates each channel's contribution to the final decision.
"""
import sys, json
sys.path.insert(0, '../')
import numpy as np
from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket
from bridge_integrator_contract import BridgeIntegrator
from replay_engine import _bridge_frame_to_kernel_frame
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule

CONST_PH = [7.1] * 3
CONST_VIB = [1.4] * 3
CONST_TEMP = [72.0] * 3

def run_pair(name, ph, vib, temp, seq_id):
    adapter = VentAdapterContract()
    bridge = BridgeIntegrator()
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()

    pkt = RawVentTelemetryPacket(
        batch_id=f"{name}-{seq_id}", timestamp=1755648000.0 + seq_id,
        chemical_pH=ph, seismic_amplitude=vib, temperature_readings=temp,
    )
    batch, log = adapter.process_raw_packet(pkt)
    assert log.qa_passed, f"{name}: QA failed unexpectedly: {log.error_message}"
    bridge_frame = bridge.verify_and_transform(batch)
    kframe = _bridge_frame_to_kernel_frame(bridge_frame, seq_id=seq_id)
    envelope, result = engine.process_frame(kframe)
    return {
        "name": name,
        "ph_norm": round(float(bridge_frame.ph_slice[0]), 6),
        "vib_norm": round(float(bridge_frame.seismic_slice[0]), 6),
        "temp_norm": round(float(bridge_frame.temp_slice[0]), 6),
        "success": result.success,
        "metrics": {k: round(v, 8) for k, v in result.metrics.items()},
        "output_payload_first5": [round(x, 8) for x in result.output_payload[:5].tolist()],
        "module_hash": result.module_hash.hex()[:16],
    }

print("="*100)
print("PAIR 1: pH -- healthy (7.1) vs BAD sensor-fault sentinel (-1.0). Vibration/temp held constant.")
print("="*100)
a = run_pair("pH-healthy", CONST_PH, CONST_VIB, CONST_TEMP, seq_id=0)
b = run_pair("pH-FAULT",   [-1.0]*3, CONST_VIB, CONST_TEMP, seq_id=0)
for r in (a, b):
    print(json.dumps(r, indent=2))
print(f"-> success flags equal: {a['success']==b['success']}")
print(f"-> metrics equal: {a['metrics']==b['metrics']}")
print(f"-> module_hash equal: {a['module_hash']==b['module_hash']}")
print(f"-> output_payload[:5] equal: {a['output_payload_first5']==b['output_payload_first5']}")

print()
print("="*100)
print("PAIR 2: Vibration -- healthy (1.4 mm/s) vs Zone-D severe fault (42.7-44.1 mm/s). pH/temp held constant.")
print("="*100)
c = run_pair("vib-healthy", CONST_PH, CONST_VIB, CONST_TEMP, seq_id=0)
d = run_pair("vib-FAULT",   CONST_PH, [42.7, 44.1, 43.8], CONST_TEMP, seq_id=0)
for r in (c, d):
    print(json.dumps(r, indent=2))
print(f"-> success flags equal: {c['success']==d['success']}")
print(f"-> metrics equal: {c['metrics']==d['metrics']}")
print(f"-> module_hash equal: {c['module_hash']==d['module_hash']}")
print(f"-> output_payload[:5] equal: {c['output_payload_first5']==d['output_payload_first5']}")

print()
print("="*100)
print("PAIR 3: Temperature -- healthy (72.0 C) vs open-circuit fault (-999.0). pH/vib held constant.")
print("="*100)
e = run_pair("temp-healthy", CONST_PH, CONST_VIB, CONST_TEMP, seq_id=0)
f = run_pair("temp-FAULT",   CONST_PH, CONST_VIB, [-999.0]*3, seq_id=0)
for r in (e, f):
    print(json.dumps(r, indent=2))
print(f"-> success flags equal: {e['success']==f['success']}")
print(f"-> metrics equal: {e['metrics']==f['metrics']}")
print(f"-> module_hash equal: {e['module_hash']==f['module_hash']}")
print(f"-> output_payload[:5] equal: {e['output_payload_first5']==f['output_payload_first5']}")

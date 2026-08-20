"""
Translation layer: EXTERNAL_WORKLOAD_SPEC.md packets -> Phoenix A's real,
unmodified RawVentTelemetryPacket, then through the real, unmodified
VentAdapterContract -> BridgeIntegrator -> replay_engine pipeline.

Mapping decisions, stated explicitly (this is where external convention
meets Phoenix's actual required shape):
  - ph            -> chemical_pH           (direct)
  - vibration_mm_s -> seismic_amplitude    (direct; different physical
    quantity and unit than Phoenix's own name implies, but it's the only
    slot of the three that isn't pH or temperature)
  - temperature_c -> temperature_readings  (direct)
  - epoch_ms / 1000.0 -> timestamp (Phoenix's field is an undocumented-unit
    float; converting ms->s is an assumption, not a confirmed contract)
  - station_id + epoch_ms -> batch_id (Phoenix has no station concept)
  - quality flags -> DROPPED. RawVentTelemetryPacket has no field for them.
"""
import sys, json
sys.path.insert(0, '../')
from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket
from bridge_integrator_contract import BridgeIntegrator
from replay_engine import _bridge_frame_to_kernel_frame

with open("workload_packets.json") as f:
    ext_packets = json.load(f)

adapter = VentAdapterContract()
bridge = BridgeIntegrator()

results = []
for i, ep in enumerate(ext_packets):
    batch_id = f"{ep['station_id']}-{ep['epoch_ms']}"
    pkt = RawVentTelemetryPacket(
        batch_id=batch_id,
        timestamp=ep["epoch_ms"] / 1000.0,
        chemical_pH=ep["readings"]["ph"],
        seismic_amplitude=ep["readings"]["vibration_mm_s"],
        temperature_readings=ep["readings"]["temperature_c"],
    )
    batch, log = adapter.process_raw_packet(pkt)
    row = {
        "idx": i, "batch_id": batch_id,
        "quality": ep["quality"],
        "qa_passed": log.qa_passed,
        "error": log.error_message,
        "data_points": log.data_points_processed,
    }
    if batch is not None:
        try:
            bridge_frame = bridge.verify_and_transform(batch)
            kframe = _bridge_frame_to_kernel_frame(bridge_frame, seq_id=i)
            row["bridge_ok"] = True
            row["kernel_ok"] = True
            row["ph_slice_sample"] = round(float(bridge_frame.ph_slice[0]), 6)
            row["seismic_slice_sample"] = round(float(bridge_frame.seismic_slice[0]), 6)
            row["temp_slice_sample"] = round(float(bridge_frame.temp_slice[0]), 6)
        except Exception as e:
            row["bridge_ok"] = False
            row["bridge_error"] = f"{type(e).__name__}: {e}"
    results.append(row)

with open("results.json", "w") as f:
    json.dump(results, f, indent=2)

# --- Summary ---
n = len(results)
qa_pass = sum(1 for r in results if r["qa_passed"])
bridge_pass = sum(1 for r in results if r.get("bridge_ok"))
print(f"Total packets: {n}")
print(f"QA passed:     {qa_pass}/{n}")
print(f"Bridge passed: {bridge_pass}/{n}")
print()
print("=== Edge-case packets (indices 20-25) ===")
for r in results[20:]:
    print(f"[{r['idx']}] batch={r['batch_id']!r} quality={r['quality']} qa_passed={r['qa_passed']} "
          f"bridge_ok={r.get('bridge_ok')} ph_norm={r.get('ph_slice_sample')} "
          f"seismic_norm={r.get('seismic_slice_sample')} temp_norm={r.get('temp_slice_sample')}")

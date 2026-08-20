"""
Generator for the External Workload Spec (v1). Produces packets conforming
ONLY to EXTERNAL_WORKLOAD_SPEC.md's own conventions -- no knowledge of
Phoenix A's schema is used here.
"""
import json
import random

random.seed(20260820)

def make_packet(station_id, epoch_ms, ph_readings, vib_readings, temp_readings,
                 ph_q="GOOD", vib_q="GOOD", temp_q="GOOD"):
    return {
        "station_id": station_id,
        "epoch_ms": epoch_ms,
        "readings": {
            "ph": ph_readings,
            "vibration_mm_s": vib_readings,
            "temperature_c": temp_readings,
        },
        "quality": {
            "ph": ph_q,
            "vibration_mm_s": vib_q,
            "temperature_c": temp_q,
        },
    }

packets = []
base_epoch = 1_755_648_000_000  # a real ms-epoch timestamp

# --- Normal operating packets (healthy, in-band readings) ---
for i in range(20):
    packets.append(make_packet(
        "STATION-07", base_epoch + i * 5000,
        ph_readings=[round(random.uniform(6.8, 7.4), 2) for _ in range(random.randint(1, 4))],
        vib_readings=[round(random.uniform(0.5, 2.0), 3) for _ in range(random.randint(1, 3))],
        temp_readings=[round(random.uniform(60.0, 85.0), 2) for _ in range(random.randint(1, 5))],
    ))

# --- Edge case 1: Zone D vibration failure, far outside anything Phoenix's own fixtures used ---
packets.append(make_packet(
    "STATION-07", base_epoch + 100_000,
    ph_readings=[7.1], vib_readings=[42.7, 44.1, 43.8], temp_readings=[71.2],
))

# --- Edge case 2: pH fault sentinels (valid readings under this spec) ---
packets.append(make_packet(
    "STATION-07", base_epoch + 105_000,
    ph_readings=[-1.0], vib_readings=[1.2], temp_readings=[72.0],
    ph_q="BAD",
))
packets.append(make_packet(
    "STATION-07", base_epoch + 110_000,
    ph_readings=[15.0], vib_readings=[1.1], temp_readings=[71.8],
    ph_q="BAD",
))

# --- Edge case 3: mixed per-channel quality within one packet ---
packets.append(make_packet(
    "STATION-07", base_epoch + 115_000,
    ph_readings=[7.05], vib_readings=[1.4], temp_readings=[73.1],
    vib_q="UNCERTAIN",
))

# --- Edge case 4: mismatched reading-array lengths across channels ---
packets.append(make_packet(
    "STATION-07", base_epoch + 120_000,
    ph_readings=[7.0, 7.02, 6.99], vib_readings=[1.3], temp_readings=[70.1, 70.3, 70.2, 70.0, 69.9],
))

# --- Edge case 5: temperature open-circuit fault sentinel ---
packets.append(make_packet(
    "STATION-07", base_epoch + 125_000,
    ph_readings=[7.0], vib_readings=[1.2], temp_readings=[-999.0],
    temp_q="BAD",
))

# --- Edge case 6: real ms-epoch timestamps (already used throughout) ---

with open("workload_packets.json", "w") as f:
    json.dump(packets, f, indent=2)

print(f"Generated {len(packets)} packets -> workload_packets.json")
print(f"  {20} normal, {6} edge-case packets from the spec's own stated conventions")

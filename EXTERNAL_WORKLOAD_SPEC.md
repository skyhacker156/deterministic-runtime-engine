# External Workload Spec — Industrial Process Telemetry (v1)

Written independently of Phoenix A's own ingestion schema. This document is
authored first, from real external process-monitoring conventions, before
any Phoenix A source file is re-consulted for this campaign. Any mapping
onto Phoenix A's actual input shape happens in a separate translation layer
afterward — this spec does not know Phoenix A exists.

## Domain

A three-sensor industrial monitoring station: pH (chemical process),
vibration (rotating equipment), temperature (RTD probe). Loosely grounded
in real, independently-documented conventions:

- **pH sensor**: continuous process pH, reported to 0.01 resolution,
  physically valid range 0.00–14.00. Analog-loop sensors of this kind
  commonly report out-of-range or fault conditions via out-of-band sentinel
  values rather than clipping silently (a NAMUR NE43-style convention: a
  4–20 mA loop reports under-range/over-range/fault via specific current
  values outside the normal 4–20 mA band, e.g. 3.6 mA or 21.0 mA, rather
  than saturating at the nominal endpoints). This spec models that as
  explicit sentinel readings: `-1.0` (under-range fault) and `15.0`
  (over-range fault), distinct from any value a healthy sensor would ever
  report.

- **Vibration sensor**: RMS velocity in mm/s, per ISO 10816-style severity
  zones for a mid-size rotating machine: Zone A (good) 0.0–2.3, Zone B
  (acceptable) 2.3–4.5, Zone C (unsatisfactory) 4.5–7.1, Zone D
  (unacceptable/damage risk) 7.1–45.0. Unlike a bounded percentage or
  ratio, this is an open-ended physical unit — there is no fixed sensor
  ceiling analogous to pH's 0–14 range; a genuinely failing machine can
  report arbitrarily high values before failure.

- **Temperature sensor**: RTD probe (e.g. Pt100-style), reporting degrees
  Celsius across an industrial process range of -50.0 to 350.0, with a
  documented open-circuit fault convention: an RTD that has failed open
  reports a specific out-of-band value (commonly a very large negative or
  positive number well outside the physical process range) rather than a
  null.

## Packet shape

Each telemetry packet:

```
{
  "station_id": string,
  "epoch_ms": integer (Unix epoch milliseconds, NOT seconds),
  "readings": {
    "ph": [float, ...] (variable-length array, 1 to N readings per packet — a real DCS commonly buffers multiple scan-cycle samples per transmitted packet, not always one-per-channel),
    "vibration_mm_s": [float, ...],
    "temperature_c": [float, ...]
  },
  "quality": {
    "ph": "GOOD" | "UNCERTAIN" | "BAD",
    "vibration_mm_s": "GOOD" | "UNCERTAIN" | "BAD",
    "temperature_c": "GOOD" | "UNCERTAIN" | "BAD"
  }
}
```

Notes, stated explicitly because they are real conventions that don't
resemble a schema designed around a fixed 256-element tensor:

- Reading arrays are **variable length**, not a fixed count — a real
  scan-cycle buffer varies with sampling rate and transmission cadence.
- Channel **quality flags** are a first-class part of the payload, separate
  from the numeric values themselves — a `BAD`-quality reading is still
  transmitted (not omitted), because downstream systems may want the raw
  value even when it shouldn't be trusted.
- `epoch_ms` is milliseconds, not seconds or a float — a common source of
  off-by-1000 errors when integrating with a system that assumes seconds.
- Channel identity is carried by **JSON object key** (`"ph"`,
  `"vibration_mm_s"`, `"temperature_c"`), not by array position — no
  ordering convention is implied or required by this spec.

## Adversarial-by-nature edge cases this spec's own conventions produce

Not injected as deliberate attacks — these are ordinary, expected
occurrences under this spec's own stated conventions, the kind a real
external system would produce without any intent to test anything:

1. A packet where `vibration_mm_s` legitimately exceeds any range Phoenix
   A's own test fixtures ever used (Zone D failure, e.g. 40+ mm/s).
2. A packet using the pH fault sentinels (`-1.0`, `15.0`) — valid,
   expected readings under this spec, not malformed input.
3. A packet where one channel's `quality` is `"BAD"` while the other two
   are `"GOOD"` — quality is per-channel, no whole-packet accept/reject
   convention exists in this spec.
4. A packet with different reading-array lengths across the three channels
   in the same packet (e.g. 3 pH readings, 1 vibration reading, 5
   temperature readings) — this spec's scan-cycle model allows independent
   per-channel buffering.
5. A packet using a temperature open-circuit fault value (e.g. -999.0),
   physically outside the -50/350 process range but a valid *reading* under
   this spec's own fault-reporting convention.
6. `epoch_ms` values spanning real wall-clock time at millisecond
   resolution, not the small integer/float timestamps Phoenix A's own test
   fixtures typically use.

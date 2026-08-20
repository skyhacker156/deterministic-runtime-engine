# Phoenix A External Generalization Experiment — v1

**Status:** frozen baseline. This is the first artifact in this project that
is not Phoenix grading itself — every claim below traces to an external
spec authored independently of Phoenix A's own schema and test fixtures,
and to real execution against the actual, unmodified pipeline.

**Related artifacts:** `EXTERNAL_WORKLOAD_SPEC.md` (the independent spec),
`generate_workload.py` / `workload_packets.json` (the 26-packet dataset),
`run_external_workload.py` / `results.json` (the full-workload ingestion
run), `downstream_pairs.py` (the three controlled paired-case downstream
trace). `EW-001` in `VERIFICATION_COVERAGE_MATRIX.md` and its full narrative
in `ADVERSARIAL_METHODOLOGY.md` are the canonical record this document
summarizes — this report is the standalone, self-contained version.

---

## 1. Independently specified workload

`EXTERNAL_WORKLOAD_SPEC.md` was authored first, before any Phoenix A source
file was re-consulted for this campaign, grounded in real,
independently-documented industrial process-monitoring conventions:

- **pH sensor** — NAMUR NE43-style analog-loop fault signaling: healthy
  readings in 0.00–14.00, out-of-range faults reported as explicit
  sentinel values (-1.0 under-range, 15.0 over-range) rather than clipped
  silently.
- **Vibration sensor** — ISO 10816-style severity zones for a mid-size
  rotating machine: Zone A/B (0.0–4.5 mm/s, healthy) through Zone D
  (7.1–45.0 mm/s, damage risk), an open-ended physical unit unlike pH's
  fixed range.
- **Temperature sensor (RTD)** — process range -50.0 to 350.0°C, with an
  open-circuit fault convention reporting a large out-of-band sentinel
  (-999.0) rather than a null.

The packet shape itself embodies conventions absent from Phoenix A's own
schema: variable-length per-channel reading arrays (a real scan-cycle
buffer varies with sampling rate), first-class per-channel quality flags
(`GOOD`/`UNCERTAIN`/`BAD`, transmitted alongside the value rather than
suppressing it), millisecond-epoch timestamps, and channel identity carried
by JSON key rather than array position.

A 26-packet synthetic dataset was generated from this spec alone: 20
normal-operation packets plus 6 edge cases that the spec's own stated
conventions produce as a matter of course — not injected as deliberate
attacks. `random.seed(20260820)` for reproducibility.

## 2. Translation layer

Built only after the spec and dataset existed, mapping the external shape
onto Phoenix A's real, unmodified `RawVentTelemetryPacket`:

| External field | Phoenix field | Note |
|---|---|---|
| `readings.ph` | `chemical_pH` | direct |
| `readings.vibration_mm_s` | `seismic_amplitude` | direct; different physical quantity/unit than Phoenix's own name implies |
| `readings.temperature_c` | `temperature_readings` | direct |
| `epoch_ms / 1000.0` | `timestamp` | ms→s conversion is an assumption, not a confirmed contract — Phoenix's field has no documented unit |
| `station_id + epoch_ms` | `batch_id` | Phoenix has no station concept |
| `quality.*` | *(nowhere)* | `RawVentTelemetryPacket` has no field for this at all |

## 3. Predictions made before execution

Stated from reading Phoenix A's real source, before running any data
through it, so the run could confirm or disconfirm them rather than being
interpreted after the fact:

1. Quality flags have no destination in Phoenix's schema.
2. `pack_channels_stratified` only rejects on channel count (`==0` or
   `>256`), never on value — nothing in this workload should fail QA.
3. The normalization formula's hardcoded `-0.01 * (raw_val - 200.0)`
   center has no relation to any channel's real physical range — extreme
   values should saturate the sigmoid, collapsing distinctions.
4. Finite fault sentinels pass through unaltered (only NaN/Inf are
   coerced to 0.0).

## 4. Observed results

**Ingestion, all 26 packets:** 26/26 passed QA and Bridge integrity.
Nothing in this workload — including every fault sentinel, the Zone-D
vibration failure, and every `BAD`-quality reading — was ever rejected.

**Normalized values, edge cases (illustrative selection):**

| Reading | Real-world meaning | Normalized value |
|---|---|---|
| pH 7.1 | healthy | 0.126861 |
| pH -1.0 | under-range fault | 0.118157 |
| pH 15.0 | over-range fault | 0.135873 |
| Vibration 1.4 mm/s | healthy | 0.120681 |
| Vibration 42–44 mm/s | Zone D failure | 0.171789 |
| Temperature 72.0°C | healthy | 0.217550 |
| Temperature -999.0°C | open-circuit fault | 0.000006 |

**Downstream trace, three controlled paired cases** (healthy vs.
externally-flagged-`BAD`, one pair per channel, other two channels held
constant), through the real `DeterministicExecutionEngine`/
`PhoenixAExecutionModule` to a real `ExecutionResult`:

| Channel | `success` (both members) | `signal_energy` Δ | `vector_variance` Δ | `output_payload[0]` Δ |
|---|---|---|---|---|
| pH | True / True | -0.006 (smallest) | +0.0005 (smallest) | -0.010 (smallest) |
| Vibration | True / True | +0.024 | -0.0015 | -0.015 |
| Temperature | True / True | -0.024 | +0.0132 (4.5×, largest) | +0.104 (largest) |

No pair was ever bit-identical between its healthy and faulted member —
`module_hash` differed in all three.

## 5. EW-001

**Phoenix A's downstream decision neither fully preserves nor fully
collapses the external GOOD/BAD distinction.** The binary `success`
decision is blind to all three fault conditions, uniformly, on every
channel. The continuous layer retains a real, hash-visible signal
everywhere, but its magnitude is disproportionate to real-world
severity — an artifact of where each channel's fault sentinel happens to
sit relative to one hardcoded, channel-agnostic normalization constant,
not of any designed relationship to real-world severity. pH, whose entire
physical range plus both fault sentinels sit closest to that constant,
shows the smallest disturbance of the three — despite representing an
equally real sensor failure as the other two channels.

## 6. Downstream consequence

Traced explicitly, per the standing instruction not to fix anything before
this question was answered: does any consequential decision path consume
`signal_energy`, `vector_variance`, or `output_payload`?

Every real consumer of `ExecutionResult` in the codebase was checked.
`ExecutionAuditRecord.from_execution()` pulls only `success`/`output_hash`/
`error_message` — the hash is used for audit-chain tamper-evidence, never
compared against a threshold. `execution_policy.py` and
`execution_authorizer.py` — the actual authorization/quota decision
layer — have zero references to any of these fields; authorization is
keyed purely on invocation counts. `phoenix_a_risk_governor.py` is
confirmed, by import graph, to be a structurally separate subsystem
(imports only from `phoenix_a_core.py`), with no import relationship to
this pipeline at all.

**Outcome A: no consequential consumer exists.** `EW-001` is a
semantic-fidelity limitation at the ingestion/domain boundary, not a
decision-path issue. This is a real, if less dramatic, result — Phoenix A
can faithfully execute a numerically transformed representation of a
sensor reading while being architecturally unaware, at every layer traced,
of the real-world distinction between a healthy and a failed sensor that
produced it. Nothing currently acts on that blindness, but nothing
currently corrects it either.

## 7. What Phoenix A preserved

- Deterministic, hash-chained execution of whatever numeric values it was
  given, regardless of their real-world provenance or plausibility.
- Structural stability under a workload it was never designed around —
  no crash, no exception, no silent data corruption at the tensor level;
  every packet produced a well-formed, internally consistent result.
- A genuine (if disproportionate) numeric distinction between healthy and
  faulted readings on every channel — not a total information loss.

## 8. What Phoenix A did not preserve

- The external system's own quality/trust assertion — discarded entirely
  at the translation boundary, before Phoenix A's own code ever runs,
  because no field exists to carry it.
- A real-world-calibrated relationship between fault severity and Phoenix's
  internal numeric response — the response magnitude is governed by
  normalization geometry, not domain meaning.
- Any decision-level acknowledgment that a reading might be untrustworthy —
  the binary success/fail layer is uniformly blind to this, on every
  channel tested.

## 9. Unresolved architectural questions

Stated as open questions this experiment raises, not as a chosen design —
consistent with the standing instruction that the evidence establishes
what's true, not which correction is right:

- Should Phoenix A's ingestion contract carry an explicit quality/trust
  state at all, or is that responsibility intentionally left to a layer
  outside this system?
- Should channel normalization be channel-specific (aware of each
  channel's real physical range), or is a single generic transform an
  acceptable, deliberate simplification?
- If quality state were added, should it participate in the deterministic
  hash chain (making trust part of what's replayed and verified), or
  remain metadata alongside it?
- Is "the binary decision is blind to fault conditions" itself a problem,
  or is Phoenix A correctly scoped as a pure computation/verification
  layer that assumes upstream validation has already happened?

None of these questions is answered by this experiment. It establishes
that they are real, live questions with a concrete evidentiary basis — not
before-the-fact groundwork for the answer.

## 10. Explicitly out of scope for this report

No fix was designed, proposed, or drafted. No architecture change was
made. Candidate corrections (explicit quality-state propagation,
channel-specific normalization, physical-range validation, fault-state
invariants, domain-module responsibility for semantic validity) were named
as possibilities in the underlying `EW-001` record but not evaluated
against each other here — that comparison, if undertaken, is Phase 2: an
experimental comparison of candidate architectures (baseline `external
semantics → Phoenix numeric tensor` vs. a candidate `external semantics →
value + quality state → Phoenix`), asking whether a candidate can preserve
both computational determinism and semantic fidelity simultaneously. Not
started here.

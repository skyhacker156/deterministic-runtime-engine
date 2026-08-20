# Phoenix A External Generalization Experiment — v2

**Status:** frozen baseline, Phase 2 complete. Supersedes `v1` by
incorporating Phases 2A–2C without removing anything `v1` established —
`v1`'s sections 1–4 (spec, translation layer, predictions, observed
results) are unchanged and not repeated in full here; see
`PHOENIX_EXTERNAL_GENERALIZATION_v1.md` for that detail. This document adds
what came after `v1`'s freeze: the downstream trace, the information-
preservation experiment, the three-architecture comparison, and the first
real code addition this campaign has made.

**Related artifacts:** `EXTERNAL_WORKLOAD_SPEC.md`, `generate_workload.py`
/ `workload_packets.json`, `run_external_workload.py` / `results.json`,
`downstream_pairs.py` (all `v1`); `phase2a_information_preservation.py`,
`phase2b_architectures.py`, `phase2c_execution_semantics_unchanged.py`
(Phase 2); `semantic_state_contract.py` / `test_semantic_state_contract.py`
(the real code addition). `EW-001` and `EW-003` in
`VERIFICATION_COVERAGE_MATRIX.md`, full narratives in
`ADVERSARIAL_METHODOLOGY.md`.

---

## EW-001 (carried forward from v1, summarized)

An independently-authored external telemetry spec, grounded in real
industrial process-monitoring conventions, was translated onto Phoenix A's
real ingestion contract. All 26 synthetic packets passed QA and Bridge
integrity. Binary `success` was uniformly `True` regardless of fault
condition, on all three channels. Continuous metrics differed in every
paired case but by magnitudes disproportionate to real-world severity —
pH's fault (equally real as the other two) produced the smallest
disturbance of the three, an artifact of one hardcoded, channel-agnostic
normalization constant. Downstream consequence traced and resolved:
nothing in `execution_policy.py`, `execution_authorizer.py`, or the audit
chain consumes these metrics for any decision; `phoenix_a_risk_governor.py`
is confirmed structurally separate by import graph. **EW-001 is a
semantic-fidelity limitation at the ingestion/domain boundary, not a
decision-path issue.**

---

## Phase 2A — Information-preservation experiment

**Question:** what information must cross the ingestion boundary for
Phoenix A to preserve the semantics an external system actually provides?
Not whether a candidate architecture is "better" — first, whether the
distinction can be represented at all.

**The sharp test:** two readings with the *identical* numeric value (7.1),
differing only in externally-asserted quality (GOOD vs. BAD).

| Question | Baseline (real, unmodified Phoenix A) | Candidate A (standalone harness) |
|---|---|---|
| Can downstream reconstruct which was BAD from Phoenix's own artifacts alone? | No — a shift exists but isn't marked as fault | Yes — quality is its own explicit field |
| Included in provenance? | No — `compute_canonical_hash` only ever consumes `batch_id`/`timestamp`/tensor | Yes, in a separate combined hash |
| Does changing *only* quality produce a different Phoenix state? | **No** — `provenance_hash`, `kernel_provenance_hash`, `output_payload` all identical | **Yes** — combined hash differs, real Phoenix hash stays identical |
| Can the system distinguish "value changed" from "trust changed"? | No — trust-only change is invisible; only value-change produces any signal | Yes — the two are hashed from independent inputs |

**Result:** baseline Phoenix A cannot represent, propagate, or distinguish
an external quality signal from ordinary numeric fluctuation, at any layer
tested, even when the numeric value is held perfectly constant. A minimal
standalone candidate demonstrates the distinction is representable without
touching Phoenix's real hash chain or deciding whether it should affect
execution.

---

## Phase 2B — Three-architecture comparison

Three candidate architectures for carrying quality alongside Phoenix A's
real value pipeline, tested against six explicit invariants, without
presupposing a winner. All three reuse Phoenix A's real
`compute_canonical_hash` and real `generation_id` mechanism unmodified.

- **A — External sidecar:** quality in a wholly separate record, never
  touching Phoenix's real chain.
- **B — Incorporated canonical state:** quality as a required field of one
  object that also produces the real value hash, kept as a *separate* hash
  from value provenance (not merged into one).
- **C — Domain-module interpretation:** same preservation as B, plus an
  explicit downstream interpretation function, structurally separate from
  Phoenix's own execution decision.

| Invariant | A | B | C |
|---|---|---|---|
| 1. Value-only change → value provenance changes | PASS | PASS | PASS |
| 2. Quality-only change → semantic provenance changes | PASS | PASS | PASS |
| 3. Generation change → generation identity changes | PASS | PASS | PASS |
| 4. Replay reproduces both value and quality | Value: yes. Quality: **no** (structural — two independent logs) | Value: yes. Quality: **structurally possible, not currently real** | Same as B |
| 5. Removing quality can't silently reproduce the same state | **FAILS** — Phoenix's own artifacts are identical either way | **PASS** — quality is a required constructor field | **PASS** (same mechanism as B) |
| 6. Domain module can consume quality without Phoenix deciding what BAD means | PASS, trivially | PASS, implicit | **PASS, explicitly demonstrated** |

**Result:** invariants 1–3 are satisfied identically by all three (they
only exercise mechanisms already real in Phoenix). Invariant 4 is
unsatisfied by all three today — sidecar's gap is permanent and structural;
B/C's gap is an unimplemented extension to real Phoenix persistence code,
not a design flaw. Invariant 5 concretely separates sidecar (fails) from B
and C (pass). No architecture was recommended as "correct" — this
comparison established what each structurally can and cannot do, not which
should be built.

---

## EW-003 / Phase 2C — Semantic-state persistence and cold reconstruction

The first point in this campaign where a real Phoenix A source file was
added — deliberately withheld until this phase, so the preceding
experiments weren't designed around an implementation that didn't exist
yet.

**Scope, held narrow deliberately:** the smallest possible semantic
object — one value, one opaque quality string, one binding hash. No
confidence scores, no domain reasoning. `semantic_state_contract.py` is
freestanding: not imported by, and does not import from, any existing
Phoenix A pipeline file. `BAD` does not mean "reject execution" — that
would have answered a different question.

**The experiment:**

```
H(GOOD, 7.1) != H(BAD, 7.1)
```

confirmed directly and through real cold reconstruction — written to an
actual disk file, read back as a separate operation, value/quality/hash
all reconstructed exactly across four mixed readings, in order.

**Result, in full:**

- 10/10 new tests passed, including tamper-detection on both fields
  (stored hash never trusted, always recomputed — the exact convention
  `CI-004` found had zero enforcement elsewhere in the codebase; this new
  code has coverage for it from the start) and confirmation that two
  entirely novel, unrecognized quality strings work identically to the
  three the external spec named (no content-based whitelisting).
- The real, unmodified Phoenix pipeline was run for a GOOD and a BAD case:
  `success=True` in both — identical to `EW-001`'s own original
  measurement, confirmed by direct comparison. Nothing in the real
  pipeline imports or references the new file.
- Full existing suite re-run: 474/474 (sandbox baseline) plus 10/10 new,
  zero regressions.

**What this demonstrates:** the information-preservation gap `EW-001`
identified is not an inherent limitation of Phoenix A's determinism/
hash-chain model — a minimal, additive extension preserves and
cryptographically distinguishes the missing semantic information while
leaving Phoenix's real execution decision completely untouched.

**What this does not demonstrate, stated as plainly as what it does:**
whether this extension should ever influence a real decision (a
domain-module question, untouched here); whether a richer semantic object
would preserve the same separation as cleanly; whether this pattern
generalizes beyond quality/trust to other external-boundary gaps; whether
invariant 4 (replay of quality) can actually be closed without deeper
changes to Phoenix's real persistence layer.

---

## Phase 2 — what was demonstrated, in total

- The GOOD/BAD distinction is representable without corrupting Phoenix
  A's value provenance, generation identity, or execution determinism.
- The distinction survives persistence and cold reconstruction, and is
  tamper-evident.
- The distinction remains outside execution semantics — Phoenix A's real
  success/fail decision is provably identical with or without it.
- Not every candidate architecture achieves this equally: a sidecar
  approach concretely fails to prevent silent removal; an incorporated
  canonical-state approach concretely does not.

## Phase 2 — what remains unresolved

- Replay of the quality signal itself (invariant 4) — unsatisfied by
  every architecture tested, for different reasons.
- Whether quality *should* ever influence a decision, and if so, where
  that decision belongs.
- Whether the pattern demonstrated here for a single scalar quality flag
  holds for richer semantic objects.
- Whether the boundaries demonstrated (external semantic state,
  computational representation, provenance, execution interpretation) can
  be formally characterized rather than only experimentally shown to hold
  in these specific constructions.

---

## What comes next — explicitly not started here

Per the framing this phase was scoped under: the next question is not
another architectural expansion or another isolated finding. It's whether
someone who did not build Phoenix A can reproduce the central semantic
distinction from the frozen external specification alone — moving toward
the independent-oracle problem `CI-005` first exposed, this time applied
to the external-workload thread itself rather than to Phoenix A's internal
replay mechanism. Not begun in this document.

# MODE_B_CLAIMS_REGISTRY.md

**Scope: Mode B only** (multi-generation replay — `generation_segmentation.py`, `generation_segment_verification.py`, `candidate_lineage_construction.py`). Not a project-wide claims registry. `PHOENIX_VERIFICATION_STATE.md` remains the project's general evidence ledger; this file exists because Mode B's claims are now precise enough (via `REPLAY_GENERATION_MODEL.md`'s Theorem 1/Theorem 2) to warrant stable, referenceable IDs, and because the project has been doing this informally in `PHOENIX_VERIFICATION_STATE.md`'s tables all session without a compact citable handle. Whether this pattern is worth extending project-wide is a separate, later decision — not made here.

**Status vocabulary (closed set, do not introduce ad hoc statuses):**
- **VERIFIED** — the claim is proven true, bounded by explicitly stated assumptions, with passing tests as evidence.
- **FORMALLY NOT PROVABLE** — the claim is proven to be *unprovable* under a stated evidence model. Stronger and more specific than "unverified" — this status means a proof of impossibility exists, not merely that no proof of possibility has been attempted yet.

---

## MB-001 — Within-generation hash-chain continuity

**Description:** for a segment of records sharing one `generation_id`, if Phase 2 reports `fully_verified=True`, the segment's records form one continuous, internally-untampered hash chain, anchored to genesis at that `generation_id`.

**Status:** VERIFIED

**Evidence:** `kernel_state_replay.py::replay_and_verify_state_hashes()` (pre-existing, reused unmodified); `generation_segment_verification.py::verify_segments()`; `test_generation_segment_verification.py`, 5/5, built from genuinely executed engine runs, not fabricated hashes.

**Limitation:** proves internal chain self-consistency only, bounded by SHA-256 collision and second-preimage resistance. Does **not** authenticate that the chain's original inputs were genuine — someone with the ability to execute the same deterministic code from genesis on different chosen inputs could construct an equally self-consistent, equally `fully_verified` segment. See `REPLAY_GENERATION_MODEL.md`, Theorem 1's full statement.

---

## MB-002 — Generation boundary discovery

**Description:** a persisted `ExecutionAuditRecord` history can be partitioned into contiguous segments, each sharing one `generation_id`, purely from the persisted field — no replay involved.

**Status:** VERIFIED

**Evidence:** `generation_segmentation.py::segment_by_generation()`; `test_generation_segmentation.py`, 8/8, including a structural AST-based test proving the module never imports `KernelStateMachine` or performs hash computation (not just a docstring claim).

**Limitation:** purely a function of the `generation_id` field as persisted. Performs no hash verification itself (see MB-001) and makes no claim about *why* a boundary exists — that's MB-004's limited, corroboration-only concern, not this claim's.

---

## MB-003 — Cross-generation continuity

**Description:** whether two adjacent, independently-verified segments with different `generation_id` values represent a genuine continuation of the same kernel instance, versus a coincidental adjacency of two unrelated instances' logs.

**Status:** FORMALLY NOT PROVABLE (under the current persisted evidence model)

**Evidence:** `REPLAY_GENERATION_MODEL.md`, Theorem 2 — an information-theoretic proof, not an engineering limitation. `generation_id` at a reset is minted via `uuid.uuid4()`, statistically independent of the prior `generation_id` and everything else persisted (confirmed directly in `kernel_state_replay.py`'s own source comment on the `FAULTED -> INITIALIZING` transition).

**Limitation, stated as precisely as the theorem itself:** this is not a "not yet" status. No function of persisted evidence — however constructed, however much circumstantial evidence is gathered — can ever close this gap under the current schema. The only thing that could change this status is a schema change persisting evidence dependent on the prior `generation_id` (e.g., the deliberately-deferred `GenerationTransitionRecord`). See `REPLAY_GENERATION_MODEL.md`'s "What would have to change" section for the exact structural requirement, and its "when to revisit" criteria for why that record type remains deferred rather than built.

**Semantic inflation risk for future integrators (added 2026-08-06, `ADVERSARIAL_METHODOLOGY.md`):** `SegmentVerificationResult.fully_verified` proves only within-segment continuity (`MB-001`). Nothing in that property's name warns against reading two adjacent, both-`fully_verified` segments as implying the *boundary between them* is also verified — `MB-003` says it structurally cannot be. This is not a risk in current code (no aggregation or confidence-scoring exists yet to make this mistake), but a real risk for whatever is built next on top of Mode B — a dashboard, a report, an alert. **Any future code presenting `fully_verified` results to a human or another system MUST NOT imply cross-segment continuity from two individually-true `fully_verified` values without also surfacing `MB-003`'s boundary alongside them.**

---

## MB-004 — Candidate lineage construction

**Description:** given a set of MB-002-segmented, MB-001-verified segments, construct the graph that best fits the evidence — never claiming it is the proven, unique lineage.

**Status:** VERIFIED (as a graph-construction procedure — explicitly **not** VERIFIED as a continuity proof; see MB-003, which this claim depends on and does not override)

**Evidence:** `candidate_lineage_construction.py::construct_candidate_lineage()`; `test_candidate_lineage_construction.py`, 8/8, including a deliberately hand-corrupted segment proving unverified segments are excluded and never silently bridged, and (2026-08-08, adversarial finding) a same-generation-adjacency guard proving two real, independently-verified segments sharing one `generation_id` are rejected outright rather than silently producing a meaningless edge.

**Limitation:** every edge in the constructed graph carries `continuity_caveat` unconditionally, restating MB-003's boundary on every single edge rather than once in a docstring. `fault_record_precedes_boundary` is supporting evidence only, never proof of *why* a transition occurred — and its `False` value is explicitly documented as not suspicious, since the schema does not guarantee a fault record exists for every real administrative reset.

**Fixed 2026-08-08 (adversarial finding, MB-004's first attempted attack family):** `construct_candidate_lineage()` defended its length-match precondition with a `raise` but never verified a comparably load-bearing one — that adjacent segments actually represent different generations, which `generation_segmentation.py`'s `segment_by_generation()` structurally guarantees for real Phase 1 output but this function never re-checked. A caller bypassing Phase 1 with malformed input (two adjacent, genuinely-verified segments sharing one `generation_id`) would previously get a `CandidateLineageEdge` with `from_generation_id == to_generation_id` — not a data-integrity failure, a "boundary" that doesn't represent any real transition at all, accepted silently. Now raises `ValueError` immediately, matching the existing length-check's own pattern. Same disposition precedent as `PG-001`: an adversarial-fabrication-only finding (Phase 1 itself can never produce this input) still gets fixed, not just documented, in this project.

---

## Claim dependency graph

```
MB-001 (within-generation continuity, VERIFIED)
   |
   v
MB-004 (candidate lineage construction) -- depends on: needs verified segments to have anything to connect

MB-002 (generation boundary discovery, VERIFIED)
   |
   v
MB-004 -- depends on: needs a segmentation to know what the candidate nodes even are

MB-003 (cross-generation continuity, FORMALLY NOT PROVABLE)
   |
   v
MB-004 -- constrained by: every edge MB-004 constructs carries MB-003's continuity_caveat
             unconditionally; MB-004 does NOT and cannot defeat MB-003's impossibility result
```

**MB-004 depends on:**
- MB-001 — a segment must be `fully_verified` before it can appear as a node in the candidate graph at all (`construct_candidate_lineage()` filters to `verification_results` where `fully_verified` is true; excluded segments never become nodes).
- MB-002 — segmentation is what defines the candidate nodes and their order in the first place; MB-004 never re-derives boundaries itself, only consumes Phase 1's output.

**MB-004 does not defeat:**
- MB-003 — this is the relationship worth stating precisely, not just noting. MB-004 is not "weaker evidence toward" MB-003's impossibility result; it cannot make partial progress against it, because MB-003 is a proof, not a confidence level. No amount of graph-construction sophistication moves MB-004 closer to overriding MB-003 — that's the entire reason `continuity_caveat` is unconditional on every edge rather than varying by how much corroborating evidence (e.g. a trailing fault record) happens to be present. `fault_record_precedes_boundary` can make an edge's *narrative* more plausible; it cannot make the edge provable, because MB-003 already forecloses that regardless of narrative plausibility.

**MB-001 and MB-002 do not depend on each other.** Phase 1 (MB-002) runs as a pure function with zero awareness of Phase 2 (MB-001) — confirmed structurally, not just by claim, via `generation_segmentation.py`'s own AST-based test proving it never imports `KernelStateMachine` or performs hash computation. Either could in principle be replaced independently (e.g. a different segmentation heuristic, or a future Path A hash-verification strategy per `KernelStateVerifier`'s own substitutability) without disturbing the other.

---

## What this registry does not cover

- Gap 1 (`KernelStateEnvelope.state_hash` consistency from disk alone, no live `KernelStateMachine`) — orthogonal to all four claims above; Mode B's completion does not change Gap 1's status. See `COLD_BOOT_RECONSTRUCTION_CONTRACT.md`.
- Gap 2 (policy decision hash provenance) — closed, unrelated to Mode B; see `PHOENIX_VERIFICATION_STATE.md`.
- The schema-evolution arc (`SCHEMA_EVOLUTION_MODEL.md` and downstream) and the provenance-graph arc (`PROVENANCE_GRAPH_MODEL.md`, the Check 1 fix) — both real, both completed, neither reflected here since this registry is Mode B-scoped only.

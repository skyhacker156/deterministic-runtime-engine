# MODE_B_CLAIMS_REGISTRY.md

**Scope: Mode B only** (multi-generation replay — `generation_segmentation.py`, `generation_segment_verification.py`, `candidate_lineage_construction.py`). Not a project-wide claims registry. `PHOENIX_VERIFICATION_STATE.md` remains the project's general evidence ledger; this file exists because Mode B's claims are now precise enough (via `REPLAY_GENERATION_MODEL.md`'s Theorem 1/Theorem 2) to warrant stable, referenceable IDs, and because the project has been doing this informally in `PHOENIX_VERIFICATION_STATE.md`'s tables all session without a compact citable handle. Whether this pattern is worth extending project-wide is a separate, later decision — not made here.

**Status vocabulary (closed set, do not introduce ad hoc statuses):**
- **VERIFIED** — the claim is proven true, bounded by explicitly stated assumptions, with passing tests as evidence.
- **FORMALLY NOT PROVABLE** — the claim is proven to be *unprovable* under a stated evidence model. Stronger and more specific than "unverified" — this status means a proof of impossibility exists, not merely that no proof of possibility has been attempted yet.

---

## MB-001 — Within-generation hash-chain continuity

**Description:** for a segment of records sharing one `generation_id`, if Phase 2 reports `fully_verified=True`, the segment's records form one continuous, internally-untampered hash chain, anchored to genesis at that `generation_id`.

**Status:** VERIFIED

**Evidence:** `kernel_state_replay.py::replay_and_verify_state_hashes()` (pre-existing, reused unmodified); `generation_segment_verification.py::verify_segments()`; `test_generation_segment_verification.py`, 6/6, built from genuinely executed engine runs, not fabricated hashes.

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

**Evidence:** `candidate_lineage_construction.py::construct_candidate_lineage()`; `test_candidate_lineage_construction.py`, 11/11, including a deliberately hand-corrupted segment proving unverified segments are excluded and never silently bridged, (2026-08-08) a same-generation-adjacency guard, (2026-08-08) a segment/verification-result cross-validation guard, and (2026-08-08) a global (non-adjacent) generation-uniqueness guard. `generation_segment_verification.py::verify_segments()`; `test_generation_segment_verification.py`, 6/6, including (2026-08-08) a segment-label cross-check.

**Limitation:** every edge in the constructed graph carries `continuity_caveat` unconditionally, restating MB-003's boundary on every single edge rather than once in a docstring. `fault_record_precedes_boundary` is supporting evidence only, never proof of *why* a transition occurred — and its `False` value is explicitly documented as not suspicious, since the schema does not guarantee a fault record exists for every real administrative reset.

**Fixed 2026-08-08 (adversarial finding, MB-004's first attempted attack family — Substitution):** `construct_candidate_lineage()` defended its length-match precondition with a `raise` but never verified a comparably load-bearing one — that adjacent segments actually represent different generations, which `generation_segmentation.py`'s `segment_by_generation()` structurally guarantees for real Phase 1 output but this function never re-checked. A caller bypassing Phase 1 with malformed input (two adjacent, genuinely-verified segments sharing one `generation_id`) would previously get a `CandidateLineageEdge` with `from_generation_id == to_generation_id` — not a data-integrity failure, a "boundary" that doesn't represent any real transition at all, accepted silently. Now raises `ValueError` immediately, matching the existing length-check's own pattern. Same disposition precedent as `PG-001`: an adversarial-fabrication-only finding (Phase 1 itself can never produce this input) still gets fixed, not just documented, in this project.

**Fixed 2026-08-08 (adversarial finding, second attack family — Omission):** `segments` and `verification_results` are two separate parameters, and nothing previously verified that `verification_results[i]` was genuinely computed from `segments[i]` — only `verification_results[i]`'s own fields were read for edge identity, while `_last_record_is_fault()` separately reads `segments[i]`'s actual records. A caller supplying a mismatched pair (each individually valid, real output of `verify_segments()`, just paired against the wrong segment) would get an edge whose reported identity and whose fault-evidence came from two different, uncorrelated generations — the cross-check connecting a verification result back to the segment it claims to describe simply didn't exist. Now validated upfront, for every index, before any edge construction begins. Same disposition as above.

**Fixed 2026-08-08 (adversarial finding, third attack family — Boundary Crossing, root cause traced upstream to Phase 2):** `GenerationSegment` is a plain frozen dataclass with no validation of its own — nothing enforces `generation_id` (the external label) actually matches what `records` contains. `replay_and_verify_state_hashes()` independently derives its own reference generation_id from `execution_history[0].generation_id` and checks every record's internal consistency against *that* — but had no parameter for an externally-claimed label, and `verify_segments()` was trusting `segment.generation_id` wholesale when building `SegmentVerificationResult`, never comparing it to what the records themselves actually attest to. A segment with internally consistent, genuinely-valid records (all truly generation B, correctly hash-chained) but a false external label (claiming A) would previously produce `fully_verified=True` with the WRONG `generation_id`, `unexpectedly_crosses_generation_boundary` staying `False` throughout, since nothing about the replay itself was actually inconsistent — invisible to the existing mixed-generation test, which covers a different failure shape (a later record diverging mid-stream, not the whole segment being consistently, wholly mislabeled from the start). This gap sat in Phase 2 (`verify_segments()`), not Phase 3 — but MB-004's own edges are built directly from Phase 2's output, so a mislabeled segment reaching Phase 3 undetected would have made MB-004's reported `from_generation_id`/`to_generation_id` wrong regardless of the first two fixes. Now checked explicitly before any result is built. Same disposition as above.

**Fourth attack family attempted — Orphan (2026-08-08): clean pass, not fixed, because there was nothing to fix.** Traced three independent mechanisms that jointly close this family off: `edges` and `verified_segments` both derive from the same `verification_results` list (edge endpoints structurally guaranteed present in inventory); the same-generation-adjacency guard above (built for Substitution) closes the one way a self-referential orphan edge could form; and the segment/result cross-check above (built for Omission) covers `excluded_segments` the same way it covers `verified_segments`. Two of the three closing mechanisms were built for *different* attack families and happen to jointly close Orphan as a side effect — recorded as a genuine, traced clean pass, not an absence of trying. See `ADVERSARIAL_METHODOLOGY.md`'s Eleventh finding for the full trace.

**Fifth attack family attempted — Asymmetry (2026-08-08): found → formally documented limitation, not fixed.** Two candidates traced. The apparent current/next read asymmetry in the edge-building loop was ruled out — closed transitively by the Omission fix's per-index validation, which already covers the "missing" relationship. The real finding: `construct_candidate_lineage()` treats list *position* as chronological succession, with nothing verifying it — confirmed via a reversed-order construction (two genuine, independently-verified real generations, handed in as `[B, A]` instead of `[A, B]`) producing a backwards edge. Traced to the same root cause as MB-003's own Theorem 2 (the Generation Identity Independence Principle) and formalized as a **Corollary to Theorem 2** in `REPLAY_GENERATION_MODEL.md`: cross-generation chronological ordering is, like identity continuity, unprovable under the current persisted evidence model — not a missing check, an absence of any persisted field carrying the needed signal at all. Deliberately no defensive raise added — rejecting some orderings without knowing which is correct would replace an honest "cannot determine" with a false "corrected." See `ADVERSARIAL_METHODOLOGY.md`'s Twelfth finding and `REPLAY_GENERATION_MODEL.md`'s Corollary section for the full argument, including the explicit input-contract-vs-verification-claim distinction (ordering matters to the graph's meaning even though it isn't independently verifiable).

**Fixed 2026-08-08 (adversarial finding, sixth attack family — Duplication):** the same-generation-adjacency guard added for Substitution only ever compared *adjacent* pairs (`segments[i]` vs `segments[i+1]`) — genuinely adjacent. Nothing checked global uniqueness of `generation_id` across the whole list, even though `generation_segmentation.py`'s `segment_by_generation()` (Phase 1) enforces a *stronger* invariant: `UnsegmentableHistoryError` fires the instant any `generation_id` reappears anywhere after a later, different one was witnessed, adjacent or not. A caller bypassing Phase 1 with three individually-genuine, independently-verified segments assembled as `[A, B, A]` — no adjacent pair sharing a `generation_id` — would previously pass every existing check while generation A appeared twice, non-adjacently: two edges (`A→B` and `B→A`) and a `verified_segments` tuple containing generation A twice, a candidate graph asserting the kernel returned to a generation it had already left. Fixed by replacing the adjacent-only comparison with a single global-uniqueness pass, checked before any edge construction begins — this *subsumes* the original adjacent-only check rather than sitting alongside it. Same disposition precedent as the other three fixed findings above.

**Seventh and final attack family attempted — Semantic Inflation (2026-08-08): found → documented limitation, no code change.** Framed around consumer-facing meaning rather than malformed input: can a caller take individually valid `fully_verified=True` segments and infer something stronger than `MB-001` establishes? Traced three checkpoints against real source: `fully_verified` itself is a clean passthrough of Phase 2's replay result; `continuity_caveat` is an unconditional property on every edge, not silently omittable; but the module's own docstring, which thoroughly warns against the identity-continuity misreading (`MB-003`, via its "WHAT AN EDGE ACTUALLY ASSERTS" section), said nothing at all about the structurally identical ordering misreading this session's Asymmetry finding established. A caller reading only this module's own documentation could reasonably infer a constructed edge `A → B` means the system has established A occurred before B — it has not, and per the Corollary to Theorem 2, cannot. Fixed by adding a new, parallel-weight docstring section stating the limitation in the theorem's own strength of claim ("the persisted evidence does NOT independently establish chronological ordering," not the weaker "ordering is not guaranteed"). No behavior change, no new test — matching this campaign's precedent for pure-documentation findings.

`MB-004` reached full family coverage 2026-08-08 — the first claim in the adversarial campaign to do so. Final shape: Substitution, Omission, Boundary Crossing, and Duplication all found→fixed (4 of 7); Orphan clean (1 of 7); Asymmetry and Semantic Inflation found→documented limitation (2 of 7).

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
- MB-003 — this is the relationship worth stating precisely, not just noting. MB-004 is not "weaker evidence toward" MB-003's impossibility result; it cannot make partial progress against it, because MB-003 is a proof, not a confidence level. No amount of graph-construction sophistication moves MB-004 closer to overriding MB-003 — that's the entire reason `continuity_caveat` is unconditional on every edge rather than varying by how much corroborating evidence (e.g. a trailing fault record) happens to be present. `fault_record_precedes_boundary` can make an edge's *narrative* more plausible; it cannot make the edge provable, because MB-003 already forecloses that regardless of narrative plausibility. The same logic now extends to ordering, per the Asymmetry finding's Corollary above: MB-004's edges assert a direction, but that direction is exactly as unprovable from persisted evidence as identity continuity is.

**MB-001 and MB-002 do not depend on each other.** Phase 1 (MB-002) runs as a pure function with zero awareness of Phase 2 (MB-001) — confirmed structurally, not just by claim, via `generation_segmentation.py`'s own AST-based test proving it never imports `KernelStateMachine` or performs hash computation. Either could in principle be replaced independently (e.g. a different segmentation heuristic, or a future Path A hash-verification strategy per `KernelStateVerifier`'s own substitutability) without disturbing the other.

---

## What this registry does not cover

- Gap 1 (`KernelStateEnvelope.state_hash` consistency from disk alone, no live `KernelStateMachine`) — orthogonal to all four claims above; Mode B's completion does not change Gap 1's status. See `COLD_BOOT_RECONSTRUCTION_CONTRACT.md`.
- Gap 2 (policy decision hash provenance) — closed, unrelated to Mode B; see `PHOENIX_VERIFICATION_STATE.md`.
- The schema-evolution arc (`SCHEMA_EVOLUTION_MODEL.md` and downstream) and the provenance-graph arc (`PROVENANCE_GRAPH_MODEL.md`, the Check 1 fix) — both real, both completed, neither reflected here since this registry is Mode B-scoped only.

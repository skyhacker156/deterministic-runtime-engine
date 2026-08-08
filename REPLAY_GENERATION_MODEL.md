# REPLAY_GENERATION_MODEL.md

**Status: Phases 1-3 IMPLEMENTED and tested. This document is now the formal specification of what those phases prove, not a pre-implementation design.** `generation_segmentation.py`, `generation_segment_verification.py`, and `candidate_lineage_construction.py` all exist and are covered by their corresponding test suites and the full verification suite alongside everything else in this project. What remained genuinely open after implementation was not "what to build next" but "under exactly what conditions can Phoenix claim two records belong to the same execution generation" — precisely, not probabilistically. That question is answered in **"The Formal Question, Answered"** below, and the answer is what makes the rest of this document a specification rather than a changelog.

---

## Two replay claims, not one

### Replay Mode A — "Can I rerun the same computation?"

The claim: given a fixed starting point (a specific generation), replaying or re-executing the same logical input sequence produces identical output hashes.

- **A1 — synthetic determinism.** Two independently-constructed engine instances, explicitly seeded with the *same* `generation_id` via `DeterministicExecutionEngine.with_generation()`, given the same synthetic input sequence, produce identical hashes. Proven by `test_deterministic_execution_engine.py::test_replay_equivalence_determinism`, `test_module_contract_compliance.py::test_module_replay_matches`, and the rest of the replay-equivalence cluster.

- **A2 — real-history replay, single generation.** A *real*, already-persisted execution stream is replayed sequentially through a `KernelStateMachine` reconstructed via `from_history()`, and the replayed hash chain is compared against what was actually persisted. Proven by `test_kernel_state_replay.py`, scoped explicitly to a single generation.

**A1 and A2 are both proven. Neither is Mode B.**

### Replay Mode B — "Can I reconstruct the exact historical execution lineage?"

The claim: given a real, persisted history that spans **more than one generation**, replay can reconstruct the full lineage — which records belong to which generation, in what order, with each transition correctly identified.

```
Generation 1
    |
    frame 1
    frame 2
    fault
    reset
    |
Generation 2
    |
    frame 3
    frame 4
```

**Current status: all three phases below are implemented.** What they collectively prove — and, precisely, do not prove — is the subject of this document from here on.

---

## Why three phases

Mode B decomposes into three much smaller problems with a hard boundary between them:

```
Phase 1: Segmentation      -- graph discovery, no replay [IMPLEMENTED]
Phase 2: Independent verification -- existing replay engine, run per segment [IMPLEMENTED]
Phase 3: Candidate lineage construction -- graph construction, no replay [IMPLEMENTED]
```

Phase 2 consumes Phase 1's output and nothing else; Phase 3 consumes Phase 2's output and nothing else.

---

## Phase 1 — Generation segmentation [IMPLEMENTED: `generation_segmentation.py`]

**Input:** a persisted, already-reconstructed `List[ExecutionAuditRecord]` history.
**Output:** `List[GenerationSegment]`, each a contiguous range sharing one `generation_id`.

Nothing is replayed. Nothing is reconstructed. Pure grouping over the existing `generation_id` field — confirmed pure by AST-based import inspection (`test_module_never_imports_kernel_state_machine_or_hashlib`), not merely by docstring claim.

### Phase 1 SHALL (implemented, tested)
- **SHALL derive segment boundaries purely from persisted `generation_id` values, in given order.** `test_two_generations_produce_two_ordered_segments`, `test_three_generations_produce_three_segments`.
- **SHALL reject a segmentation where a previously-seen `generation_id` reappears** after a later, different one was witnessed — `UnsegmentableHistoryError`, `test_generation_reappearing_after_a_later_generation_is_unsegmentable`.
- **SHALL produce independently checkable output.** `GenerationSegment.sequence_id_range`, direct field access.

### Phase 1 SHALL NOT (implemented, tested)
- **SHALL NOT construct a `KernelStateMachine` or perform hash verification.** `test_module_never_imports_kernel_state_machine_or_hashlib` (real AST-based check, not substring search — an earlier draft of this test used a substring check and false-positived on this module's own docstring; fixed).
- **SHALL NOT infer why a boundary exists.** No such inference exists anywhere in `generation_segmentation.py`.

---

## Phase 2 — Independent verification [IMPLEMENTED: `generation_segment_verification.py`]

**Input:** one `GenerationSegment` from Phase 1.
**Output:** a `SegmentVerificationResult`, produced by `kernel_state_replay.py`'s existing `replay_and_verify_state_hashes()` — **unmodified**.

### Phase 2 SHALL (implemented, tested)
- **SHALL verify each segment via the existing, unmodified replay machinery**, seeded via `from_history()` with that segment's own `generation_id`. `test_single_real_generation_segment_is_fully_verified`, `test_two_real_generations_both_independently_fully_verified` — both built from genuinely real `DeterministicExecutionEngine.with_generation()` runs, not fabricated hash bytes (fabricated bytes would simply fail replay, since `replay_and_verify_state_hashes()` genuinely recomputes).
- **SHALL treat each segment's verification as fully independent.** Each `.verify()` call constructs its own fresh `KernelStateMachine` internally; nothing is shared across segments — confirmed by `kernel_state_replay.py`'s own source, not assumed.

### Phase 2 SHALL NOT — the load-bearing cross-check (implemented, tested)
> **If Phase 1's segmentation is correct, every Phase 2 replay of a single segment must report no generation boundary.**

Implemented as `SegmentVerificationResult.unexpectedly_crosses_generation_boundary`. Proven both ways: `test_two_real_generations_both_independently_fully_verified` confirms it's `False` for correctly-segmented real data; `test_segment_spanning_two_real_generations_is_flagged_not_silently_passed` hand-corrupts a segment (a shape Phase 1 itself could never produce) and confirms the property correctly flags it rather than silently passing or crashing uninformatively.

---

## Phase 3 — Candidate lineage construction [IMPLEMENTED: `candidate_lineage_construction.py`]

**Input:** Phase 1's segments plus Phase 2's verification results, paired.
**Output:** a `CandidateLineageGraph` — deliberately never called "the lineage" anywhere in code, tests, or this document.

### Phase 3 SHALL (implemented, tested)
- **SHALL only include Phase-2-verified segments.** `CandidateLineageGraph.excluded_segments`, `coverage_is_partial` property. `test_unverified_segment_is_excluded_and_no_edge_bridges_across_it` proves an unverified segment is excluded *and* that no edge is built bridging across the gap it leaves.
- **SHALL make the continuity assumption explicit on every edge.** `CandidateLineageEdge.continuity_caveat`, present on every constructed edge, not optional.

### Phase 3 SHALL NOT (implemented, tested)
- **SHALL NOT claim full coverage on partial data.** `coverage_is_partial` exists specifically so this can't be silently missed.
- **SHALL NOT assert *why* a transition occurred as proven fact.** `fault_record_precedes_boundary` is corroboration only — `test_edge_without_preceding_fault_record_is_not_marked_suspicious` proves its *absence* is explicitly not treated as suspicious, matching the known schema gap (some fault paths trip `FAULTED` before an audit record is ever constructed).
- **SHALL NOT describe output as "the lineage."** Enforced by naming throughout: `CandidateLineageGraph`, `CandidateLineageEdge`, `construct_candidate_lineage()` — no type or function in this module is named without "candidate."

---

## The Formal Question, Answered

**The question:** under exactly what conditions can Phoenix claim that two persisted records belong to the same execution generation?

The answer has exactly two parts, and they are not points on a continuum of confidence — they are categorically different kinds of claim.

### Theorem 1 — Within-generation continuity is provable

**Statement:** for a segment of records sharing one `generation_id`, Phase 2 reporting `fully_verified=True` is possible if and only if a real `KernelStateMachine`, initialized fresh via `from_history()` at that `generation_id` with zero prior processed state, and fed exactly those records' frames in exactly that order, derives a `state_hash` at every step matching that record's persisted `prior_state_hash`.

**What this proves:** no record in the segment can have been modified in isolation — altered while every other record in the segment stays unchanged — without detection, except under failure of the underlying cryptographic assumptions (SHA-256 collision or second-preimage resistance). This is a narrower claim than "the segment reflects genuine, unmodified original inputs," and the wording is deliberate: someone with the ability to execute the same deterministic code from genesis on different, chosen inputs could construct an entirely different segment that is *also* internally self-consistent and *also* reports `fully_verified=True`. That is not a cryptographic attack — SHA-256 is not broken by it, and the resulting chain is completely honest about what it actually computed. Theorem 1 proves the chain cannot be tampered with piecemeal after the fact; it says nothing about whether the inputs the chain was built from were the genuine ones. See "internal consistency, not external authenticity" in "Explicitly out of scope," below, which this wording is written to match precisely rather than loosely gesture at.

**Evidence:** `test_two_real_generations_both_independently_fully_verified` and the whole Phase 2 test suite, built from genuinely executed engine runs, not fabricated fixtures.

### Theorem 2 — Cross-generation continuity is not provable, under the current persisted evidence model, ever

**Statement:** for two Phase-2-verified segments A and B with distinct `generation_id` values, adjacent in persisted order, there is no function of persisted evidence — however constructed, however much circumstantial evidence is gathered — that can distinguish "B is a genuine continuation of the same kernel instance that produced A" from "B is an entirely independent instance whose log happened to be appended directly after A's."

**Why, precisely:** `generation_id` at a reset is minted via `uuid.uuid4()` — a draw from a source of randomness with zero dependence on the prior `generation_id`, on the machine's prior state, or on any other persisted field. This is not an implementation gap; it is confirmed directly in `kernel_state_replay.py`'s own source comment: the `FAULTED -> INITIALIZING` transition "would mint a genuinely new random generation_id (identical behavior to production, since it's the same code path)." Since the new value is statistically independent of everything persisted about the old one, no algorithm operating only on persisted records — Phase 3's or any future one — can extract information distinguishing the two hypotheses above. This is a fact about the joint distribution of what the schema persists, not a limitation of `candidate_lineage_construction.py`'s specific logic.

**This is why every edge Phase 3 constructs carries `continuity_caveat` unconditionally**, and why `fault_record_precedes_boundary` is corroboration, never proof: no amount of circumstantial evidence changes Theorem 2's conclusion, because the thing being inferred (same-instance continuity) is, by construction, uncorrelated with everything observable.

### Corollary — Cross-generation chronological ordering is equally unprovable

**Statement:** for two Phase-2-verified segments A and B with distinct `generation_id` values, presented to Phase 3 in some order, there is no function of persisted evidence that can establish which segment's records genuinely occurred first in real time — a question logically independent of, and prior to, the identity-continuity question Theorem 2 answers.

**Why:** Phase 1 (`segment_by_generation()`) explicitly takes list order as given input — "SHALL derive segment boundaries purely from persisted `generation_id` values, in given order" — and verifies nothing about that order. The only per-record field that varies with real time, `frame_timestamp_ns`, is supplied by the caller at `CoreExecutionFrame.create()` with zero validation: `execution_kernel_contract.py`'s `__post_init__` and `verify_integrity()` check payload shape, hash type, and hash match — nothing about `timestamp_ns`. The subsequent hash chain makes a persisted `timestamp_ns` **tamper-evident** (an adversary cannot alter it in a real record after the fact without breaking Theorem 1's hash chain) — but tamper-evidence is not authenticity. The hash proves "this value was part of this artifact when created," never "this value accurately reflects when the frame actually occurred." This is the same internal-consistency/external-authenticity boundary Theorem 1 itself draws for its own claim.

**Demonstrated:** `test_reversed_generation_segments_produce_reverse_candidate_edge` constructs two genuinely independent, individually fully-verified real generations (A executed first, B executed second) and hands them to `construct_candidate_lineage()` in reversed list order. Every existing guard passes (length match, per-index correspondence, differing `generation_id`, both fully verified), and the function returns an edge asserting B -> A — the reverse of what actually happened — with nothing in the returned graph distinguishing this from the correct A -> B case.

**Relationship to Theorem 2:** not a restatement. Theorem 2 answers "are A and B the same kernel instance"; this corollary answers "which of A and B happened first" — two segments could in principle be provably ordered while their identity-continuity remains unprovable, or vice versa. Both trace to the same root cause via the Generation Identity Independence Principle: `generation_id`, and everything derivable only from records sharing it, is minted with zero dependence on anything prior — so nothing persisted carries a signal correlating one generation's segment to another's real-time position. `construct_candidate_lineage()` cannot be fixed to check ordering correctly, because there is no persisted field to check it against.

**What would have to change:** the same structural requirement as Theorem 2's own answer — new persisted evidence not independent of the prior generation, e.g. an externally-attested, tamper-evident clock or ordering signal outside the current three-log schema. Caller-supplied `frame_timestamp_ns` does not meet this bar and must never be treated as if it does.

**Input contract, distinguished explicitly from verification claim.** This Corollary does not mean ordering is meaningless to Phase 3 — it means Phoenix cannot independently confirm it. The two are different statements, and conflating them would be its own kind of semantic inflation, in the opposite direction from usual (understating a real requirement rather than overstating a proof):

- **Input contract (an operational requirement on the caller):** `segments` MUST be supplied in true historical order — the order in which the underlying records actually occurred. `construct_candidate_lineage()`'s entire output is only meaningful under this assumption; every edge's `from_generation_id -> to_generation_id` direction is a direct expression of it.
- **Verification claim (what Phase 3 can actually prove):** Phoenix has no persisted-evidence-based way to confirm that contract was honored. A caller who violates it — accidentally or adversarially — gets a candidate graph that is silently backwards, not one that fails loudly.

Ordering matters to what the candidate graph *means*; it is simply not among the things this system can *verify*. Any future documentation, dashboard, or API docstring describing `construct_candidate_lineage()` should state the input contract plainly rather than let the Corollary's unprovability read as license to treat input order as unimportant.

### The unifying principle

Theorem 2 is not a Phase-3-specific finding — it is the same underlying fact, applied at three points that have, until now, been documented as three separate caveats:

| Where it was previously stated | What it actually is |
|---|---|
| `kernel_state_replay.py`'s "limitation 2" (single generation only) | Theorem 2 applied to why replay must stop at a boundary rather than guess through it |
| Phase 1's "genesis is always assumed, never proven" (`COLD_BOOT_RECONSTRUCTION_CONTRACT.md`'s Canonical Replay Verification SHALL NOT) | Theorem 2 applied to the *first* record in any history — genesis itself is a `generation_id` with nothing upstream of it to check, for exactly the same reason a mid-history boundary has nothing linking it backward |
| `REPLAY_GENERATION_MODEL.md`'s original single-instance-continuity caveat | Theorem 2 stated informally, before this document derived it formally |

All three are the same theorem. **Call it the Generation Identity Independence Principle**: `generation_id` values are, by design, statistically independent across a reset — which is precisely what makes them trustworthy as *identity* (two different generations will essentially never collide) and precisely what makes them useless as *continuity evidence* (a genuine reset and a coincidental fresh instance are indistinguishable from the value alone). The same design choice that closed Gap 1b cannot also close the cross-generation lineage question — they are opposite requirements on the same field. The Corollary above shows this same principle also forecloses chronological ordering, not only identity continuity.

### What would have to change for Theorem 2's status to change

Not vague future work — the precise structural requirement: a new piece of *persisted evidence that is not independent of the prior generation*. Concretely, this means either (a) the reset transition itself persists a value derived from or referencing the prior `generation_id` (breaking the independence Theorem 2's proof relies on), or (b) an external, out-of-band attestation of process identity that the current three-log schema has no field for. This is exactly what the previously-deferred `GenerationTransitionRecord` idea would provide, and exactly why deferring it was correct: without it, no amount of additional replay logic changes Theorem 2's conclusion, so building more replay machinery ahead of that schema decision would have been pure speculation. The deferral is not "we haven't gotten to it" — it is "nothing except this specific kind of schema change can do it."

---

## The open question — resolved, now with the formal justification behind it

**Decision, unchanged from before: do not add `GenerationTransitionRecord` or any equivalent yet.** What's new is *why* this is now a settled conclusion rather than a judgment call: Theorem 2 proves that no amount of application-layer cleverness — better heuristics, more corroborating signals, richer candidate-graph logic — can ever cross the proof/candidate boundary Phase 3 respects. The only lever that could ever move it is the schema change itself. This means continuing to build replay/lineage logic without that schema change cannot get closer to proving cross-generation continuity, no matter how sophisticated it becomes — a fact worth having proven rather than assumed, since it forecloses a whole category of future "maybe if we just add more evidence-gathering" proposals.

**When to revisit:** unchanged — a real, demonstrated need to distinguish genuine continuation from coincidental collision, not a hypothetical one.

---

## Explicitly out of scope for this document

- No code changes in this revision. All three phases are exactly as previously committed (451/451).
- No decision to build `GenerationTransitionRecord` — Theorem 2 explains why it would be required to change the answer, not that it should be built now.
- No claim about `KernelStateEnvelope.state_hash` consistency outside Mode B's scope — that remains Gap 1's separate question (`COLD_BOOT_RECONSTRUCTION_CONTRACT.md`).
- No claim that Theorem 1 authenticates *who* produced a segment's records, or that its inputs were genuine — only that the segment is internally self-consistent. See Theorem 1's own "What this proves," above, which states this boundary directly rather than leaving it only here. This is a boundary of every hash-based check in this codebase, not specific to Mode B.

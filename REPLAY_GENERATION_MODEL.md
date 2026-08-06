# REPLAY_GENERATION_MODEL.md

**Status: design note, pre-implementation.** Nothing in this document is built. It exists to settle what "replay" actually claims to prove before extending `from_history()` or `kernel_state_replay.py` any further — see `PHOENIX_VERIFICATION_STATE.md`'s Execution Generation Identity section for what is currently proven, and its Gap 1b entry for why this document exists at all.

**Scope note, matching `PHOENIX_VERIFICATION_STATE.md`'s own convention:** this document distinguishes two claims that have so far been talked about as one thing — "replay works." They are not the same claim, they are not proven by the same evidence, and conflating them is exactly the mistake this session already found and fixed once (several tests named `*_replay_determinism` were actually testing something narrower than their names implied, until `with_generation()` made the distinction explicit).

**Revision note (this version):** Mode B, originally described as one undifferentiated capability, is decomposed below into three phases with a hard boundary between them. This is a scope-reduction decision, not just an organizational one — see "Why three phases" below.

---

## Two replay claims, not one

### Replay Mode A — "Can I rerun the same computation?"

The claim: given a fixed starting point (a specific generation), replaying or re-executing the same logical input sequence produces identical output hashes.

This claim has two distinct sub-cases, currently conflated in casual conversation but proven by different mechanisms:

- **A1 — synthetic determinism.** Two independently-constructed engine instances, explicitly seeded with the *same* `generation_id` via `DeterministicExecutionEngine.with_generation()`, given the same synthetic input sequence, produce identical hashes. This proves the computation itself is deterministic, holding generation identity constant as a controlled variable. Proven by `test_deterministic_execution_engine.py::test_replay_equivalence_determinism`, `test_module_contract_compliance.py::test_module_replay_matches`, and the rest of the replay-equivalence cluster fixed this session.

- **A2 — real-history replay, single generation.** A *real*, already-persisted execution stream — not a freshly synthesized one — is replayed sequentially through a `KernelStateMachine` reconstructed via `KernelStateMachine.from_history()`, and the replayed hash chain is compared against what was actually persisted at the time. This proves replay can faithfully reproduce one real historical generation's causal chain, not just that two synthetic runs agree with each other. Proven by `test_kernel_state_replay.py` (all 6 tests), scoped explicitly to a single generation — see that file's own module docstring.

**A1 and A2 are both proven. Neither is Mode B.**

### Replay Mode B — "Can I reconstruct the exact historical execution lineage?"

The claim: given a real, persisted history that spans **more than one generation** — i.e., contains one or more genuine administrative resets — replay can reconstruct the full lineage: which records belong to which generation, in what order, with each generation-to-generation transition correctly identified and accounted for.

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

The question Mode B answers: **can Phoenix reconstruct that exact graph** — not just verify that generation 1's frames are internally consistent, and separately that generation 2's frames are internally consistent, but that the *transition itself*, its position, and its cause are all correctly recovered from disk alone.

**Current status: NOT proven. Nothing in the codebase attempts this today.**

What exists today that Mode B would build on:
- `generation_id` is a real, persisted field on `DecisionRecord` and `ExecutionAuditRecord` (round-trips through JSON — `test_decision_record_persistence.py`, `test_execution_audit_persistence.py`).
- `kernel_state_replay.py` already *detects* a generation change mid-history (`generation_boundary_index` on `KernelReplayReport`) and, on detecting one, **stops and reports** rather than attempting to continue. This is deliberate — see that module's own docstring, limitation 2 — but it means the boundary is currently a stopping condition, not a transition Mode B replay walks through.
- `KernelStateMachine.from_history()` reconstructs exactly one generation. It has no concept of "the next generation" and is not meant to.

None of this reconstructs the graph above. It detects that a graph like it might exist and refuses to guess at its shape.

---

## Why three phases

Mode B as originally stated is one large capability: segment, verify, and connect, all at once. Decomposed, it's three much smaller problems with a hard boundary between them — and, critically, **two of the three barely need new code at all.**

```
Phase 1: Segmentation      -- graph discovery, no replay
Phase 2: Independent verification -- existing replay engine, run per segment
Phase 3: Candidate lineage construction -- graph construction, no replay
```

The phases are ordered as a strict pipeline: Phase 2 consumes Phase 1's output and nothing else; Phase 3 consumes Phase 2's output and nothing else. Each phase has its own SHALL/SHALL NOT contract below, and each phase's contract assumes the previous phase's guarantees held — it does not re-derive them.

---

## Phase 1 — Generation segmentation

**Input:** a persisted audit log (and, implicitly, the decision log — both carry `generation_id`).

**Output:** an ordered list of segments, each a contiguous range of records sharing one `generation_id`.

```
Generation 1
Frames 1-84

Generation 2
Frames 85-141

Generation 3
Frames 142-...
```

**Nothing is replayed. Nothing is reconstructed.** This phase only discovers where the boundaries are — it is graph discovery over the existing `generation_id` field, not a new capability layered on top of replay.

### Phase 1 SHALL

- **SHALL derive segment boundaries purely from persisted `generation_id` values, in persisted sequence order.** A boundary is a point where consecutive records (ordered by `sequence_id` within a module) show a `generation_id` change. This is the same signal `kernel_state_replay.py` already checks for a single boundary — Phase 1 just checks for every boundary instead of stopping at the first.
- **SHALL reject a segmentation where a previously-seen `generation_id` reappears after a later, different `generation_id` was already witnessed.** This is not a valid single-lineage segmentation — it indicates either data corruption or multiple interleaved engine instances sharing one log (see `kernel_state_replay.py`'s own docstring, limitation 1). Phase 1 must flag this as unsegmentable, not silently produce a segmentation that ignores it.
- **SHALL produce output that is itself independently checkable** — each segment's record range, boundary positions, and `generation_id` should be inspectable without needing Phase 2 or Phase 3 to run first.

### Phase 1 SHALL NOT

- **SHALL NOT construct a `KernelStateMachine`, call `from_history()`, or perform any hash verification.** Phase 1 is a pure function over already-persisted `generation_id` values. If Phase 1's implementation ever needs to replay anything to determine where a segment ends, that's a sign Phase 1 and Phase 2 have been conflated again.
- **SHALL NOT infer anything about *why* a boundary exists.** That question belongs to Phase 3, not Phase 1 — see "the open question," resolved below.

---

## Phase 2 — Independent verification

**Input:** one segment from Phase 1's output.

**Output:** a `KernelReplayReport` for that segment (or equivalent), produced by running the *existing, unmodified* replay engine against it.

```
Replay(segment 1)
Replay(segment 2)
Replay(segment 3)
```

Each segment is, by Phase 1's own contract, single-generation — which is exactly what `kernel_state_replay.py` and `KernelStateMachine.from_history()` already handle. This is the phase that reuses almost everything already built.

### Phase 2 SHALL

- **SHALL verify each segment using `kernel_state_replay.py`'s existing `replay_and_verify_state_hashes()`, unmodified**, seeded via `KernelStateMachine.from_history()` with that segment's own `generation_id` — the same call shape A2 already proves works for a real single-generation history.
- **SHALL treat each segment's verification as fully independent of every other segment's.** Segment 2's replay must not be constructed using any state carried over from segment 1's replay (no shared `KernelStateMachine` instance, no shared audit log accumulator) — each is its own `from_history()` call.
- **SHALL preserve historical generation identity — never mint a new one.** This is `from_history()`'s existing guarantee (no `generation_id` parameter on `KernelStateMachine.__init__`, only on `from_history()`); Phase 2 must not introduce any path that bypasses it.

### Phase 2 SHALL NOT

- **SHALL NOT report a `generation_boundary_index` for any segment, if Phase 1 segmented correctly.** This is the load-bearing cross-check between the two phases, stated as a hard invariant:

  > **If Phase 1's segmentation is correct, every Phase 2 replay of a single segment must report `generation_boundary_index is None`.**
  >
  > If any segment's replay *does* report a boundary, that is proof Phase 1 either mis-segmented (a boundary it should have found and split on was missed) or the underlying data is more tangled than a clean single-lineage history (e.g. two generations' records interleaved by `sequence_id` rather than cleanly partitioned — which Phase 1's own SHALL clause above is supposed to catch and reject, so this would indicate Phase 1's rejection check itself has a gap). Either way, a boundary appearing inside a Phase-1-declared segment is a test failure for the *pipeline*, not a normal outcome to route around.

- **SHALL NOT attempt to verify anything across a segment boundary.** That is Phase 3's job. A Phase 2 implementation that quietly stitches segment *i* and segment *i+1* together to keep replaying has re-invented Mode B monolithically and defeated the point of the split.

---

## Phase 3 — Candidate lineage construction

**Input:** the ordered list of segments from Phase 1, each independently verified by Phase 2 (a `KernelReplayReport` with `fully_verified is True` and no reported boundary, per Phase 2's contract above).

**Output:** the candidate lineage graph — the best graph consistent with the evidence, constructed from verified islands. Deliberately not called "the connected lineage graph" or "the reconstructed lineage" — see the SHALL NOT clause below on why "candidate" and "constructed" are the correct verbs here, not "connect" or "prove."

```
Gen A
  |
  v
Gen B
  |
  v
Gen C
```

This is a graph-construction problem over already-verified segments, not a replay problem — Phase 3 never touches `KernelStateMachine` or any hash computation directly.

### Phase 3 SHALL

- **SHALL only include segments that Phase 2 independently verified in the candidate graph.** An unverified or partially-verified segment (per Phase 2's `fully_verified` flag) must not be silently included as if it were sound.
- **SHALL distinguish, in its output, "verified within a generation" from "included in the candidate graph."** These are different-strength claims — a segment being internally sound says nothing about whether the *edge* placing it next to another segment is sound. `KernelReplayReport`'s existing `generation_boundary_index` field already encodes exactly this kind of distinction for the single-boundary case; Phase 3's report needs the same honesty extended across however many edges it constructs.
- **SHALL make explicit, every time it constructs an edge, the assumption it is relying on and cannot independently verify: that adjacency in the persisted log means causal continuity of the same kernel instance.** See "the open question," below — this is an inherited limitation, not one Phase 3 introduces, but Phase 3 is the phase that actually *acts* on the assumption by placing an edge, so it is the phase whose output must carry the caveat forward rather than let it go silent.

### Phase 3 SHALL NOT

- **SHALL NOT claim full lineage verification on partial coverage.** If 3 of 4 discovered segments were independently verified and one was not, the report must say exactly that — not round up to "lineage reconstructed." This mirrors `PHOENIX_VERIFICATION_STATE.md`'s own standing rule: every claim is scoped to exactly what was checked.
- **SHALL NOT assert *why* a transition occurred as a proven fact.** Phase 3 may *note supporting evidence* (see below — a fault record immediately preceding a boundary is consistent with an administrative reset) but must report this as corroboration, not proof, and must not treat its absence as evidence of tampering (see below for why the absence case is genuinely ambiguous).
- **SHALL NOT describe its output as "connecting" or "the lineage," unqualified.** Phase 3 does not prove an edge between two segments is a genuine causal continuation of the same kernel instance — see the single-instance-continuity caveat below. It constructs the graph that best fits the evidence available, which is a narrower claim than "this is what happened." Output, documentation, and any future UI surfacing this graph should say "candidate lineage" or "inferred lineage," not "the lineage" or "reconstructed history," to keep this distinction visible to whoever reads the result, not just to whoever wrote this document.

---

## The open question — resolved (for now): do not add a new record type

**Resolution: defer.** Do not introduce a dedicated transition-logging record type at this stage. The reasoning below is sharper than "avoid scope creep," though that's also true.

**Why the current inference is sound enough to build on:**

```
Generation changes
       |
       v
persisted generation_id changes
       |
       v
boundary exists
```

This inference is deterministic, reproducible, and independently checkable without any new schema — exactly the property Phase 1 depends on. `generation_id` only ever changes via one code path (`FAULTED -> INITIALIZING` in `KernelStateMachine.transition_to()`), so a change in the persisted value is real evidence a boundary occurred.

**Why introducing a new record type now would be premature:** a `GenerationTransitionRecord` (or equivalent) means a new schema, new append logic, a new corruption-rejection test suite, a new persistence round-trip, a new entry in the cold-boot reconstruction contract, new append-ordering guarantees, new hashing — the same shape of work every existing record type in this codebase required (each of the three current logs has 9-15 dedicated tests). That is justified when a real question can't be answered without it. Nothing in Phases 1-3 above hits that wall: Phase 1 doesn't need it (segmentation is a pure function of existing `generation_id` values), Phase 2 doesn't need it (verification is per-segment, unaware of *why* the segment ended), and Phase 3 can note supporting evidence without it (below).

**Two caveats on the inference, surfaced by working through Phases 2 and 3 above, that weren't visible when the question was first raised:**

1. **A fault record is corroborating evidence for a reset, but its absence proves nothing.** Phase 3 can check whether the segment immediately preceding a boundary ends in an audit record with `success=False`, as support for "this boundary looks like an administrative reset following a real fault." But `deterministic_execution_engine.py`'s frame-integrity and sequence-violation fault paths trip `FAULTED` *before* an audit record is ever constructed for the triggering frame — so a reset caused by a corrupted or out-of-order frame leaves no audit record at all for the actual fault. Phase 3 SHALL treat a trailing fault record as supporting evidence when present, and SHALL NOT treat its absence as suspicious — the schema simply doesn't guarantee one exists for every real fault.

2. **The inference silently assumes single-instance continuity — an assumption Phase 3 inherits, not one it creates.** `kernel_state_replay.py`'s own docstring already names this limitation for the single-boundary case: nothing in the schema distinguishes *this generation is a reset-continuation of the same kernel instance* from *this generation is an unrelated kernel instance that happens to write to the same three log files*. Both paths mint `generation_id` via `uuid.uuid4()` — one via the reset branch, one via ordinary `KernelStateMachine.__init__()` — and nothing persisted distinguishes which code path produced a given value after the fact. Phase 3's candidate-graph construction is exactly where this matters: placing an edge between two segments asserts causal continuity that adjacency-in-the-log alone does not prove. This is why Phase 3's SHALL clauses above require every edge to carry this caveat forward explicitly, rather than Phase 3 presenting the graph as if continuity were already established.

**When to revisit:** if, after Phases 1-3 are built and in use, a real question surfaces that the current inference genuinely cannot answer — e.g., needing to distinguish a true reset-continuation from a coincidental fresh-instance collision, or needing an explicit trigger reason/actor for audit purposes beyond what a preceding fault record can corroborate — that is the signal to reopen this question, not before. Whether "why" belongs in the kernel layer or a higher-level administrative audit layer is a separate architectural decision to make at that point, not now.

---

## Explicitly out of scope for this document

- No code changes. `from_history()` remains single-generation, as built. `kernel_state_replay.py` remains stop-on-boundary, as built.
- No new record type — see resolution above.
- No claim that Phases 1-3 are close to buildable in sequence within any particular timeframe — this document defines what each phase would have to satisfy and how they compose, not a timeline or a line-by-line implementation sketch.
- `ExecutionPolicyDecision.decision_hash`'s continued generation-blindness (see `PHOENIX_VERIFICATION_STATE.md` Gap 1b) is a separate, orthogonal gap — none of Phases 1-3 touch it.

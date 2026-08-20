# ADVERSARIAL_METHODOLOGY.md

**Purpose:** formalize the attack pattern that found real gaps this session (Check 1's generation-blindness, Check 5's orphan gap) into a reusable methodology, so the next attacks are systematic rather than ad hoc. The governing question, stated precisely: not "what bugs are there," but **"if I were trying to make each claim false while making Phoenix say VERIFIED, what would I construct?"** That is a harder, more productive question than fuzzing — it starts from the claim's stated boundary and asks whether the boundary is exactly where the implementation actually draws it.

---

## The seven attack families

Each family is defined precisely enough to be distinguishable from its neighbors — several of these look similar at first glance and are not.

### 1. Orphan
**Question:** can an artifact exist without the relationship the model implies it should have?
The artifact itself is genuine and well-formed. What's missing is that no check ever verifies it connects to what the graph model says it should connect to. (`PG-001`/Check 5: a fabricated `PolicyDecisionRecord` with no corresponding `DecisionRecord`.)

### 2. Asymmetry
**Question:** is A checked against B, but B never checked against A?
**Relationship to Orphan, stated precisely so the two aren't treated as synonyms:** asymmetry is usually the *structural cause* of an orphan vulnerability, but they are not the same thing. An asymmetric check can exist without producing an exploitable orphan, if some other check happens to independently prevent the gap. And an orphan-shaped gap can exist without asymmetry, if a record type simply has no relationship checks in either direction. Check 5 closed both at once — Check 4 was asymmetric (`DecisionRecord → PolicyDecisionRecord` only), and that asymmetry was exactly what made the orphan possible.

### 3. Substitution
**Question:** can a valid artifact be moved into the wrong context?
Distinct from Orphan (the artifact here *is* connected to something — just the wrong something) and from Boundary Crossing (which is specifically about generation boundaries, not general context). Already has a real, closed example: `test_swapped_valid_policy_decision_records_are_caught` — two individually-valid `PolicyDecisionRecord`s, swapped between sequence_ids, each passing its own construction validation perfectly.

### 4. Omission
**Question:** can required evidence simply disappear while verification still reports success?
Distinct from Orphan: omission is about a *missing* piece whose absence goes unflagged, not an *extra* piece with no connection. Two sub-types, distinguished by whether the evidence *could* exist at all: **caller-level omission** (the evidence could exist — a real log — a caller simply didn't supply it; see the `CH-004`/`CH-006` finding below) versus **schema-level omission** (the evidence *cannot* exist for any caller, because no record type captures it; see `GAP-005` below). Caller-level is fixable by the caller; schema-level requires a schema change.

### 5. Duplication
**Question:** can the same evidence appear twice without detection?
See the CH-004/CH-006 finding below — a real, current instance.

### 6. Boundary crossing
**Question:** can evidence from generation A satisfy a check intended for generation B?
This is retroactively exactly what Check 1's original gap was, before this session's fix — see the calibration case study below.

### 7. Semantic inflation
**Question:** can a candidate/verified/integrity statement accidentally become a stronger claim than it warrants?
This is an attack on *interpretation*, not on data or code — it targets `MB-003`, `MB-004`, and `PG-001` specifically, the claims this project has been most careful to keep bounded. See the `MB-003` finding below.

---

## Calibration case study: the first real attack was unusually productive

Worth stating plainly rather than treating Check 5 as "one more fix": the first serious adversarial pass against `PROVENANCE_GRAPH_MODEL.md` found three things at once, not one —

- **An implementation gap** (Check 5 didn't exist; orphans were invisible).
- **An asymmetric verification path** (Check 4 only ever walked one direction).
- **An imprecision in the formal model itself** (the document's own edge-composition claim named a mechanism — "composing through `DecisionRecord`" — that didn't actually exist yet, since the reverse edge it depended on hadn't been built; see `PROVENANCE_GRAPH_MODEL.md`'s corrected text).

Classified against this taxonomy: Check 5's finding is **Orphan + Asymmetry** simultaneously (the asymmetry was the cause, the orphan was the exploitable consequence). Check 1's earlier finding, retroactively classified, is **Boundary Crossing** — a `DecisionRecord` from one generation and an `ExecutionAuditRecord` from another, sharing `(sequence_id, module_id)`, satisfying a check that assumed same-generation.

That two of seven attack families each found a real, previously-unknown, closeable gap on the *first* attempt is a genuinely strong signal the methodology works. It does not mean every future attempt will find something — the next attacks finding nothing would itself be useful evidence the surface is now sound. Both outcomes are informative; only one of them feels productive, which is worth resisting as a bias when reading the results below.

---

## Finding disposition loop

Every attack terminates in exactly one of these outcomes — this is the explicit version of what was, until now, an intuitive process:

```
ATTACK
  |
  v
Finding? --No--> record "survived"
  |
  Yes
  |
  v
Already covered by an existing Boundary statement? --Yes--> documentation confirmation
  |
  No
  |
  v
Is the claim itself too broad (should be narrowed)? --Yes--> narrow the claim
  |
  No
  |
  v
Implementation gap? --Yes--> fix + regression test
  |
  No
  |
  v
Formally document the limitation (it's real, correctly scoped, just previously unstated)
```

Retroactively checked against every finding below: Check 1 and Check 5 both terminated at "fix + regression." `HC-001` and `MB-003` both terminated at "formally document limitation" — a real, accurate limitation that was simply never written down. `CH-002` *originally* terminated at "documentation confirmation" — but that verdict was itself premature, corrected below. The loop's structure held; what failed once was an input to it, not the loop itself — see the correction to `CH-002` for what that means in practice.

**A "clean pass" needs its own caveat, learned the hard way:** "documentation confirmation" means the attacks *actually run* found nothing — it does not mean every relevant attack was tried. `CH-002` was marked clean after one attack (cross-module wall-clock interleaving) without Boundary Crossing ever being tried against it directly, despite `sequence_id` being exactly the kind of claim that family exists to test. The real gap was found by accident, through a different check's test. Going forward: before recording a clean verdict, check whether the claim's own subject matter points at an attack family that hasn't actually been run yet, not just whichever one was tried first.

## Attack result and disposition — two distinct axes (formalized 2026-08-08)

Retroactive restructuring, not a new methodology: every finding below already carries this information, just folded into a single shorthand (`found→fixed`, `found→documented`, `clean`, `found→logged`) that conflates two genuinely different questions. Separated explicitly:

**ATTACK RESULT** — what kind of thing the attack actually discovered:

```
ATTACK RESULT
├── survived
└── finding
     ├── implementation defect
     ├── schema limitation
     ├── epistemic limitation
     ├── claim-boundary / semantic-inflation issue
     └── insufficient evidence
```

**DISPOSITION** — what was decided to do about it:

```
DISPOSITION
├── fixed + regression
├── documented limitation
├── claim narrowed
├── logged / pending evidence
└── schema change deferred
```

**Precise definitions, to prevent the two `schema`-adjacent categories from re-blurring into each other:**

- **`schema limitation`** (attack result): the current persisted evidence model lacks the information needed to establish the claim. This does **not** imply the schema itself is defective or that it should change — `HC-001`'s optional `manifest_hash` is an intentional design choice that happens to produce this result; `GAP-005`'s missing lifecycle record type is a potentially useful future extension that also produces this result. Same attack-result category, two different reasons the evidence is missing.
- **`epistemic limitation`** (attack result): the current persisted evidence model cannot establish the claim, and — unlike `schema limitation` — no verifier-only change and no schema addition within the current architecture's terms can ever make it establishable, because the thing being inferred is, by construction, statistically independent of everything persisted (`MB-003`'s Theorem 2, `MB-004`/Asymmetry's Corollary). This is a stronger, formally-derived claim, not a synonym for "hasn't been built yet."
- **`documented limitation`** (disposition): applies to *both* `schema limitation` and `epistemic limitation` findings alike — the disposition doesn't need to re-encode which flavor it is, because the attack result already says so. A reader wanting to know *why* something is a documented limitation should look at its attack-result tag, not expect the disposition bucket to carry that distinction.
- **`schema change deferred`** (disposition): reserved for the specific case where a concrete, named schema addition (a new record type, a new persisted field) would resolve the finding, that addition is buildable in principle, and a decision has been made not to build it *yet*, pending real demonstrated need — distinct from `documented limitation`, which covers findings where no schema change was even proposed as a live option, or a general design tradeoff.

**Worked mappings, given as calibration examples:**
- `MB-003` → `finding: epistemic limitation` / `disposition: documented limitation`
- `MB-004`/Asymmetry (Twelfth finding) → `finding: epistemic limitation` / `disposition: documented limitation`
- `HC-001` (`manifest_hash` optionality) → `finding: schema limitation` / `disposition: documented limitation`
- `GAP-005` → `finding: schema limitation` / `disposition: schema change deferred`
- Check 1, Check 5, Check 6, Check 7, Check 2's fix, `MB-004`'s Substitution/Omission/Boundary-Crossing fixes → `finding: implementation defect` / `disposition: fixed + regression`
- `CH-004`/`CH-006`'s Duplication, `CH-001`'s Duplication → `finding: insufficient evidence` / `disposition: logged / pending evidence`
- `CH-001`'s Semantic Inflation, `MB-003`'s naming risk, `HC-001`'s compound dashboard-badge risk → `finding: claim-boundary / semantic-inflation issue` / `disposition: documented limitation`
- `MB-002`'s five sub-attacks, `MB-004`'s Orphan, `CH-001`'s Substitution → `attack result: survived` / `disposition: n/a` (nothing to dispose of when nothing was found)

**Scope of this restructuring:** classification only. No finding's prose, conclusion, or existing shorthand tag (`found→fixed` etc., still used in the campaign matrix below) is reinterpreted or changed by this section — each finding below now additionally carries its two-axis tag alongside its original disposition sentence, exactly as originally written.



## The meta-principle this methodology already proved about itself

**Claims, models, and implementations are all attack surfaces — not just implementations.** Check 5's finding wasn't only an implementation gap; `PROVENANCE_GRAPH_MODEL.md` itself named a composition mechanism ("composing through `DecisionRecord`") that didn't actually exist yet. The model was wrong, not just incomplete. That means this methodology has to periodically attack its *own* documents — `PROVENANCE_GRAPH_MODEL.md`, `MODE_B_CLAIMS_REGISTRY.md`, `VERIFICATION_COVERAGE_MATRIX.md`, and this file — the same way it attacks code, on the theory that a formal model describing a graph an adversary is meant to reason against is itself a claim that can be false.

The corollary for this document specifically: it must hold itself to the verification standard it's formalizing. `HC-003` staying flagged rather than resolved is not a gap in this methodology's output — it *is* the methodology's output, working correctly. A version of this document that speculated about `HC-003` to look more complete would itself be an instance of semantic inflation.

---

## First wave of applied attacks

Five claims, as raised. Verdicts vary deliberately — this is meant to show the methodology's actual output distribution, not a curated set of wins.

### HC-001 — real finding, not previously stated this precisely
**Attack:** can I change something that matters operationally but isn't included in `attempt_hash`?
`ModuleRegistrationAttemptRecord` persists `manifest_hash` — a *reference* to the declared manifest, not the manifest's content, and certainly not the actual loaded module code. Two structurally different module implementations that happen to declare identical capabilities and `runtime_api` version would produce the same `manifest_hash`, and `HC-001`'s tamper-evidence says nothing about which one actually ran. **This is the same "internal consistency, not external authenticity" boundary `REPLAY_GENERATION_MODEL.md`'s Theorem 1 already states for hash chains generally — but it had never been stated for `HC-001` specifically.** Not a bug; a boundary worth adding to `HC-001`'s row in `VERIFICATION_COVERAGE_MATRIX.md`. Disposition: formally document limitation. **[finding: schema limitation / disposition: documented limitation]**

### HC-003 — RESOLVED 2026-08-07 against real source, not guessed
**Attack:** are there semantically important fields excluded from `audit_hash`'s coverage?
Originally flagged, not guessed at — resolved once `execution_audit_contract.py` was actually read. **Result: no field is excluded.** `_compute_audit_hash()` hashes all 9 fields, confirmed directly (`generation_id` and `frame_timestamp_ns` both included, not assumed). Deterministic metrics specifically: `output_hash = result.module_hash`, and `ExecutionResult.module_hash` (`execution_module_contract.py`) already bakes in the filtered, sorted, deterministic subset of `metrics` before `ExecutionAuditRecord` ever sees it — covered transitively, via the same opaque-hash-reference pattern every field in this record uses, not by `ExecutionAuditRecord` inspecting metrics directly. The one real, now-precisely-grounded boundary: `__post_init__` validates `output_hash` is a well-formed 32-byte digest, never that it's the *correct* `module_hash` for a genuine `ExecutionResult` — internal consistency, not external authenticity, same as everywhere else in this hash chain. Disposition: documentation confirmation, refined with the verified mechanism (`VERIFICATION_COVERAGE_MATRIX.md` updated). **[attack result: survived (existing boundary refined, not newly discovered) / disposition: documented limitation]**

### CH-002 — SUPERSEDED 2026-08-07: the "clean pass" verdict was premature
**Original attack:** can I construct a history that is globally nonsensical while remaining locally ordered? Yes — two engines' records interleaved in one log file, each internally sequence-ordered, with `frame_timestamp_ns` values that contradict the interleaving. Check 2 doesn't catch this, but `CH-002`'s Boundary column already stated exactly that limitation, so this was recorded as documentation confirmation.

**That verdict was too narrow, not wrong on its own terms but incomplete.** `sequence_id` obviously interacts with generation boundaries — that's the whole axis Check 1's fix and Check 6 both operate on — and Boundary Crossing was never actually tried against `CH-002` specifically, even though it had just been used successfully against `CH-001`. The real gap (below) was found by accident, via a Check 6 test, not by this methodology's own deliberate coverage. **Worth recording honestly: a "clean pass" only means the attacks actually run found nothing — not that every relevant attack was tried.** The campaign matrix's empty cells are the backlog for exactly this reason; this is the first concrete case of a filled cell turning out to have been filled too early.

**Real finding, fixed:** `_check_sequence_ordering()` tracked `last_seen` keyed purely by `module_id`, with zero `generation_id` awareness — the identical class of gap Check 1 had before its own fix, but more severe in consequence: Check 1's gap needed a coincidental cross-generation collision to misfire; this one fired **unconditionally on every administrative reset**, since `sequence_id` legitimately resets to 0 each time. Any real multi-generation history for the same module — not an adversarial construction, ordinary healthy operation — would have been guaranteed a false "out of causal order" violation. Fixed by scoping the join key to `(module_id, generation_id)`, mirroring Check 1's and Check 6's shape. Two new regression tests: the exact false-positive scenario (`test_sequence_numbering_resetting_across_a_real_generation_boundary_is_not_flagged`) and a sanity check that genuine within-generation violations are still caught.

Disposition: fix + regression test. Reclassifies from "documentation confirmation" to "found→fixed," Boundary Crossing family. **[finding: implementation defect / disposition: fixed + regression]**

### MB-002 — clean pass across five sub-attacks
**Attack:** missing records, duplicate sequence_ids, empty segments, boundary records, malformed transitions — does segmentation accept any impossible pattern?
- *Missing records (a sequence_id gap within one segment):* accepted by `segment_by_generation()` — it never checks sequence continuity. **Correctly layered, not a gap**: Phase 2's replay enforces monotonic sequencing via the real `KernelStateMachine` (`test_non_monotonic_frame_execution_rejected`), so a genuine gap fails at Phase 2, not silently at Phase 1.
- *Duplicate sequence_id within one segment:* same answer — Phase 1 doesn't check it, Phase 2's replay does.
- *Empty segments:* structurally impossible by construction — `segment_by_generation()`'s algorithm never flushes an empty batch.
- *Boundary records (empty history, single-record history):* already tested directly (`test_empty_history_returns_empty_list`, `test_single_generation_returns_one_segment`).
- *Malformed `generation_id` (wrong length/type):* caught earlier, at `ExecutionAuditRecord`'s own construction validation — correctly out of Phase 1's scope.

No new findings. This is the "found nothing, and that's useful evidence" case the methodology predicted might happen — five sub-attacks, five confirmations that the layering between Phase 1 and Phase 2 is where it should be. Disposition: documentation confirmation (all five). **[attack result: survived (×5) / disposition: n/a]**

### MB-003 — real epistemic risk, semantic inflation family
**Attack:** can any implementation accidentally turn an unknowable relationship into a claimed one?
Not in current code — `CandidateLineageEdge.explanation()`'s wording is disciplined ("PLAUSIBLE, not proven"), and no aggregation or confidence-scoring exists to inflate. **But there is a real naming risk for future code built on top of this:** `SegmentVerificationResult.fully_verified` proves only within-segment continuity (Theorem 1). Nothing in that property's name warns a future integration — a dashboard, a report generator, an alerting layer — against reading "both adjacent segments are `fully_verified`" as implying the *boundary between them* is also verified, when `MB-003` explicitly says it structurally cannot be. This is the most realistic risk in the whole Mode B design: not that current code overclaims, but that a future caller could misread two true, narrow statements as implying a third, false, broader one. Preventive note added to `MODE_B_CLAIMS_REGISTRY.md`'s `MB-003` entry. Disposition: formally document limitation (done). **[finding: claim-boundary / semantic-inflation issue / disposition: documented limitation]** — note this specific finding is about the *naming risk*, distinct from `MB-003`'s own underlying `epistemic limitation` (Theorem 2 itself), which is `documented limitation` in its own right.

---

---

## Third finding: CH-003 has no time-window awareness, and the schema can't give it one — FROZEN 2026-08-07

**Attack (reclassified from Substitution to Omission — schema-level, see refinement below):** can a genuinely valid artifact — a real, successful `ModuleRegistrationAttemptRecord` — remain permanently sufficient evidence even after the situation it attests to has changed?

Verified directly against `_check_module_identity_cross_reference()`'s real source (2026-08-07): `successfully_registered_ids` is a flat set built from every `success=True` registration attempt, checked via pure set membership against `referenced_ids` from decision/audit records. No time-window, sequence, or generation correlation exists between a registration and the records that later cite it.

Tracing this to its actual root, not stopping at "no time check": `ModuleRegistrationAttemptRecord` only ever captures the *initial registration attempt*. Every subsequent lifecycle transition — activate, fault, retire — is tracked extensively in-memory (`module_lifecycle.py`, `module_registry.py`, well-tested: `test_faulted_module_cannot_be_resolved`, `test_retired_module_cannot_be_resolved`) but **none of it is ever persisted as its own record, anywhere in this codebase.** This is not an implementation gap in `CH-003` — the question "was this module active when this decision was made" is unanswerable from disk *at all*, for any check, because the schema has no record type capable of representing lifecycle state past the moment of registration.

**Reclassification, corrected on review:** originally called Substitution ("valid artifact moved into the wrong context"). That was too weak a fit — the registration record isn't moved anywhere or misused; it sits exactly where it belongs, permanently valid evidence of exactly what it attests to. What's actually missing is a *different record type* that was never created. That's Omission, not Substitution. But it's a meaningfully different severity of Omission than the `CH-004`/`CH-006` finding, worth naming as its own sub-type:
- **Caller-level omission** (`CH-004`/`CH-006`): the evidence *could* exist — a real policy decision log — a caller simply didn't supply it. Fixable by the caller, no schema change needed.
- **Schema-level omission** (`GAP-005`, this finding): the evidence *cannot* exist, for any caller, because no record type captures it. Fixable only by a schema change.

**Frozen classification (final, per this session's review):**
- `CH-003`: **VERIFIED**, within its stated scope — the check does exactly what it claims, correctly.
- `GAP-005`: module lifecycle state is not recoverable from persisted evidence.
- Status: **NOT YET BUILT** — buildable in principle (a new lifecycle-transition record type plus a correlating check), not an information-theoretic impossibility like `MB-003`/Theorem 2.
- Attack family: **Omission, schema-level sub-type.**
- No immediate schema change — the campaign's job is to map where the actual boundaries are, not to trigger a redesign every time one is found. Building `GAP-005` is a real, separate, scoped decision for later.

Disposition: formally document limitation (`GAP-005` added, both documents updated with the corrected classification), not fixed. **[finding: schema limitation / disposition: schema change deferred]** — the specific case a fifth disposition bucket exists for: a concrete, named schema addition (a lifecycle-transition record type) would resolve this, buildable in principle, deferred pending real demonstrated need rather than left as an undifferentiated "documented limitation."

---

## Fourth finding: CH-001's mirror image — fixed with Check 6

**Attack (Orphan + Asymmetry, CH-001):** if every `ExecutionAuditRecord` must have a corresponding `DecisionRecord`, can a `DecisionRecord` exist without the corresponding audit record? This was predicted before the attack ran: the same directionality pattern that made Check 5 productive against `CH-004` was applied deliberately to `CH-001`, on the theory that a high-information attack beats random test generation.

Traced directly against `deterministic_execution_engine.py`'s real `process_frame()` (2026-08-07), not guessed: `DecisionRecord` (`allowed=True`) is appended to the decision log **unconditionally**, before `module.execute()` is ever called. Any uncaught exception from `module.execute()` — a genuine module bug, or a deliberately hostile module — means the line constructing `ExecutionAuditRecord` never runs. The live kernel correctly transitions to `FAULTED` (`process_frame()`'s own catch-all `except Exception` handler), but nothing backfills an audit record for the frame that never completed. The allowed decision stays persisted, permanently, with no matching audit record — invisible to Checks 1 through 5, since Check 1 only ever iterates `audit_records` checking each has a matching decision, never the reverse.

**A real nuance, caught before it became a false-positive bug:** not every allowed-decision-with-no-audit is wrong. If `module.execute()` throws, there genuinely is nothing to build an audit record *from* — no `ExecutionResult` was ever returned. The *last* allowed decision for a `(module_id, generation_id)` having no audit record is the legitimate "execution crashed, nothing came after" case — directly mirroring `kernel_state_replay.py`'s own `KernelReplayReport.fully_verified` property, which already treats a history that legitimately ends at a fault as fully verified. What's actually wrong is a missing audit record *with later decisions or audits for the same module/generation proving execution continued past it* — that's demonstrably not a trailing crash.

**A second nuance, applying an earlier lesson to new code rather than repeating the mistake it came from:** the "last decision" computation is scoped per `(module_id, generation_id)`, not `module_id` alone — grouping by module only would wrongly flag a legitimate trailing-crash decision in one generation just because a *later* generation reused the same module successfully. That's the exact class of cross-generation conflation Check 1's original fix closed, and it would have been silently reintroduced here without this scoping.

**Fix:** Check 6 (`_check_decision_execution_completeness`) added to `causal_history_verifier.py`, always runs (not optional, unlike Checks 4/5 — it only needs the two always-available logs). Four new tests: the core mid-stream-gap attack (`test_mid_stream_decision_with_no_audit_is_caught`), the trailing-exemption clean case (`test_trailing_decision_with_no_audit_is_not_flagged`), the generation-scoping proof (`test_trailing_exemption_is_scoped_per_generation_not_globally` — the specific test designed to catch the bug this fix's own design was built to avoid), and a trivial single-decision sanity check.

Disposition: fix + regression test (matching Check 1 and Check 5's precedent — a real finding gets the same discipline as any bug, not deferred as future work because it came from a review pass). **[finding: implementation defect / disposition: fixed + regression]**

---

## Fifth finding: HC-001's authenticity gap can be total, not partial — verified against real source

**Attack (Substitution family, continuing HC-001's coverage):** the original `HC-001` finding established that `manifest_hash` is a *reference*, not the manifest's content — two different implementations declaring identical capabilities could collide on one hash. That finding assumed a `manifest_hash` exists to collide on. This attack checks a sharper question: does the binding have to exist at all?

Verified directly against `module_registration_audit.py` (2026-08-07, not inferred from test names): `manifest_hash: Optional[bytes] = None`, and `__post_init__` only validates the field's shape *if it is present* — there is no cross-check requiring `manifest_hash` when `success=True`. A registration attempt with `success=True` and `manifest_hash=None` is fully valid and passes every check this record type has. The source docstring confirms this is deliberate: *"not every caller will have a manifest hash on hand, and this field existing or not does not change the validity of the record."*

**What this means precisely:** a successful `ModuleRegistrationAttemptRecord` can carry **zero cryptographic reference to any manifest at all**. `CH-003` would still treat it as valid registration evidence for any later decision/audit record citing that `module_id` — with nothing, not even an imperfect hash, connecting the registration to what actually got loaded. This is a strictly stronger gap than the original finding: not "the binding could theoretically collide," but "the binding can be absent by design."

**What this does NOT mean:** `attempt_hash` itself is not weakened — `HC-001`'s core claim (tamper-evidence across every field) remains fully true even when `manifest_hash` is `None`; the absence is hashed as an explicit sentinel byte, same as every other optional-but-absent field in this codebase's pattern. This is a completeness boundary on what the record can attest to, not a defect in what it does attest to.

**Not proposed as a fix.** The source docstring states this is deliberate, not an oversight — making `manifest_hash` required would be a real behavior change contradicting an explicit design decision, and I don't know how many real callers rely on being able to omit it. Matches `HC-001`'s original disposition: formally document limitation, not fix.

**Compound semantic-inflation risk, worth naming alongside `GAP-005`:** a future dashboard or report showing "module X: registration verified" could easily be read as "module X's identity is cryptographically confirmed" — when in fact (a) the registration may carry no manifest binding at all, per this finding, and (b) even a well-formed registration says nothing about whether the module was later retired or faulted, per `GAP-005`. Two narrow, individually-accurate claims compounding into a false broad one is exactly the shape `MB-003`'s semantic-inflation warning was written to prevent — the same discipline applies here.

Disposition: formally document limitation (`VERIFICATION_COVERAGE_MATRIX.md`'s `HC-001` row updated with the precise mechanism; the original matrix row had never actually been updated with the first `HC-001` finding either, corrected in the same pass). **[finding: schema limitation / disposition: documented limitation]** — an intentional design choice (source docstring confirms deliberate), not a buildable-but-unbuilt gap, so `schema change deferred` does not apply here the way it does for `GAP-005`.

---

## Sixth finding: MB-004 never verified its own most basic precondition (Substitution family)

**Attack (highest-information empty cell in the campaign matrix, selected deliberately):** `MB-004` had zero attempted families before this — flagged by the GPT dispatch as high-value and confirmed by inspection to be genuinely untested, unlike every other row with at least one attempt. Applying the directionality lesson that made `CH-006` and `CH-007` productive (2/2 hit rate this session): does `construct_candidate_lineage()` verify every precondition it depends on, the same way it verifies the one it already defends?

Verified directly against `candidate_lineage_construction.py`'s real source (2026-08-08): the function raises `ValueError` if `segments` and `verification_results` have mismatched lengths — a defended precondition. But it never checked a comparably load-bearing one: that adjacent entries in `segments` actually represent *different* generations. `generation_segmentation.py`'s `segment_by_generation()` structurally guarantees this for real Phase 1 output — that's what makes two list entries separate segments in the first place — but `construct_candidate_lineage()` itself never re-verified it, trusting the caller completely on this one specific point while explicitly not trusting them on the length point.

**Concrete construction:** two genuinely valid, independently-verified segments (both real, correctly hash-chained, both `fully_verified=True`) that happen to share one `generation_id`, assembled as adjacent list entries — bypassing `segment_by_generation()` entirely. Before the fix, this silently produced a `CandidateLineageEdge` with `from_generation_id == to_generation_id`: not a data-integrity failure (nothing here is tampered with), but a "boundary" that doesn't represent any real generation transition at all, presented via `.explanation()` exactly as if it were a genuine candidate transition.

**Disposition, following the `PG-001` precedent directly:** this is adversarial-fabrication-only — Phase 1 itself can never produce this input in the normal pipeline. That was true of the original `PG-001` orphan finding too, and this project's standing answer is the same one given there: an adversarial-only finding still gets fixed with the same discipline as an operational bug, not merely documented, because "not currently exploitable through the normal pipeline" and "not exploitable at all" are different claims, and this function is a public API a caller could call directly. Fixed with a `raise`, matching the existing length-check's own pattern exactly. New regression test: `test_adjacent_segments_sharing_a_generation_id_raise_value_error`, built from two real engine runs (not fabricated data), confirming the malformed pair is rejected outright. **[finding: implementation defect / disposition: fixed + regression]**

---

## Seventh finding: CH-001's Omission surface — a contradictory decision pair goes unweighed

**Attack (Omission family, deliberately targeting CH-001's remaining blank cell):** `CH-001` had Boundary Crossing and Orphan/Asymmetry both attacked and fixed already; Omission was the one family left untried, and the claim's own subject matter — "every audit has a corresponding decision" — points directly at it: what evidence required for that relationship can disappear while the verifier still passes?

Traced against `_check_decision_ancestry()`'s real source: the match condition is `if key in denied_keys and key not in allowed_keys` for the denied-only case, falling through to `elif key not in allowed_keys` otherwise. **A key present in *both* `allowed_keys` and `denied_keys` simultaneously satisfies neither branch** — the first requires the key's *absence* from `allowed_keys`, the second requires the same. The audit is silently accepted as validly matched. The denial evidence doesn't get weighed against the allowed decision; it disappears from consideration the instant any allowed decision exists at that key, regardless of a contradictory denial sitting right next to it.

**Why this is a real, not merely theoretical, gap:** in normal operation, exactly one decision is ever made per frame — a key can never legitimately appear in both sets. The only ways to produce this state are a genuine data-integrity failure or deliberate fabrication: append one fake `allowed=True` `DecisionRecord` at the same key as a real denied one, and the entire verifier treats the frame as legitimately authorized, with the denial silently omitted. Exactly the kind of "laundering" attack this project's whole verification apparatus exists to prevent.

**Fix:** Check 7 (`_check_no_contradictory_decisions`) added, always runs (needs only `decision_records`, no optionality). Validates `decision_records`' own internal consistency directly — independent of whether any audit even references the contradictory key, catching the fabrication at its source rather than only its downstream effect on Check 1. Two regression tests: the core attack (contradictory pair, no audits needed at all, since this is purely a decision-log integrity concern) and a false-positive check confirming a denial and a later allowance at *different* sequence_ids — ordinary, legitimate history — is not flagged.

Disposition: fix + regression test, same discipline as every other real finding this campaign has produced. **[finding: implementation defect / disposition: fixed + regression]**

---

## Eighth finding: CH-001's remaining three cells, all traced to one structural fact

**Context:** `CH-001` had Orphan, Asymmetry, Omission, and Boundary Crossing already attacked and fixed. The three remaining cells — Substitution, Duplication, Semantic Inflation — turn out to share a single root cause, confirmed directly against both record types' real field lists: `DecisionRecord` and `ExecutionAuditRecord` share **no fields beyond the three-part join key itself** (`sequence_id`, `module_id`, `generation_id`). `decision_hash` (`DecisionRecord`-only) refers to the *policy* decision, not the frame; `input_hash`/`output_hash`/`success`/`frame_timestamp_ns`/`error_message` (`ExecutionAuditRecord`-only) have no counterpart on the decision side. Check 1's matching logic is therefore pure key co-occurrence — it was never designed to, and cannot, cross-validate any content between the two records.

### Substitution — clean, and structurally so, not incidentally

**Attack:** can a genuinely valid `DecisionRecord` be relied upon by the wrong audit?

There is nothing to substitute. Substitution requires shared content that could be swapped between two contexts — `CH-004`'s swap attack worked because `decision_hash` is genuinely shared, checkable content between `DecisionRecord` and `PolicyDecisionRecord`. `CH-001` has no analogous shared content at all beyond the key itself, so there is no vector for this family to exploit. Worth recording as a structural clean pass, not a "nothing found, move on" — a future reader shouldn't need to re-derive why this family doesn't apply here.

### Duplication — real, same shape as the CH-004/CH-006 finding, a new instance

**Attack:** can two `ExecutionAuditRecord`s exist at the identical `(sequence_id, module_id, generation_id)` key, both silently accepted?

Yes. Check 1's loop iterates `audit_records` independently, checking each one's key membership in `allowed_keys` with no tracking across iterations — two audits sharing a key would each pass individually. **Check 6 doesn't catch this either**: `_check_decision_execution_completeness()`'s `audit_keys` is also a *set* comprehension, so it only ever asks "does at least one audit exist at this key," identical `>= 1` semantics to Check 1. A duplicated, byte-identical `ExecutionAuditRecord` is invisible to both checks that touch this relationship.

Investigated the same way as `CH-004`/`CH-006`'s Duplication finding, because it's the same append path: no retry logic exists anywhere in the code actually available (`execution_audit_log.py`, `deterministic_execution_engine.py` — confirmed earlier this session, the production persistence call site itself isn't in this sandbox). Same honest limit applies: cannot rule out an unseen external caller retrying, but no legitimate retry mechanism was found. Logged, not built — same disposition as its sibling finding, for the same reason. **[finding: insufficient evidence / disposition: logged / pending evidence]**

### Semantic inflation — real, and it's the direct consequence of the Substitution finding's cause

**Attack:** can "`CH-001` VERIFIED" be read as a stronger claim than it makes?

Yes, precisely because of the structural fact above: `CH-001` proves a `DecisionRecord` and an `ExecutionAuditRecord` share a key — it does **not** and structurally *cannot* prove the decision's authorization has anything to do with the audit's actual content, since `DecisionRecord` carries none. A future integrator reading "decision ancestry verified" could easily infer "this specific execution's inputs and outputs were authorized," when the honest claim is only "an allowed decision object existed for this attempt identifier." This is worth a documented warning for the same reason `MB-003` and the `HC-001`/`GAP-005` compound risk got one — not a defect in the check, a defect in how its result could be narrated.

### Disposition summary

Substitution: documentation confirmation (structural, not incidental). **[attack result: survived (structural clean pass) / disposition: n/a]** Duplication: logged, not built (same reasoning as `CH-004`/`CH-006`'s sibling finding). **[finding: insufficient evidence / disposition: logged / pending evidence]** Semantic inflation: formally document limitation. **[finding: claim-boundary / semantic-inflation issue / disposition: documented limitation]** No code changes this turn — `CH-001` is now the most thoroughly attacked claim in the campaign, 7 of 7 families attempted, four real fixes, one structural clean pass, two documented limitations.

---

## Ninth finding: MB-004's second attack, Omission — a cross-check that never existed

**Attack (continuing MB-004's campaign, Omission family, per the reasoning "what evidence can disappear between verified segments and candidate edge while the constructor still produces an apparently valid edge"):** `construct_candidate_lineage(segments, verification_results)` takes two separate parameters. Does anything verify `verification_results[i]` actually describes `segments[i]`?

First hypothesis, checked against real source and ruled out before building anything: could a hand-constructed, zero-record `GenerationSegment` reach edge construction, given `replay_and_verify_state_hashes(())` is confirmed (via `test_empty_history_is_trivially_fully_verified`) to report `fully_verified=True` for empty input? No — `GenerationSegment.sequence_id_range` does `self.records[0].sequence_id`, which `IndexError`s on an empty segment, so `verify_segments()` itself crashes before `construct_candidate_lineage()` is ever reached. Ruling this out is worth recording, not silently discarding — it's what redirected the investigation to the real finding.

**The real finding, tracing exactly which fields the function reads from which parameter:** `current_segment, current_result = segments[i], verification_results[i]` — but only `current_result.generation_id` and `current_result.fully_verified` feed edge construction; `segments[i].generation_id` is read *nowhere*. Meanwhile `_last_record_is_fault(current_segment)` reads `segments[i]`'s actual records directly. **Nothing ever cross-checks that these two came from the same place.** A caller supplying `segments_a` (genuinely real, generation A's actual records) paired with `results_b` (genuinely real, generation B's actual, valid `verify_segments()` output) — each individually completely legitimate — gets an edge whose reported identity comes from generation B while its supporting fault-evidence comes from generation A's real last record. Two uncorrelated pieces of data presented as one coherent artifact.

**Fix:** an upfront validation loop, checked for every index before any edge construction begins — `segments[i].generation_id != verification_results[i].generation_id` raises immediately, matching the existing length-check's and same-generation-check's own pattern. New regression test built entirely from real objects (two real generations, each independently run through `verify_segments()`), swapped in the call — no hand-constructed data anywhere, the violation is purely in the pairing.

Disposition: fix + regression, same `PG-001` precedent as the first MB-004 finding — adversarial-fabrication-only (Phase 1's own pipeline always pairs correctly by construction), still fixed rather than merely documented, since this is a public API a caller could invoke directly. **[finding: implementation defect / disposition: fixed + regression]**

---

## Tenth finding: MB-004's third attack, Boundary Crossing — root cause one layer upstream, in Phase 2

**Attack (continuing MB-004's campaign, explicitly scoped to Boundary Crossing only, per instruction not to expand into `VP-001`):** two fixes already exist for mismatches between a segment and *something else* (adjacent segments' generation identity, and segment/result pairing). The remaining question specific to Boundary Crossing: can evidence genuinely belonging to one generation be presented, and accepted, as belonging to a different one — not through mismatched pairing, but through the segment's own label simply not matching its own content?

Traced through all three layers of the pipeline before asserting anything. `GenerationSegment` (`generation_segmentation.py`): a plain frozen dataclass, no `__post_init__`, no validation that `records` share `generation_id` — confirmed directly against source. `replay_and_verify_state_hashes()` (`kernel_state_replay_updated.py`): seeds its own reference `generation_id` from `execution_history[0].generation_id` — the records' *own* data — and checks every subsequent record against *that*, but the function signature has no parameter at all for an externally-claimed label to cross-check against. `verify_segments()` (`generation_segment_verification.py`): calls the verifier with only `segment.records`, then separately, unconditionally builds `SegmentVerificationResult(generation_id=segment.generation_id, ...)` — trusting the label completely, never comparing it to what the records themselves, and Phase 2's own internal replay, actually derived.

**The gap this leaves:** a `GenerationSegment` whose `records` are entirely, internally consistent — all genuinely generation B, correctly hash-chained, nothing mixed or corrupted — but whose external `generation_id` label falsely claims A. The replay succeeds honestly on B's real data; `fully_verified=True` is a completely accurate statement about the records. But `SegmentVerificationResult.generation_id` reports A. `unexpectedly_crosses_generation_boundary` stays `False` throughout, since nothing about the replay itself was inconsistent — this is invisible to the *existing* mixed-generation test (`test_segment_spanning_two_real_generations_is_flagged_not_silently_passed`), which covers a different failure shape entirely: there, the first record correctly matches the label and a later one diverges mid-stream, caught by the boundary check inside the replay loop. Here, every record agrees with every other record — just not with the label sitting outside all of them.

**Why this matters for MB-004 specifically, even though the fix landed in Phase 2:** `construct_candidate_lineage()`'s two existing guards both operate on `verification_results[i].generation_id` — and a mislabeled segment reaching Phase 3 would have sailed past *both* of them, since the label would be internally self-consistent by the time Phase 3 ever sees it. The two Phase 3 fixes protect against a caller mismatching parameters; this fix protects against the data itself being wrong before either parameter is even constructed. Root cause traced one layer upstream rather than patched at the symptom.

**Fix:** `verify_segments()` now checks `segment.generation_id != segment.records[0].generation_id` (when `records` is non-empty) before calling the verifier, raising immediately — matching the same pattern as every other precondition guard added this campaign. New regression test built from one real engine run (genuinely, consistently generation B) deliberately mislabeled as A — not fabricated data, just a false label on real content.

Disposition: fix + regression, same `PG-001` precedent. Campaign scope respected: `VP-001` not touched this turn, per instruction. **[finding: implementation defect / disposition: fixed + regression]**

---

## Eleventh finding: MB-004's fourth attack, Orphan — clean, and precisely because of prior work, not by accident

**Attack (Orphan family, scoped to `MB-004` only per instruction — no expansion into `VP-001`):** can a `CandidateLineageEdge` exist in `graph.edges` referencing a generation not actually present in `graph.verified_segments` — a valid-looking artifact never genuinely connected into the graph, the same shape as the original Check 5/`PG-001` finding?

Traced rather than assumed clean. Three checks, in order:

1. **Can an edge reference a generation absent from the inventory?** No — `edges` and `verified_segments` are both derived from the exact same `verification_results` list (`verified_results = [r for r in verification_results if r.fully_verified]`, and edges only ever built between adjacent pairs both satisfying that same `fully_verified` condition). An edge's endpoints are structurally guaranteed to appear in the inventory it's drawn from.

2. **Can a self-referential orphan edge form (an edge claiming a transition that never happened)?** This was possible before this session's earlier fix — the same-generation-adjacency guard (Substitution family) closes exactly this: an edge with `from_generation_id == to_generation_id` no longer forms at all.

3. **Can `excluded_segments` contain a "ghost" entry — a result mismatched from the segment it's paired with?** This was also possible before the Omission fix, which validates `segment.generation_id == result.generation_id` for *every* index, not only ones adjacent to an edge — so entries destined for `excluded_segments` are covered by the same guarantee as ones destined for `verified_segments`.

**A fourth angle checked explicitly, since it's the one place this session hadn't yet verified precisely:** does `fully_verified` correctly go `False` if a segment's *internal* records diverge in generation anywhere past the first — not just mid-stream, but even at the very last record? Confirmed against `kernel_state_replay_updated.py`: `fully_verified` requires `verified_count == total_records`, and any internal mismatch breaks the replay loop early, leaving `verified_count < total_records` regardless of *where* the mismatch falls. A segment with an internally inconsistent tail is excluded before it can reach Phase 3 at all — the pre-existing mixed-generation detection, untouched by any fix this session, already covers this.

**Named honestly rather than glossed over:** `verified_segments` can legitimately contain an isolated entry — a verified segment surrounded by excluded neighbors, with no edge touching it at all. Checked against the field's own documented contract before treating this as a finding: it's declared as an inventory of everything Phase 2 verified, never a claim of connectivity — `edges` is the separate field for that. An isolated entry isn't missing an implied relationship the field never made.

**Why this is a meaningful clean pass, not a shrug:** three independent mechanisms close this off, and only one of them (the pre-existing mixed-generation detection) predates this session's work — the other two (same-generation-adjacency, segment/result cross-check) were built for *different* attack families (Substitution and Omission respectively) and happen to jointly close Orphan as a side effect. Worth recording precisely, matching the `CH-002` lesson: a clean verdict is only as good as what was actually checked against it, and this one traces to three named, verified mechanisms rather than an absence of trying.

Disposition: documentation confirmation. No code changes this turn. **[attack result: survived (three mechanisms traced, not asserted) / disposition: n/a]**

---

## Twelfth finding: MB-004's fifth attack, Asymmetry — a formally documented limitation, not a fix

**Attack (Asymmetry family, per the structural hint surfaced during the Orphan pass):** `segments` and `verification_results` are consumed as two correlated lists throughout Phase 3. Is there a directional relationship this function or its neighbors rely on where only one direction is actually checked?

**Candidate 1, traced and ruled out:** the edge loop reads `segments[i]` (for `_last_record_is_fault()`) and `verification_results[i+1]` (for the "next" side of the edge) but never `segments[i+1]` directly — syntactically asymmetric on its face. Traced against the existing upfront per-index validation loop (built for the Ninth finding, Omission): it already establishes `segments[j].generation_id == verification_results[j].generation_id` for *every* index `j`, including `i+1`, before the edge loop ever runs. By the time the edge loop reaches index `i`, the apparently-missing `segments[i+1]` relationship has already been established indirectly. No exploitable degree of freedom remains — worth recording as a traced, ruled-out asymmetry rather than silently passed over, matching the `CH-002` lesson: syntactic asymmetry is not automatically exploitable asymmetry. **[attack result: survived (traced, not asserted) / disposition: n/a]**

**Candidate 2, the real attack:** `construct_candidate_lineage()` treats list *position* as chronological succession, with nothing verifying it. Constructed two genuinely independent, individually fully-verified real generations — A executed first, B executed second, each run through the real engine and `verify_segments()` separately — then handed to `construct_candidate_lineage()` in reversed order: `segments=[segments_b[0], segments_a[0]]`, `results=[results_b[0], results_a[0]]`. This construction preserves every guard the function already has: lengths match, each segment matches its own paired result, adjacent generation_ids differ, both individually `fully_verified`. Confirmed via `pytest -v` (`PASSED`): the function returns a single edge, `from_generation_id=_GEN_B, to_generation_id=_GEN_A` — the reverse of what actually happened.

**Evidence investigation — why this is not "add a check":** the only per-record field that varies with real time, `frame_timestamp_ns`, was traced to `CoreExecutionFrame.create()` (`execution_kernel_contract.py`): caller-supplied, with zero validation anywhere (`__post_init__` and `verify_integrity()` check payload shape, hash type, and hash match — nothing about `timestamp_ns`). The subsequent hash chain makes a persisted value **tamper-evident**, never **authentic** — it proves "this value was part of this artifact when created," not "this value reflects when the frame actually occurred." Using it as even corroboration-only, matching `fault_record_precedes_boundary`'s "consistent with, not proof of" pattern, would manufacture evidentiary weight that doesn't exist — the same semantic-inflation risk already named for `MB-003` and `HC-001`.

**Formal result:** this traces to the same root cause as `MB-003`'s own Theorem 2 — the Generation Identity Independence Principle, extended from identity-continuity to chronological ordering. `generation_id`, and everything derivable only from records sharing it, is minted (via `uuid.uuid4()` at reset) with zero dependence on anything prior — so nothing persisted carries a signal correlating one generation's segment to another's real-time position. Formalized as a new **Corollary to Theorem 2** in `REPLAY_GENERATION_MODEL.md`, alongside Theorem 2 itself: cross-generation chronological ordering is, like identity continuity, unprovable under the current persisted evidence model — not a missing check, an absence of any persisted field carrying the needed signal at all.

**Deliberately no defensive raise added.** Rejecting some orderings (e.g. by list-position parity, or any other heuristic) would reject one malformed call shape without ever establishing which ordering is actually correct — replacing an honest "cannot determine" with a false "corrected." The regression test (`test_reversed_generation_segments_produce_reverse_candidate_edge`, renamed from an exploratory probe) is kept permanently, with its docstring stating explicitly that this is intentional characterization of a documented epistemic limitation, not a defect for a future developer to casually "fix."

**Unprovable is not the same as unimportant.** The Corollary in `REPLAY_GENERATION_MODEL.md` distinguishes the input contract (`segments` MUST be supplied in true historical order — the entire graph's meaning depends on it) from the verification claim (Phoenix cannot independently confirm that contract was honored). This finding is a gap in the latter, not evidence the former doesn't matter — a caller violating the contract gets a silently backwards graph, not a loud failure.

Disposition: **found → formally documented limitation** — the first `MB-004` finding of this kind; Substitution, Omission, and Boundary Crossing were all found→fixed. Same category as `MB-003` itself: refusing to manufacture a verification claim the evidence cannot support is, per this methodology's own disposition loop, exactly as valid an outcome as a fix. **[finding: epistemic limitation / disposition: documented limitation]**

---

## Thirteenth finding: MB-004's sixth attack, Duplication — adjacent-only guard bypassed by a non-adjacent repeat

**Attack (Duplication family, per the matrix's highest-semantic-applicability filter):** `construct_candidate_lineage()`'s existing same-generation-id guard, added for the Sixth finding's Substitution attack, only ever compares `segments[i]` against `segments[i+1]` — genuinely adjacent pairs. Nothing checks global uniqueness of `generation_id` across the whole list. `generation_segmentation.py`'s `segment_by_generation()` (Phase 1) enforces a *stronger* invariant: `UnsegmentableHistoryError` fires the instant any `generation_id` reappears anywhere after a later, different one was witnessed — adjacent or not. This asymmetry between Phase 1's global guarantee and Phase 3's local-only check is the concrete attack surface.

**Construction, confirmed rather than assumed:** three genuinely independent, individually real, individually fully-verified segments — `_run_real_generation(_GEN_A)`, `_run_real_generation(_GEN_B)`, `_run_real_generation(_GEN_A)` again — hand-assembled as `segments = [A_first, B, A_second]`, bypassing `segment_by_generation()` entirely (which could never produce this shape from one real history). No adjacent pair shares a `generation_id` (A≠B, B≠A), so the existing guard never fires. Confirmed via `pytest -v -s` before the fix: produced exactly the predicted result — two edges (`A→B` and `B→A`) and a `verified_segments` tuple containing generation A twice, a candidate graph asserting the kernel returned to a generation it had already left.

**Fix:** replaced the adjacent-only comparison with a single global-uniqueness pass (a `seen_generation_ids` set, checked and populated once per `verification_results` entry, before any edge construction begins) — this *subsumes* the original adjacent-only check rather than sitting alongside it, so the fix simplifies the function's structure slightly rather than only adding to it. Error message deliberately preserves the substring `"same generation_id"` so the existing `test_adjacent_segments_sharing_a_generation_id_raise_value_error` (from the Sixth finding) continues to pass unchanged against the new, earlier-firing check — no test churn for a change that doesn't alter that test's own behavioral contract. New regression test: `test_nonadjacent_duplicate_generation_id_raises_value_error`, built from three real engine runs (not fabricated data), confirming the non-adjacent duplicate is now rejected.

Disposition: fix + regression, same `PG-001` precedent as every other `MB-004` implementation-defect finding — adversarial-fabrication-only (Phase 1 itself could never produce this input), still fixed rather than merely documented, since this is a public API a caller could misuse directly. **[finding: implementation defect / disposition: fixed + regression]**

`MB-004` now 6 of 7 families attempted: Substitution/Omission/Boundary-Crossing/Duplication all found→fixed, Orphan clean, Asymmetry found→documented. Only Semantic Inflation remains untried.

---

## Fourteenth finding: MB-004's seventh attack, Semantic Inflation — the module warns against one false inference but not its structural twin

**Attack, framed around consumer-facing meaning rather than malformed input (a deliberate departure from the other six families in this campaign, which all probed whether the constructor accepts invalid data):** can a downstream consumer take individually valid `fully_verified=True` segments and infer something stronger than `MB-001` actually establishes? The registry itself already states the precise danger in two parts — `fully_verified(A) ∧ fully_verified(B)` does not entail `A genuinely continued into B` (`MB-003`), and, per this session's own Corollary to Theorem 2, does not entail `A chronologically preceded B` either. The question: does the module's own representation or API make either stronger interpretation easy or implicit?

**Traced against three checkpoints, each against real source, not assumed:**

1. **`fully_verified` → within-segment only.** `SegmentVerificationResult.fully_verified` is a direct passthrough of `KernelReplayReport.fully_verified` (Phase 2's replay result) — nothing in `candidate_lineage_construction.py` recomputes or reinterprets it. Clean.
2. **Candidate edge → `continuity_caveat` always present.** Computed as an unconditional `@property` on `CandidateLineageEdge`, not something a caller could omit populating, and available even to a consumer who reads `edge.from_generation_id`/`edge.to_generation_id` directly without ever calling `explanation()`. A consumer can still choose to ignore the field — but that's a limit no type design can prevent without becoming radically restrictive; the relevant question is whether the API *silently encourages* the false interpretation, and it doesn't. Not a defect.
3. **Ordering → the real finding.** `CandidateLineageGraph`'s docstring says only "in Phase 1's original order" — the single mention of ordering in the entire module. The module's top-level docstring has a dedicated, thorough section — "WHAT AN EDGE ACTUALLY ASSERTS" — warning against the identity-continuity misreading (`MB-003`). It said **nothing** about the structurally identical, now-equally-unprovable ordering misreading (this session's own Corollary to Theorem 2). A developer reading only this module's documentation would get strong warning against one false inference and zero warning against its twin, even though both now rest on the exact same formal footing.

**Why this counts as semantic inflation and not mere incompleteness:** a caller seeing `A → B` and "in Phase 1's original order" could reasonably infer the system has *established* A occurred before B. It hasn't — the graph asserts "given the supplied Phase 1 ordering, this is the candidate relationship," a materially weaker claim. Preserving an order is not the same as proving that order; constructing `A → B` is not the same as proving A preceded B. That distinction was previously implicit at best.

**Fix:** documentation only, no behavior change. Added a new module-docstring section, "ORDERING IS NOT INDEPENDENTLY ESTABLISHED EITHER," placed immediately after "WHAT AN EDGE ACTUALLY ASSERTS" (parallel weight, parallel placement — not an appendix). Uses the theorem's own strength of claim rather than a weaker hedge: *"the persisted evidence does NOT independently establish chronological ordering,"* not "ordering is not guaranteed" — the latter reads as ordinary uncertainty, understating a proven epistemic limit. Explicitly states why no defensive raise accompanies this (rejecting some orderings without knowing which is correct would replace an honest "cannot determine" with a false "corrected," same reasoning as the Twelfth finding) and cross-references `test_reversed_generation_segments_produce_reverse_candidate_edge` as the executable demonstration.

Disposition: **found → documented limitation**, no code behavior change, no new test — matching this campaign's own precedent for pure-documentation findings (the Eleventh finding, `MB-003`'s own registry semantic-inflation note). **[finding: claim-boundary / semantic-inflation issue / disposition: documented limitation]**

`MB-004` now 7 of 7 attack families attempted — the first claim in this campaign to reach full family coverage. Final shape: Substitution/Omission/Boundary-Crossing/Duplication found→fixed (4), Orphan clean (1), Asymmetry and Semantic Inflation found→documented (2).

---

## VP-001: latent exhaustiveness in `historical_verification.py`'s dispatch — a distinct finding class, not an eighth attack family

**This does not belong to the seven-family taxonomy above, and is deliberately not numbered into that sequence.** Every finding in this campaign so far — `MB-004`'s seven, `CH-001`'s seven, all the rest — was reachable by a real caller supplying genuine-but-adversarial Python objects through a public API today. This finding is different in kind: `SchemaRecognition` is a closed three-member `Enum`, and nothing external can synthesize a fourth member at runtime. The risk this finding names is **future code evolution**, not adversarial input against the system as it exists right now.

**How it was found:** picked as the next target after `MB-004` reached full coverage, using the same "highest-information cell" filter established mid-campaign — `VP-001`'s own claim (`historical_verification.py`, per `VERIFICATION_COVERAGE_MATRIX.md`) is a partition claim: "a single record resolves deterministically to **exactly one** of four outcomes." That phrasing points directly at Duplication (could two outcomes fire at once?) and Omission (could zero outcomes fire, or an uncaught exception instead?) as the two families with the strongest semantic fit, before any code was even read.

**Duplication, traced and ruled out structurally, not just empirically:** both `verify_decision_record_line()` and `verify_execution_audit_record_line()` are built entirely from early `return`s — exactly one `HistoricalVerificationResult` construction can ever execute per call, by the shape of the control flow itself. No attack construction needed; this is foreclosed at the source level.

**Omission, the real finding:** both functions reach their `CURRENT_SCHEMA` verification branch by elimination, not confirmation — explicit `if` checks rule out `RECOGNIZED_HISTORICAL_SCHEMA` and `UNRECOGNIZED`, then a comment (`"# CURRENT_SCHEMA: the only branch..."`) asserts, without a corresponding check, that anything remaining must be `CURRENT_SCHEMA`. Confirmed against `SchemaRecognition`'s actual definition (`historical_schema_recognition.py`): exactly three members today, and `_classify()` — the only function that ever constructs a `SchemaClassification` — is genuinely exhaustive over those three, so the assumption is correct as of this writing. But it is an invariant `historical_verification.py` relies on without establishing itself, held together only by two files staying in sync. If a future `SchemaRecognition` member is ever added (e.g. a `PARTIALLY_RECOGNIZED` tier) without this dispatch being updated to handle it explicitly, a payload of that new kind would previously have silently fallen into the `CURRENT_SCHEMA` branch and had real verification attempted against it — a possible false `PASS` or `FAIL` for a record this module was never actually confirmed to understand.

**Why this counts as a real defect despite not being currently exploitable:** the same file already demonstrates the stricter alternative style — `HistoricalVerificationResult.__post_init__` raises on an assumed-impossible `schema_family`/`outcome` combination rather than trusting callers to never construct it. The dispatch's elimination-by-two logic was one function away from the guard this project's own established style would normally insist on. This is architecturally the same principle already applied throughout `MB-004`'s campaign — same-generation adjacency, global generation uniqueness, segment/result correspondence, segment-label-vs-content identity — load-bearing assumptions enforced at the boundary where they matter, rather than trusted from upstream. The difference here is severity and attack source (future code evolution, not present-day adversarial input), not the underlying pattern.

**Fix:** both dispatch functions now explicitly check `classification.recognition == SchemaRecognition.CURRENT_SCHEMA` before proceeding, and raise `ValueError` immediately on anything else — turning silent absorption of an unrecognized future state into a fail-closed guard, without restructuring the file's existing early-`return` style into an `elif` chain. Two new regression tests (`test_decision_record_dispatch_raises_on_unrecognized_schema_recognition_value`, `test_execution_audit_record_dispatch_raises_on_unrecognized_schema_recognition_value`) confirm the fail-closed behavior by monkeypatching the classification functions to return a synthetic non-`SchemaRecognition` value, since the real enum has no fourth member to test against directly. 470/470, zero regressions.

**Classification:** `[finding: implementation defect / disposition: fixed + regression]` — same disposition category as `MB-004`'s four fixed findings, but explicitly not filed under `MB-004` or any of the seven attack families, since the discovery process and the risk model are both genuinely different. `VERIFICATION_COVERAGE_MATRIX.md`'s `VP-001` row updated accordingly; `Status` remains `VERIFIED` (the claim itself — one record, exactly one outcome — was never false; this fix strengthens the mechanism that guarantees it, not the claim's truth).

---

## CH-003: a calibration attack — does the methodology generalize beyond `MB-004`, or was `MB-004` simply under-hardened?

**Purpose, stated up front:** after `MB-004` reached full 7/7 family coverage and `VP-001` closed as a distinct latent-exhaustiveness finding, the open question was whether this campaign's seven-family taxonomy finds real things because it's a genuinely effective methodology, or because `MB-004` specifically happened to be unusually under-hardened at the point the campaign started. `CH-003` was chosen deliberately as a target with no presupposition of what it would find — a claim outside the Mode B work entirely, already `VERIFIED` with two passing tests, last touched only via its already-known `GAP-005`/`PG-001` boundary notes. All seven families were traced against real source, not assumed clean or assumed vulnerable going in.

**The claim:** `_check_module_identity_cross_reference()` (`causal_history_verifier.py`) — every `module_id` referenced in the decision or audit logs has at least one successful registration attempt on record. Traced against the actual implementation, which is a two-set-comprehension, one-difference-check function — simple enough that several families could be ruled out structurally rather than empirically:

- **Substitution — ruled out.** The check *is* string equality on `module_id`; no second field or indirection exists for a substitution attack to exploit.
- **Duplication — ruled out.** `successfully_registered_ids` is a set comprehension; multiple successful attempts for the same `module_id` collapse harmlessly, and failed attempts are filtered (`if r.success`) before the set is even built.
- **Boundary Crossing — ruled out, traced rather than assumed.** No `generation_id` scoping exists here, unlike Checks 1/2/6/7 — but `ModuleRegistrationAttemptRecord` (confirmed directly against `module_registration_audit.py`) has no `generation_id` field at all, matching the system's actual design: module registration is meant to persist *across* generations, unlike sequence-bearing records. This is the opposite shape of Check 1/2's original bugs — those needed generation scoping and lacked it; this correctly doesn't need it.
- **Orphan — ruled out.** Every failure entry is built only for `module_id`s already confirmed present in the real `decision_records`/`audit_records` passed in — no failure can reference a phantom identity.
- **Asymmetry — not applicable, not forced.** Registration-to-reference is inherently many-to-one (one registration, many possible references), unlike Check 1/Check 6's or Check 4/Check 5's genuine 1:1 reverse-direction pairs. Recorded as N/A rather than manufacturing an attack that doesn't fit the claim's shape.
- **Omission — real, but already known.** `PolicyDecisionRecord.module_id` is never checked against this at all (confirmed: `verify_causal_history()` never passes `policy_decision_records` into this function). This is `VERIFICATION_COVERAGE_MATRIX.md`'s own pre-existing `CH-003` boundary note, citing `PG-001`'s transitive-edge finding — confirmed accurate, not re-filed as new.
- **Semantic Inflation — the one real, new finding.** The check proves module identity *exists* in the registration history; it does not and structurally cannot prove that registration *preceded* the decision/audit record referencing it. `ModuleRegistrationAttemptRecord.attempted_at_ns` exists, but neither `DecisionRecord` nor `ExecutionAuditRecord` carries a comparable, trustworthy wall-clock coordinate to check it against — the same evidentiary gap this module's own docstring already states for Check 2's cross-log interleaving (`"frame_timestamp_ns is explicitly data, not wall-clock... no reliable shared clock to interleave the two files by"`), simply never previously connected to Check 3's own claim. A future reader seeing `Check 3: PASS` for a `module_id` could reasonably promote "a successful registration exists" into "the module was validly registered when it was used" — a materially stronger claim the evidence does not support.

**Deliberately no new check added.** Comparing `registration.attempted_at_ns` against some decision/audit timestamp would create the *appearance* of temporal verification without resolving the underlying evidentiary gap — no trustworthy shared clock exists between the registration log and the decision/audit logs, the same reason Check 2 doesn't attempt cross-log interleaving either. The honest result is a narrower claim boundary, not a new mechanism: **Check 3 establishes registration existence, not registration-before-reference ordering.** Documented via a new `CLAIM BOUNDARY` section in `_check_module_identity_cross_reference()`'s own docstring, plus `VERIFICATION_COVERAGE_MATRIX.md`'s `CH-003` row.

**Classification:** `[finding: claim-boundary / semantic-inflation issue / disposition: documented limitation]` — no code behavior change, no new test, matching the precedent of every pure-documentation finding this campaign has produced (`MB-004`'s Semantic Inflation, `MB-003`'s registry note, the Eleventh finding).

**What this calibrates:** six of seven families traced to genuine, structural rule-outs or already-known gaps — not "nothing was tried," but "the attacks that were tried against real source found nothing new." One family found a real, previously-undocumented claim-boundary risk. This is evidence the methodology generalizes rather than merely finishing `MB-004`'s own under-hardened corners: the same taxonomy, applied cold to an unrelated, already-`VERIFIED` claim, produced a mix of genuine clean passes and one genuine finding — the shape a sound methodology should produce, rather than either finding nothing anywhere (suggesting the taxonomy is too narrow to be useful) or finding something in everything (suggesting it manufactures findings regardless of the target).

---

## HC-001: remaining four families attacked — full 7/7 coverage reached, four clean

`HC-001` (`ModuleRegistrationAttemptRecord.attempt_hash` detects any field tampering) already carried three findings from earlier in this campaign — Substitution and Omission (both found→documented: `manifest_hash` is a mismatched-implementation-collision risk, and can be entirely absent by design) and Semantic Inflation (found→documented: compound risk with `GAP-005`). The remaining four families — Orphan, Asymmetry, Duplication, Boundary Crossing — had never been attacked. Traced each against real source rather than assumed clean by default:

- **Boundary Crossing — clean, on existing evidence, not fresh tracing.** `ModuleRegistrationAttemptRecord` has no `generation_id` field (confirmed directly against `module_registration_audit.py`), and `SE-002`'s own boundary note already establishes this record type has no historical schema variants either. Neither the generation-boundary bugs Checks 1/2 originally had, nor the schema-boundary risk `historical_verification.py`/`VP-001` covers, has a foothold here — the dimensions those attacks exploit elsewhere don't exist on this record type at all.
- **Asymmetry — clean, traced through all three layers.** The concrete question: is `attempt_hash` re-verified independently on read, or only trusted as computed on write? Traced `module_registration_audit.py` (`attempt_hash: bytes = field(init=False)` — not a constructor parameter, always recomputed in `__post_init__`), `module_registration_audit_persistence.py` (`record_to_json()` never writes `attempt_hash` to the JSON payload at all — there is no stored value for a read path to trust instead of recomputing), and `module_registration_audit_log.py` (`read_all_records()` routes every line through `record_from_json()`, no shortcut, no separate parsing path). The write/read asymmetry this attack looks for structurally cannot exist here, because only the recompute side of that asymmetry exists in the first place — a stronger result than "read-side re-verification exists," since there is no alternative path to have skipped it.
- **Duplication — clean.** `read_all_records()` returns a strict ordered list with no deduplication or set-based collapsing. A duplicate record is simply two independently-tamper-evident entries; `HC-001`'s claim is about a single record's own internal consistency, not log-level uniqueness, so duplicate records don't threaten what the claim actually asserts.
- **Orphan — clean, not a natural fit.** `HC-001` is a leaf claim — a single record type's own hash tamper-evidence — not a composition of other records the way `MB-004`'s candidate graph or `CH-003`'s cross-reference are. There is no edge structure here for an Orphan attack to target.

**Classification:** `[attack result: survived ×4 / disposition: n/a]` for each of the four — no code change, no new test, no new documentation beyond this record of the trace itself.

`HC-001` is now the second claim in this campaign (after `MB-004`) to reach full 7/7 family coverage: 3 found→documented (Substitution, Omission, Semantic Inflation), 4 clean (Orphan, Asymmetry, Duplication, Boundary Crossing).

---

## HC-003: remaining six families attacked — full 7/7 coverage, zero new findings across the entire taxonomy

`HC-003` (`ExecutionAuditRecord.audit_hash` detects tampering across every field) had exactly one prior attack — Omission (resolved 2026-08-07: all 9 fields confirmed hashed, nothing excluded from coverage). The other six families had never been tried. Traced each against real source (`execution_audit_persistence.py`, `execution_audit_log.py`), not assumed to mirror `HC-001`'s results despite the structural similarity:

- **Asymmetry — clean, confirmed fresh rather than inferred from `HC-001`.** `audit_record_to_json()`'s own docstring states `audit_hash` is "NOT written"; `audit_record_from_json()` always reconstructs via the real `ExecutionAuditRecord(...)` constructor, so `__post_init__` recomputes fresh every time. `read_all_audit_records()` routes every line through `audit_record_from_json()` directly, no shortcut. No stored hash value exists anywhere for a compromised read path to trust — same result as `HC-001`, independently verified against a different file rather than assumed to carry over.
- **Boundary Crossing — clean, with a sharper mechanism than expected.** Unlike `HC-001`'s record type, `ExecutionAuditRecord` *does* carry `generation_id` — but `execution_audit_persistence.py`'s own docstring confirms it "participates in `audit_hash`'s derivation," so tampering with it is caught exactly like tampering with any other field. No cross-generation boundary exists for a single record's own tamper-evidence claim to cross, regardless of whether the record type carries a generation dimension at all.
- **Substitution — traced to a real specificity gap in existing documentation, not a new underlying finding.** `execution_audit_persistence.py`'s docstring names something the original `HC-003` resolution text didn't spell out individually: `input_hash`, `prior_state_hash`, AND `output_hash` are all three genuine opaque external references, not just `output_hash` alone. The existing boundary text ("internal consistency, not external authenticity... same as everywhere else in this hash chain") already generalizes correctly to cover all three — this attack confirms that generalization explicitly for each field rather than leaving two of the three as an unstated inference. `VERIFICATION_COVERAGE_MATRIX.md`'s `HC-003` row updated to name all three fields directly.
- **Duplication — clean**, same reasoning as `HC-001` and every other single-record hash claim in this campaign: no dedup logic exists at the log level, and the claim is about one record's own internal consistency, not log-wide uniqueness.
- **Orphan — clean.** `audit_hash` is never used as a join key anywhere in this codebase (`CH-001`'s actual join key is `(sequence_id, module_id, generation_id)`) — no edge exists for an Orphan attack to target.
- **Semantic Inflation — clean.** The existing boundary text's "internal consistency, not external authenticity" framing already does the anti-inflation work this family targets. Checked specifically for a `CH-003`-style existence-vs-ordering risk (given the shared naming with the causal-history `CH-003` check, worth ruling out rather than assuming distinct) — `frame_timestamp_ns` is already documented elsewhere as non-authoritative data, and this claim makes no temporal assertion for that risk to attach to in the first place.

**Classification:** `[attack result: survived ×6 / disposition: n/a]` — no code change, no new test. One documentation specificity gap closed (Substitution's finding, folded into the matrix row update rather than filed as a separate numbered finding, since the underlying claim was never actually wrong).

`HC-003` is now the **third** claim in this campaign to reach full 7/7 family coverage — and the first to do so with **zero new findings across the entire taxonomy**. `MB-004` and `HC-001` each closed with several `found→documented` results mixed in; `HC-003` closed entirely clean. Read together with `CH-003`'s calibration result (6 clean, 1 real finding) and `HC-001`'s (4 clean, 3 already-known), this is further evidence the methodology's clean passes are genuine signal, not an absence of trying — three claims attacked to full coverage this session, with a real spread of outcomes (all-clean, mostly-clean-plus-one-finding, mixed) rather than a uniform result in either direction.

---

## PG-001: the provenance graph itself — a deliberately different axis of attack

`PG-001` (`PROVENANCE_GRAPH_MODEL.md` — the four record types' causal relationships form an explicit, checkable graph, with direct edges distinguished from transitively-composed ones) was chosen deliberately, after ranking candidates against six criteria (attack surface, cross-object coupling, claim strength, sparse coverage, independence from what's already been attacked, evidence availability). It scored highest on cross-object coupling and independence — every prior full-coverage claim this session (`MB-004`, `HC-001`, `HC-003`) concerned a single record type's own construction or hash integrity; `PG-001` is explicitly *about* the relationships between four different record types, a genuinely different question.

**A self-audit correction, worth stating openly rather than quietly editing away:** this section originally marked all seven families as closed with uniform confidence. On review, three of those cells were weaker than the others — Boundary Crossing and Duplication had been traced by reading the check's own logic, not attacked by constructing and running anything, and Orphan/Asymmetry had been counted as two independent closures when they were actually one pre-session finding tagged to two columns. Per this campaign's own `CH-002` lesson — a clean verdict recorded before the actual attack was run is exactly the premature-closure failure mode this methodology exists to catch — those cells have been re-done with real adversarial constructions, executed, not just reasoned about. What follows is the corrected, honest state.

**Orphan — found→fixed, pre-session (2026-08-06).** Check 5 was added specifically to catch a fabricated `PolicyDecisionRecord` with no `DecisionRecord` at all — the literal orphan-artifact shape. See `PROVENANCE_GRAPH_MODEL.md`'s "Second finding" for the full account.

**Asymmetry — the same finding as Orphan above, not an independent closure.** The root cause of the Second finding *was* an asymmetry (Check 4 existed with no reverse-direction check at all — "A checked against B, B never checked against A"); the artifact it produced *was* an orphan. One finding, two legitimate descriptions of it, but only one attack was ever run. Recorded here as a cross-reference, not double-counted as two separate results.

**Substitution — the real defect this session, confirmed by direct construction and execution.** Check 5 verified `(sequence_id, generation_id)` key co-occurrence only — its body never read `module_id` or `decision_hash` on either side. Check 4 already defends the reverse direction with a `decision_hash` equality requirement (which encodes `module_id`, confirmed directly against `ExecutionPolicyDecision._compute_decision_hash()`); Check 5 had no equivalent condition. Built the real dependency chain in the sandbox (`module_state.py`, `execution_policy_decision_contract.py`, `decision_record_contract.py`, `policy_decision_record_contract.py`, and Check 5's own logic, extracted verbatim) and actually ran the adversarial construction: a genuinely valid `DecisionRecord` for `module_B` and a genuinely valid `PolicyDecisionRecord` wrapping a real `ExecutionPolicyDecision` for `module_A` — different modules, different `decision_hash` values, sharing only the key — passed Check 5 with zero failures reported, confirmed by execution. Fixed by requiring `decision_hash` equality among same-key candidates, mirroring Check 4's own pattern exactly. Two new regression tests added to `test_causal_history_verifier.py`: `test_orphan_check_rejects_a_different_modules_decision_at_the_same_key`, `test_orphan_check_still_passes_clean_on_genuinely_correlated_pair_after_identity_fix`. 472/472, zero regressions. Committed `24c3a88`.

**Classification:** `[finding: implementation defect / disposition: fixed + regression]`.

**Boundary Crossing — clean, confirmed by direct construction and execution against the fixed Check 5, not traced.** The sharpest available construction: `decision_hash` does not encode `generation_id` (confirmed against `ExecutionPolicyDecision._compute_decision_hash()`), so two genuinely valid `DecisionRecord`s for the *same module*, with *identical* policy content, in *two different generations*, produce **identical `decision_hash` values** — confirmed by execution (`b4962e04ebefde5a...` for both). Built exactly this collision, then ran the current, fixed Check 5 against it two ways: with both generations' decisions present (no false negative — passes clean, as it should, since generation 1's real decision is genuinely there); and — the case that would actually expose a defect if one existed — with *only* the wrong-generation decision present, policy record wanting generation 1's key specifically. Result: correctly rejected, despite the identical `decision_hash`, because `decisions_by_key`'s dict key is `(sequence_id, generation_id)` — a compound tuple checked by exact equality before any hash comparison ever runs, so a cross-generation collision structurally cannot reach the hash-comparison stage at all. This is architecturally the strongest possible negative result for this family: not "we didn't find a way to break it," but "the mechanism that would need to fail for this to be exploitable is checked first, unconditionally, before the mechanism the attack targets is ever reached."

**Duplication — clean, confirmed by direct construction and execution, not traced.** Built two genuinely different `DecisionRecord`s at the exact same `(sequence_id, generation_id)` — a legitimate-shaped duplicate, different policy content, different `decision_hash` values — then two `PolicyDecisionRecord`s: one genuinely matching one of the duplicates, one a genuine orphan (matching neither). Ran the current Check 5 against both duplicates plus both policy records together: exactly one failure reported, for the genuine orphan only — the real match was correctly found among the duplicate noise, and the real orphan was not masked by the presence of unrelated duplicate candidates at its key. Confirms `any(...)` semantics do what they're supposed to: find a genuine match if one exists among candidates, without being fooled by decoys, and without candidates that don't match suppressing detection of ones that should fail.

**Omission — attacked and executed this turn, a single, focused construction against the real pipeline.** The precise question: can a `PolicyDecisionRecord` ultimately reference an unregistered module while every current graph check nevertheless passes — i.e., does the "transitive, not direct" composition (Check 4 + Check 3) actually enforce what `PROVENANCE_GRAPH_MODEL.md` claims it does when the full pipeline runs together, or only in isolated theory? Built the exact construction the hypothesis calls for: a genuine `ExecutionPolicyDecision` and matching `DecisionRecord` for `module_A`, with `module_A` deliberately never registered (only an unrelated `module_B` is), everything else satisfying Check 4/5's requirements. Ran the **real, unmodified `verify_causal_history()`** — not `_check_module_identity_cross_reference()` called alone — importing the real `causal_history_verifier.py` confirmed fresh from the repo at `24c3a88`, with only the four disk-read functions (`read_all_registration_records` etc.) monkeypatched to return the constructed objects directly rather than reading real files; every `_check_*()` function and `verify_causal_history()`'s own orchestration ran unmodified. Result: `report.passed is False`, exactly one failure, and it is precisely the one this attack was built to test for — `"Module identity: module_id='module_A' appears in decision and/or audit logs but has no successful registration attempt..."` (Check 3, firing directly). `checks_run` confirms all eight signals (seven checks, one of them run twice for the two logs) executed. **Why:** the `DecisionRecord` needed to satisfy Check 4/5's `decision_hash` match for `module_A` is the *same* `DecisionRecord` object `verify_causal_history()` passes to Check 3 — there is no path where a decision real enough to satisfy the transitive composition could exist without also being directly visible to Check 3 in the same pipeline run. The "transitive, not direct" language describes how the *proof* is structured, not a gap in what the full pipeline actually checks together.

**Classification:** `[attack result: survived / disposition: n/a]` — one attack, one hypothesis, one execution, genuinely clean.

**Classification:** `[attack result: insufficient evidence / disposition: logged / pending evidence]` — not a new finding, an accurate acknowledgment that this family wasn't actually attacked.

**Semantic Inflation — documented, a different kind of finding entirely, appropriately rigorous for its type.** Distinguishing the two questions precisely, since conflating them would be its own kind of imprecision: *does this edge actually connect the correct records* (implementation — answered above, yes, as of the Substitution fix, now confirmed by execution across three families) versus *what does successfully constructing an edge prove* (claim boundary — a different question, with no runtime construction to execute against). `VERIFICATION_COVERAGE_MATRIX.md`'s own `CH-001` row already states the precise boundary for one edge — proves key co-occurrence, never that the decision's authorization relates to the audit's actual content — but `PROVENANCE_GRAPH_MODEL.md`, the document that actually defines the graph this claim refers to, never generalized that caveat to the graph level. Documented via a new section in `PROVENANCE_GRAPH_MODEL.md` itself.

**Classification:** `[finding: claim-boundary / semantic-inflation issue / disposition: documented limitation]`.

**One genuine documentation-completeness gap, found while tracing Asymmetry, worth naming separately from the family verdict itself:** the model names exactly one two-hop transitive path (`PolicyDecisionRecord → DecisionRecord → ExecutionAuditRecord`) but never its reverse, even though the reverse has been fully covered by two already-existing direct checks composed since before Check 5 existed. Named explicitly in `PROVENANCE_GRAPH_MODEL.md`'s transitive-edges table now — a documentation gap, not a verification gap, since nothing needed to change in the checks themselves.

`PG-001` is now the **fourth** claim in this campaign to reach full 7/7 family *disposition* — and, as of the Omission attack above, all seven genuinely attacked, not merely dispositioned (four executed constructions confirming real results: one fixed defect, three clean; two pre-session/cross-referenced; one documented claim-boundary finding, which by its nature has no runtime construction to execute). This is the campaign's second result with real executed-clean evidence at this scale (alongside `HC-003`), and the self-correction that preceded it is worth keeping on record: the first draft of this section would have been exactly the kind of premature closure `CH-002` already taught this project to watch for, caught this time before being committed rather than after.

---

## Two additional findings, surfaced by applying Omission and Duplication to CH-004/CH-006

Not requested, but a natural extension once the taxonomy existed — applying two of the seven families to the two directional checks just built.

**Omission — resolved 2026-08-08.** `verify_causal_history()`'s own docstring states the deliberate contract explicitly: `passed=True` means *all requested checks passed*, not *all applicable checks passed* — "behavior is IDENTICAL to before Check 4 existed." The distinguishing signal (`policy_decision_record_count` staying `None` when Checks 4/5 didn't run) already existed and was already documented — the finding was never that no signal exists, only that it's *indirect*: a caller checking only `.passed`, the obviously-named field, would never notice it. Built: `checks_run: FrozenSet[str]`, populated with a stable string identifier for every check that actually executed, always including the six that always run, plus the two optional ones when `policy_decision_log_path` is supplied. This adds no new information over what `policy_decision_record_count` already implied — it adds discoverability: a field literally named `checks_run` doesn't require already knowing the indirect inference. Two regression tests confirm the exact set in both the with- and without-policy-log cases. **[finding: implementation defect / disposition: fixed + regression]** — a mild one (adds discoverability, not new information), but still a concrete code change with a regression test, not a documentation-only outcome.

**Duplication — decision made 2026-08-08: stay logged, not built. This is a resolved "insufficient evidence to act" state, not an unresolved one.** Check 4's matching logic (`policy_by_key.setdefault(key, []).append(p)`, then `any(...)` over the matches) accepts *any* number of matching `PolicyDecisionRecord`s at a given key — it asserts "at least one," never "exactly one." A duplicated, byte-identical `PolicyDecisionRecord` appended twice would pass Check 4 without comment. The retry-legitimacy investigation (2026-08-07) checked every file with sandbox access to the append path — `policy_decision_record_log.py` (its own docstring explicitly disclaims "crash safety, atomic writes, or concurrent-writer coordination... those remain separate, harder questions"), and `deterministic_execution_engine.py`, which never calls `append_policy_decision_record()` (or any `append_*`) at all — it only builds in-memory lists; real persistence happens outside this file. No other file in the sandbox calls any `append_*` function except tests setting up fixtures. **That investigation was already exhausted — there is no further fact-finding available without the production persistence call site, which genuinely isn't in this sandbox and cannot be requested without knowing what file it would even be.** The honest conclusion stands exactly where it was left: no retry logic exists anywhere in accessible code, narrowing the risk to "a bug in an unseen caller, or deliberate fabrication" — but this does not amount to evidence that duplicates are categorically impossible in the real architecture, and tightening to "exactly one" without that evidence risks breaking a legitimate pattern this project simply cannot see. **Decision: remain at "logged, not built." This is the responsible conclusion given the actual evidence ceiling, not a deferred one** — revisiting it would require new source material, not more analysis of what's already here. **[finding: insufficient evidence / disposition: logged / pending evidence]**

---

## CB-001: `reconstruction_valid`'s scope was understated — then a full seven-family campaign, run only after the claim was synchronized

Selected via a disciplined matrix-level candidate selection pass (not a default next-in-line pick) after four claims — `MB-004`, `HC-001`, `HC-003`, `PG-001` — reached genuine full 7/7 coverage. Ranked against six criteria (cross-object coupling, claim strength, consequence if false, sparse coverage, independence from the four closed campaigns, quality of executable evidence): `CB-001` (cold boot reconstruction — registration, authorization, and execution histories reconstructed from disk alone, "verified ordering and causal relationships") scored highest on every criterion, ahead of `CH-007` (strong second, but adjacent to `CH-001`/`PG-001`'s already-heavily-attacked territory) and `CH-008`.

**Deliberately not a seven-family sweep.** `cold_boot_reconstruction.py` is, by its own docstring, "an assembly of already-proven pieces... not new capability" — most of its substantive correctness is `verify_causal_history()`'s job, already attacked exhaustively via `PG-001`. Running the same seven attacks again against the same underlying checks would mostly re-test already-covered ground. Instead: a narrow, intent-focused investigation into a specific, precisely-stated question, matching `VP-001`'s own precedent for a finding that doesn't fit the family taxonomy.

**The question:** does `COLD_BOOT_RECONSTRUCTION_CONTRACT.md` — which calls itself "the authoritative specification for what cold-boot reconstruction can and cannot claim" — accurately describe what `reconstruction_valid` actually depends on?

**Five-step trace, each step against real source, not assumed:**
1. `reconstruct_cold_boot()`'s body: `causal_report = verify_causal_history(...)` stored whole into the result, unfiltered.
2. `reconstruction_valid`'s definition: `return self.causal_report.passed` — a direct one-line passthrough.
3. `passed`'s definition, confirmed directly from the `CausalHistoryReport` class: `return len(self.failures) == 0`, over one flat, uncategorized `failures: List[str]`.
4. The contract's own `SHALL 4` text: named exactly two checks, and stated explicitly — *"No other cross-artifact relationship is currently verified, and none should be assumed to exist."* The term `reconstruction_valid` was never used anywhere in the document at all.
5. Whether the architecture anywhere distinguishes "core `CB-001` evidence" from "additional verifier safeguards": confirmed, from the class definition's own docstring, that it does not — `passed` depends on "every check that actually ran," unconditionally.

Since no such two-layer distinction exists anywhere in the real architecture, the contract's `SHALL 4` — not the code — was the inaccurate side of the divergence: this reads as one verifier whose scope grew through genuine, deliberate additions (Checks 6 and 7, both added in later work for real reasons, per `CH-001`'s and `CH-007`'s own findings) with this specific document never revisited, the same "governing document written before a later check existed" shape already seen twice this session (`PG-001`'s Third finding; `CH-002`'s original bug).

**Two isolated adversarial constructions, executed, not merely traced, confirming Checks 6 and 7 as genuine `reconstruction_valid` prerequisites:**

- **Check 6 (decision-execution-completeness) isolated:** two genuinely allowed `DecisionRecord`s for one registered module — sequence 1 (not trailing, no audit) and sequence 2 (trailing, with a matching audit). Ran the real, unmodified `reconstruct_cold_boot()` calling the real, unmodified `verify_causal_history()`, only the disk-read functions substituted for direct in-memory objects (the same narrow substitution as `PG-001`'s own Omission finding). Result: exactly one failure, Check 6's, naming sequence 1's missing audit explicitly; both `SHALL 4`-named checks confirmed clean by inspecting the actual failure list; `reconstruction_valid` was `False`.
- **Check 7 (no-contradictory-decisions) isolated:** one registered module, two `DecisionRecord`s sharing the exact same `(sequence_id, module_id, generation_id)` key — one allowed, one denied — no audit records at all, deliberately avoiding any Check 1 interaction. Result: exactly one failure, Check 7's contradictory-decision message; Check 6 confirmed *not* firing (the allowed decision's trailing exemption applied cleanly, ruling out cross-contamination between the two attacks); both `SHALL 4`-named checks again confirmed clean; `reconstruction_valid` was `False`.

**Disposition: `COLD_BOOT_RECONSTRUCTION_CONTRACT.md`'s `SHALL 4` corrected** — now enumerates all six checks that run unconditionally when `reconstruct_cold_boot()` is called, explicitly split into genuine cross-artifact relationships (decision→audit ancestry, module identity, decision-execution-completeness) versus per-log invariants (sequence ordering, no-contradictory-decisions), with the original text preserved verbatim for the historical record. No code changed — nothing about `causal_history_verifier.py` or `cold_boot_reconstruction.py`'s actual behavior was wrong; the correction is entirely to the document describing that behavior. **[finding: claim-boundary / semantic-inflation issue / disposition: documented limitation]**.

**Why this finding is a different kind of result than anything else this campaign has produced:** every prior finding — `MB-004`'s Substitution, `PG-001`'s Check 5 identity gap, `HC-001`'s `manifest_hash` boundary — was about whether a check correctly validates the data it's given. This one is about whether the document *describing what the verification system verifies* keeps pace with the verification system itself. Not a hash bug, not a join-key bug — a test of whether the specification remains an accurate map of the territory as the territory grows.

**The claim-boundary finding above was deliberately not treated as license to declare `CB-001`'s campaign complete.** Per explicit direction: these were claim-boundary attacks establishing what `CB-001` actually means, not a full seven-family sweep — the real campaign began only after the finding above was fully synchronized across this document, `VERIFICATION_COVERAGE_MATRIX.md`, and `COLD_BOOT_RECONSTRUCTION_CONTRACT.md`, confirmed committed and verified via `git log`/`git status`/`pytest` before a single new attack was attempted.

**Substitution, Duplication, Boundary Crossing — all clean, confirmed by direct execution, not assumed from `cold_boot_reconstruction.py`'s thin-wrapper design.** Substitution: real file I/O, genuinely swapped log paths (audit log's path handed to the `decision_log_path` parameter) through the real `reconstruct_cold_boot()` — fails loudly with a specific `DecisionLogCorruptionError`, naming the exact missing field and classification detail, since the schema-shape check one layer down catches any mismatch regardless of which parameter received which path. Duplication: the same real path passed to all three parameters triggers the identical protection. Boundary Crossing: a real, deliberate multi-generation history — `sequence_id` legitimately resetting across two generations for the same module — both generations' records correctly present in both returned histories, `reconstruction_valid=True`, zero failures, no false cross-generation conflation.

**Orphan — a real implementation defect, found and fixed, the strongest result this claim has produced.** `reconstruct_cold_boot()` read each log *twice*: once directly for the returned histories, and again inside `verify_causal_history()`'s own independent internal read of the same paths — with no invariant connecting the two. Confirmed by direct adversarial construction and execution (monkeypatching the second read to return genuinely different data than the first): a caller could receive `authorization_history` containing 3 records while `causal_report` reflected verification of only 2 of them, `reconstruction_valid` reporting `True`, zero failures — a silently wrong "verified" claim over data that was never actually checked.

An important correction happened here, worth preserving on the record rather than smoothing over: the first framing of this finding characterized it as an environmental/concurrency limitation — "the files are ordinarily static, so this mostly wouldn't happen in practice." That framing was wrong, and was corrected directly: the defect holds *even in a completely static filesystem*, since nothing about the architecture's two-independent-reads design depends on concurrency to be unsound — the adversarial methodology's own standard is whether the architecture *permits* the divergence, not whether it would occur under ordinary conditions. This is the same discipline `CH-002`'s own lesson already established, applied to evaluating a finding's severity rather than to whether an attack had actually been run.

**The fix — single-read/shared-snapshot semantics, chosen deliberately over the weaker count-comparison alternative.** `causal_history_verifier.py`'s check-running core was extracted into a new function, `verify_causal_history_from_records()`, accepting already-loaded records directly with no file I/O of its own. The existing path-based `verify_causal_history()` becomes a thin wrapper delegating to it — confirmed by direct execution that its behavior, signature, and every existing caller are completely unaffected by the extraction. `reconstruct_cold_boot()` now calls the new function with the exact record objects it already read once for the returned histories: true identity of evidence, not matching counts, eliminating the entire class of divergence rather than detecting one instance of it. Confirmed the fix holds by re-running the identical adversarial monkeypatch against the patched code: zero effect, since there is no longer a second, divertable read to target. `[finding: implementation defect / disposition: fixed + regression]`. Regression test: `test_snapshot_identity_returned_and_verified_histories_cannot_diverge`. Full suite: 473/473.

**Semantic Inflation — cross-referenced with Orphan, not a separate result**, matching the same pattern already established for `PG-001`'s Orphan/Asymmetry pair: one underlying issue (`reconstruction_valid` could be over-read as covering the full returned history, when the two-read design never guaranteed that), two legitimate family-shaped descriptions of it, but only one attack.

**Omission — already covered by the earlier claim-boundary finding above**, not re-attacked fresh: `reconstruction_valid` depending on Checks 6/7 beyond the two originally-named checks was itself an Omission-shaped gap in what the contract disclosed, already found and documented before this campaign began.

**Asymmetry — traced, not assumed, and found to have no meaningful attack surface at this composition layer.** Five candidate directional relationships were considered and ruled out: registration-to-decision/audit cross-referencing (already `PG-001`/`CH-003` territory, no meaningful reverse); the three returned histories against what gets verified (eliminated by the Orphan fix itself — now the same objects); SHALL 5 hash consistency (a within-record property, not a cross-object relationship); read-order/failure-propagation across the three logs (a real question, but sequencing, not the family's actual "A checked against B, B never checked against A" shape); and the new records-based entry point's narrower input validation relative to the path-based wrapper (a real observation about the fix's own contract, not a pre-existing cross-record relationship `CB-001`'s claim depends on). `cold_boot_reconstruction.py` introduces no new cross-record relationship of its own, consistent with its own docstring describing itself as "an assembly of already-proven pieces... not new capability." `[attack result: n/a / disposition: n/a]`.

`CB-001` is now the **fifth** claim in this campaign to reach genuine full seven-family coverage, and the first whose campaign was deliberately gated behind fully synchronizing an earlier claim-boundary finding before any new attack began — a discipline worth naming as its own precedent alongside `PG-001`'s mid-campaign self-audit and `CH-002`'s original premature-closure lesson.

---

## CH-007: the first campaign run under an explicit pre-attack synchronization gate

After five claims reached genuine full coverage, the campaign paused before automatically selecting a sixth. The lessons of those five — claim/code drift (`CB-001`), premature closure (`PG-001`), cross-referencing evidence that doesn't actually establish the property in question (`PG-001`'s Orphan/Asymmetry pair) — were operationalized into an explicit five-step pre-attack gate, run *before* any construction against `CH-007`:

1. **Claim synchronization** — what does the governing text claim, what code actually determines the verdict, are there checks the text doesn't name, is anything newer than the text describes?
2. **Evidence topology** — which records establish the claim, which relationships are direct versus transitive, are they directional?
3. **Identity** — what constitutes "the same thing" — keys, hashes, generation, sequence, module, or some combination?
4. **Evidence-set integrity** — is what's returned exactly what was verified, are there multiple reads or transformations?
5. **Composition** — are individually correct checks being composed, and does the composition preserve the invariant?

Traced against real source, not assumed: `CH-007`'s own claim and code were found synchronized (unlike `CB-001`'s starting state) — the matrix row's trailing-exemption and generation-scoping language matched the implementation exactly. The join key `(sequence_id, module_id, generation_id)` was confirmed to already be the "hardened" 3-tuple shape `PG-001`'s Check 5 defect evolved into, not the vulnerable 2-tuple shape it started from — a real, correctly-flagged hypothesis about Substitution's likely fit, later confirmed by execution rather than assumed from the gate alone. The gate also flagged, correctly, that `CH-001`/`CH-007`'s Asymmetry pairing had already been examined by `PG-001` — but only for whether a reverse check *exists*, not whether `CH-007`'s own trailing-exemption logic was itself correct. That distinction — structural coverage is not the same as having tested the property an attack actually targets — was insisted on explicitly rather than allowed as a shortcut: **"already covered" does not mean "automatically closed."** `PG-001`'s evidence was checked against what `CH-007`'s own Asymmetry attack would need to establish, found insufficient, and traced fresh rather than cross-referenced.

**Substitution, Duplication, Boundary Crossing — clean, confirmed by direct execution, not assumed from the gate's own "looks safe" read.** Multi-module grouping, generation-transition variants (a real `sequence_id` collision deliberately constructed across two generations), duplicate audits, and genuinely swapped log paths through the real pipeline all behaved correctly.

**Finding #1 — Duplication, a real implementation defect, found and fixed.** The trailing exemption compared each decision's own `sequence_id` against the group's maximum value only — it never asked whether that maximum was *uniquely* held. Two allowed decisions sharing the maximum `sequence_id` — one genuinely missing its audit, one an arbitrary duplicate at the same value — both received the exemption identically. Confirmed by direct construction and execution: this exact scenario produced zero failures across the *entire pipeline*, not just this one check (Check 2's sequence-ordering check also permits ties — "non-decreasing" allows equal values — so nothing else caught it either). Fixed by requiring the maximum to be uniquely occupied by exactly one allowed decision; when two or more tie, none are exempt, and each is checked individually like any other decision. `[finding: implementation defect / disposition: fixed + regression]`. Regression test: `test_ambiguous_max_sequence_id_denies_the_trailing_exemption_to_both`.

**Finding #2 — Omission, a second, genuinely distinct real implementation defect, found and fixed.** A different mechanism from Finding #1, deliberately kept as a separate entry rather than folded into one "terminal exemption bug" — the attack surfaces differ even though they share a conceptual center. The exemption's "evidence of continuation" was computed only over *allowed* decisions — `allowed_by_module_generation` filtered `if d.allowed` before "last" was ever determined. A **denied** decision at a later `sequence_id` is real evidence the engine reached that later frame's authorization step, which requires the earlier frame to have already resolved — the same kind of proof a later *allowed* decision already provided — but it was invisible to the check entirely. Confirmed by direct construction: a single incomplete allowed decision followed only by a denied decision at the next `sequence_id` passed with zero failures. Fixed by computing the true last position over *all* decisions, allowed or denied — denied decisions still never need an audit and are never themselves flagged, but their existence now correctly denies the exemption to an earlier, genuinely incomplete allowed decision. `[finding: implementation defect / disposition: fixed + regression]`. Regression tests: `test_denied_decision_at_later_sequence_id_counts_as_evidence_of_continuation`, plus a dedicated false-positive guard (`test_denied_decision_before_a_genuine_trailing_crash_is_not_a_false_positive`) confirming a denied decision at an *earlier* position never wrongly denies a genuine trailing exemption.

**Asymmetry — traced fresh against real source, the hypothesized strict-vs-lax split disproven.** The natural hypothesis going in — `CH-001` requires exact uniqueness while `CH-007` only checks existence — was checked directly against `CH-001`'s own body rather than trusted from the matrix's summary language ("exactly one preceding decision record"). `CH-001` turned out to use the identical set-membership logic `CH-007` does; the matrix's own phrase describes the *claim*, not what the code enforces. A real, negative result from tracing real source, not a family left unattacked.

**Orphan and Semantic Inflation, both low-fit, neither skipped.** Orphan: `CH-007` operates on two flat lists with no composed structure of its own, the same leaf-check shape already established for `HC-001`/`HC-003`. Semantic Inflation: worth stating precisely given the two defects just found — `CH-007` passing means no *non-exempt, non-ambiguous* incomplete decision was found among the evidence recorded, not that no decision was ever silently abandoned.

`CH-007` is now the **sixth** claim in this campaign to reach genuine full seven-family coverage — the first attacked under an explicit, reusable pre-attack gate distilled from the prior five campaigns' own lessons, and the first campaign this session to produce two real, independently confirmed defects at the same conceptual boundary while correctly keeping them as separate findings rather than merging them for the sake of a tidier narrative.

---

## CH-008: a clean control result — correct evidence universe, correct predicate, one real claim-boundary limitation

Selected after a meta-synthesis exercise (A-Team dispatch ATD-2026-08-09-PHX-META-02) explicitly asked whether `CH-007`'s two findings generalize into a broader "evidence-universe" failure pattern across Phoenix, or whether that conclusion would be premature given `CH-007`'s own claims were deliberately selected for cross-object coupling — a real selection effect, not a random sample. `CH-008` (no contradictory decisions: no `(sequence_id, module_id, generation_id)` key may have both an allowed and a denied `DecisionRecord`) was chosen specifically as a genuinely different claim shape — the first single-record-type, within-record internal-consistency claim attacked this session, rather than another cross-record relationship.

**Pre-attack gate, with the evidence-universe question now embedded directly in the existing steps (not a new step, per explicit instruction against methodology sprawl):** claim and code found synchronized. The gate itself flagged the standout candidate before any attack began — a genuinely fresh composition question between `CH-008`'s contradiction check and `CH-007`'s just-fixed terminal-boundary logic, both operating on the same `decision_records` list, neither designed with the other's recent change in mind.

**Substitution, Duplication, Boundary Crossing, and the composition probe all survived, confirmed by direct execution, not assumed clean.** Two colliding records with the same `decision_hash` and two with genuinely different `decision_hash` values were both caught identically. Multiple denied records fabricated at one key produced exactly one reported failure regardless of true multiplicity. Different-generation keys correctly stayed independent. The composition probe — a contradictory pair sitting exactly at what would be `CH-007`'s terminal boundary — produced exactly the two expected, independent failures with zero interference: `CH-007` correctly flagged the genuinely earlier incomplete decision (continuation evidence exists at the contradictory key, regardless of that key's own validity), and `CH-008` independently flagged the contradiction itself, with the unique allowed decision at that key correctly *not* double-flagged by `CH-007`'s own exemption logic.

**Asymmetry and Orphan both traced fresh, genuinely n/a** — the symmetric, identical construction of `allowed_keys`/`denied_keys` from the same input list leaves no directional relationship for Asymmetry to target; no composed structure exists for Orphan to dangle from.

**Semantic Inflation — the campaign's real content, two substantive observations, not a generic caveat.** (1) The failure message is identical whether two colliding records share a `decision_hash` (one record corrupted, its `allowed` flag flipped) or have genuinely different content (two independent decisions colliding at the same key) — this check proves a contradiction exists, not which of these two structurally different situations produced it. (2) Reporting is at key granularity, not record granularity — one fabricated denied record at a key and thirty produce the identical single failure; a caller reading "1 failure" has no way to know the true scale of what was fabricated. `[finding: claim-boundary/semantic-inflation issue / disposition: documented limitation]`. No code changed.

**Why this result matters as much as a defect would have:** `CH-007` had a synchronized specification sitting on top of defective implementation semantics. `CH-008` has the inverse shape — correct implementation semantics under a claim whose plain reading doesn't overstate anything, confirmed by attacking it rather than assumed. Six-plus campaigns in, the methodology is now demonstrated to distinguish "the verifier is wrong" from "the claim is narrower than it might sound" from "the claim/verifier relationship survives attack" — three outcomes that would look identical from the outside without the seven-family discipline actually being run to completion on a clean result, not stopped early because nothing was found.

---

## HC-004: the inverse of CH-007 — correct implementation, imprecise specification

Selected as the strongest remaining candidate after `CH-008` closed the `CH-` series (`CH-001` through `CH-008`, all now attacked or closed) — ranked against `HC-002` (a near-duplicate of `HC-001`/`HC-003`'s already-twice-tested single-hash shape, low independence) and `SE-004` (narrow, low attack surface). `HC-004` stood out as genuinely different structure: `PolicyDecisionRecord`'s **two** hash layers (`decision_hash` inner, `entry_hash` outer), the first hash claim this session with internal relationship to probe rather than a single opaque value.

**The pre-attack gate surfaced the headline finding before any construction began**, directly from real source: `entry_hash`'s own computation includes `decision_hash`'s value as one of its inputs — the outer layer is built on top of the inner one, not computed from anything orthogonal to it. The project's own persistence-module docstring calls this "TWO INDEPENDENT LAYERS OF HASH RECOMPUTATION" in the same sentence that describes `entry_hash` being derived "from THAT freshly-rederived `decision_hash`" — acknowledging the chain and calling it independent in the same breath. This tension needed real execution to resolve precisely, not structural reasoning alone.

**Confirmed by direct construction:** an outer-layer-only tamper (same `policy_decision` content, different `sequence_id`) left `decision_hash` unchanged but changed `entry_hash`. An inner-layer-only tamper (different `policy_decision` content, same `sequence_id`/`generation_id`) changed both. **Checking `entry_hash` alone cannot distinguish these two cases — both produce an `entry_hash` change identically.** Only `decision_hash`, checked separately, discriminates which layer was actually corrupted. This is the real content behind the claim's imprecision: "independently tamper-evident" is true in the sense that each layer independently *catches* tampering within its own scope, but not in the stronger sense a reader might reasonably assume — that the failure signal alone tells you which layer failed.

**Substitution, Duplication, Boundary Crossing all clean, confirmed by execution.** Neither hash field can even be attempted as a constructor argument (`field(init=False)`, confirmed via `inspect.signature`, not merely read from the class definition) — no path exists to pass a forged hash directly. Two independently-constructed records from identical inputs produce identical hashes with no collapse or cross-instance state; log-level duplication is `CH-004`/`CH-006`/`PG-001` territory, outside this claim's own scope. `entry_hash` correctly distinguishes generations while `decision_hash` correctly stays unaffected by `generation_id`, confirmed by execution across multiple variants.

**Asymmetry confirmed by execution, explicitly cross-referenced rather than counted as a second finding.** The chain is strictly one-directional: `decision_hash`-scope changes always propagate to `entry_hash`; `entry_hash`-scope changes never propagate back — confirmed across multiple constructed variants, not asserted from the structure alone. This is the *same underlying structural fact* as the Semantic Inflation finding above, viewed through Asymmetry's own lens, not an independent second defect.

**Orphan traced, genuine n/a** — leaf record, no composed edges of its own; the one real composition question (`CH-003` + `HC-004`, whether the embedded decision's `module_id` was cross-checked against registration) is already `PG-001`'s territory, confirmed to be the same question already answered there rather than assumed equivalent and skipped.

**Disposition, held to deliberately:** `[finding: claim-boundary/semantic-inflation issue / disposition: documented limitation]` — **no code changed.** The architecture is coherent and defensible exactly as built; chaining the outer layer over the inner one is a reasonable design, not a defect needing a rewrite. The correction is entirely to the claim statement itself, which now says precisely what the two layers establish rather than implying a stronger, fully-parallel independence the implementation was never built to provide. Making Phoenix's claims honest and repairing Phoenix are different operations, and only the first was warranted here.

**The `CH-007`/`HC-004` symmetry is worth stating precisely, not just noting:** `CH-007` was a synchronized specification sitting on top of two genuinely defective implementation semantics. `HC-004` is the mirror image — implementation semantics that are entirely correct as built, under a specification whose wording implied more than the architecture was ever designed to deliver. Same five-step gate, same seven families, run against two structurally opposite outcomes. That contrast is itself evidence the methodology discriminates between where a failure actually lives, not merely whether one exists.

---

## CH-004/CH-006: the last remaining loose end closed (2026-08-10)

The one untraced cell across all campaigns this session — Semantic Inflation, left open since before this session began, when `CH-004`/`CH-006` were originally attacked. Closed as a real, applicable finding, not marked n/a for convenience: passing `CH-004`/`CH-006` establishes that a `DecisionRecord`'s `decision_hash` provably traces to a genuine `PolicyDecisionRecord` with matching content on disk — a real provenance link, confirmed by Check 5's own `PG-001`-era hash-equality fix. It does not establish that the underlying policy decision was itself compliant with the real, live policy/capability state at decision time — `policy_hash` and `capability_snapshot_hash` are opaque references, never independently re-derived from actual policy configuration by either check. "Provenance to a real record" and "correctness of that record's own inputs" are different properties; only the former is what `CH-004`/`CH-006` establish. Checked against `HC-004`'s own boundary note (a different composition gap) and `HC-001`/`HC-003`'s existing tamper-evidence language (written for a different claim shape) before concluding this was genuinely distinct, not already covered elsewhere. `[finding: claim-boundary/semantic-inflation issue / disposition: documented limitation]`. No code changed.

With this cell closed, `CH-004`/`CH-006` reaches genuine full seven-family coverage — the **ninth** claim this session, and the first to complete across two separate working sessions (the original six-family attack pre-dating this session, plus this closure) rather than one continuous campaign.

---

## SE-002/SE-003: the first classification/dispatch claim, structurally unlike everything attacked before it

Selected via a fresh matrix-level scan after the `CH-` series was confirmed exhausted (`CH-001` through `CH-008`, all attacked or closed) — the same disciplined elimination as every prior selection: `MB-003` off-limits, everything already closed, `MB-001`/`MB-002` transitively covered via `MB-004`, `CB-002` explicitly "not independent coverage" per its own text, `CH-005`/`DA-001` already ruled structurally poor-fit earlier this session. `HC-002` (a near-duplicate of `HC-001`/`HC-003`'s already-twice-tested single-hash shape) and `SE-004` (narrow, message-enrichment-only) both remained weaker candidates. `SE-002`/`SE-003` — historical schema classification correctness, and recognition-is-not-verification enforced structurally — stood out as genuinely new claim *shape*: not a hash-tamper-evidence claim, not a cross-record-relationship claim, not a composition claim. `VP-001` had touched these same two files earlier this session, but narrowly (one specific dispatch fail-open bug, not a full seven-family campaign against the classification claims themselves).

**Pre-attack gate**, evidence-universe question folded into the existing steps as instructed, not added as a new one: claim and code found synchronized, `VP-001`'s own fix already closing the one staleness gap that existed. The gate itself surfaced the standout composition candidate before any attack began: does a `RECOGNIZED_HISTORICAL_SCHEMA` classification ever leak into *acceptance* in `decision_record_log.py`/`execution_audit_log.py`, outside `SE-003`'s own structural guard (which lives only in `historical_verification.py`)?

**Composition — clean, confirmed by execution.** A genuine pre-generation_id historical payload still correctly raises `DecisionLogCorruptionError` when read through the real log-reading path; classification only enriches the error message, never changes control flow toward acceptance.

**Duplication — a real latent defect, found and fixed.** The real `_classify()` mechanism, tested directly with a deliberately constructed pair of historical schema entries sharing an identical field-name set: the *first* entry in the list silently won, with zero indication the ambiguity existed. Reversing list order flipped which schema name got reported — confirmed pure list-position dependence, not asserted from reading the code alone. Not reachable through any live path today (only one historical schema entry exists per real record type), matching `VP-001`'s own "risk is future code evolution, not adversarial input today" shape exactly. Fixed via `_validate_historical_schemas_are_pairwise_distinct()`, run once at import time for both record types' real constant lists — confirmed the real, live schemas pass cleanly, and the exact colliding construction that succeeded silently before now raises immediately.

**Substitution — clean, confirmed by execution.** A genuine current-schema `DecisionRecord` payload fed directly to the `ExecutionAuditRecord` classifier correctly returns `UNRECOGNIZED` — the two record types' field names genuinely differ, no accidental cross-classifier acceptance.

**Boundary Crossing — n/a, traced.** No generation-scoping concept exists anywhere in this module; `generation_id` is only ever one field name among five in the current schema, never a grouping or comparison axis.

**Omission — a second, distinct real latent defect, kept separate from Duplication per this session's own established discipline for two genuinely different mechanisms sharing a conceptual center.** `classify_*_payload()` had no defensive guard of its own against non-dict input — confirmed by direct execution that `payload.keys()` raised an uncaught `AttributeError` rather than returning a graceful `UNRECOGNIZED`. Both real callers already guarded with `isinstance(payload, dict)` before calling in, so no live path reached this gap — but the function itself was not defensive, relying entirely on every current and future caller remembering to guard first. Fixed: `_classify()` now returns `UNRECOGNIZED` directly for non-dict input.

**Asymmetry — clean, confirmed by tracing real source, not inspection alone.** Both record types' classifiers provably route through one shared `_classify()` helper — the same function, different field-set arguments — ruling out any directional leniency between them by construction. Current-schema and historical-schema matching both use identical exact-`==` frozenset comparison.

**Semantic Inflation — a confirmed genuine positive, named as such rather than left as an empty cell.** Checked whether the docstring's careful three-way epistemic humility for `UNRECOGNIZED` ("could be corruption, could be an unsupported historical schema, could be an unrelated record type — this module doesn't distinguish") survives intact all the way to the actual downstream message a caller sees. It does, verbatim — nothing compressed or overstated along the way.

Both real findings `[finding: implementation defect / disposition: fixed + regression]`, confirmed via execution before and after each fix, 479/479. `SE-002`/`SE-003` is the **tenth** claim this session to reach genuine full seven-family coverage — and, alongside `HC-004`, the second campaign this session to produce zero code-correctness surprises in five of seven families while still surfacing two real, precisely-named defects in the other two, rather than either extreme (a uniformly clean sweep or a uniformly broken one).

---

## CI-001: channel semantic identity — preserved by construction, not by verification

Selected as the next target after re-establishing suite state on a fresh,
non-git-tracked sandbox copy of the repo (474/476 passing outside the
Windows-only Rust-parity file; the two `test_longevity_benchmark.py` timeouts
left explicitly UNRESOLVED at that point — environment/performance
distinction not yet established, not treated as a regression. **Resolved
below, once the real Windows checkout supplied the missing control.**) Framed from the full-repo sweep as
a genuine Boundary-Crossing candidate distinct from every hash-chain claim
attacked so far this session: does Phoenix A actually verify that a channel's
*meaning* survives the Vent→Bridge→Kernel seam, or does the pipeline merely
happen to agree with itself across three independently-hardcoded assumptions?

**Read before attacking, per standing practice.** `VentAdapterContract.process_raw_packet`
builds its `channels` dict from three hardcoded literal keys (`chemical_pH`,
`seismic_amplitude`, `temperature_readings`). `StratifiedTensorPacker.pack_channels_stratified`
sorts channel names alphabetically before packing — position in the 256-dim
output tensor is a pure function of channel-name string ordering, nothing
else. `BridgeIntegrator.verify_and_transform` slices the flat tensor at
hardcoded offsets (`CHANNEL_LAYOUT`: `[0:86]`, `[86:171]`, `[171:256]`) and
labels them `ph_slice`/`seismic_slice`/`temp_slice` by position, not by any
check against the channel name that actually produced that data.
`replay_engine._bridge_frame_to_kernel_frame` concatenates the three named
slices back into one flat array in the same fixed order. A grep across the
kernel and risk-governor modules found zero further channel-specific reads
downstream of that concatenation — the flat payload carries no channel
semantics of its own past this seam.

**Five constructions, run for real, not inferred from reading:**

1. **Insertion-order permutation — clean.** Three differently-ordered dict
   literals with identical key/value content produced byte-identical packed
   tensors. `sorted()` genuinely neutralizes dict insertion order.
2. **Channel rename preserving alphabetical rank — clean.** Renaming each
   channel while keeping its first letter's sort position unchanged left the
   packed positions unchanged; distinctive per-channel marker values landed
   exactly where expected.
3. **Real pipeline, real field names — clean (positive control).** Through
   the actual public entry point, with distinctive markers on each channel,
   `frame.ph_slice[0]`/`seismic_slice[0]`/`temp_slice[0]` matched their
   correct channels every time.
4. **Channel rename that changes alphabetical rank — the finding.**
   Constructed three channels (`aardvark_temperature`, `chemical_pH`,
   `seismic_amplitude`) whose alphabetical order no longer matches
   `CHANNEL_LAYOUT`'s assumed (pH, seismic, temperature) order, and called
   `StratifiedTensorPacker.pack_channels_stratified` directly — bypassing
   `process_raw_packet` entirely, since the packer itself has no name
   restriction. Computed a legitimate provenance hash over the resulting
   tensor with `VentAdapterContract`'s own canonical hash function (no
   forgery — the same function the real system uses) and pushed the result
   through the real, unmodified `BridgeIntegrator.verify_and_transform`.
   **Neither `IntegrityError` nor `SensorStagnationFault` fired.** The
   returned `CoreExecutionFrame.ph_slice[0]` held the temperature marker;
   `seismic_slice[0]` held the pH marker. A validly-shaped, validly-hashed
   frame arrived with scrambled semantic labels, and every local integrity
   check passed.
5. **Reachability and downstream-consequence check.** Confirmed by reading
   `process_raw_packet`'s source directly (not assumed) that no caller-
   supplied channel name can reach the packer through the real public API —
   the three keys are hardcoded literals, full stop. Then confirmed by
   execution that the Finding #4 mislabeling *does* propagate into the final
   Kernel `payload` array rather than being cancelled out by `replay_engine`'s
   symmetric slice/reassemble — the clean and mislabeled payloads diverge
   starting at index 0.

**The precise architectural distinction this establishes, stated as the
finding rather than as a live defect:** the production path preserves channel
semantic identity *by construction* — a fixed, hardcoded set of three channel
names feeding a deterministic sort — not by any check that would catch a
future violation. **Integrity of the tensor does not establish semantic
identity of the tensor's regions.** A SHA-256 over the packed tensor proves
this is exactly the tensor that was hashed; it cannot prove the first 86
elements are actually pH. This is a materially different — and more
accurate — claim than "the pipeline has a live channel-confusion bug." It
doesn't. But nothing currently stands between today's closed, correct
production path and tomorrow's silent corruption if `pack_channels_stratified`
is ever called from a second call site, or if `process_raw_packet`'s
literal-key restriction is ever relaxed to accept configurable channel names.

`[finding: claim-boundary/architectural-risk / disposition: documented
limitation — no code changed]`. Deliberately not fixed: adding a verification
step to a boundary that is currently closed by construction would mean
solving a problem the real, deployed system doesn't have today, at the cost
of implying the packer's public surface is meant to be called with arbitrary
channel sets, which it isn't. The correct disposition is the same one used
for `HC-004`: make the claim state precisely what the architecture
guarantees, rather than rewrite working code to match an inflated claim.

`CI-001` is the **eleventh** claim this session to reach a fully-traced
disposition, and the first whose attack surface lives at the Surface/Bridge
seam rather than inside the hash-chain claims (`HC-`/`CH-`/`PG-`/`MB-`
territory) or the classification/dispatch shape (`SE-002`/`SE-003`) — a third
genuinely distinct claim *shape* this session, after cross-record-relationship
and classification/dispatch.

---

### `test_longevity_benchmark.py` — UNRESOLVED to RESOLVED/ENVIRONMENTAL

The two timeouts flagged at session start (`test_short_longevity_burn_in_memory_stability`,
`test_full_longevity_burn_in_100k`, both failing at pytest-timeout's 60s
ceiling inside `StratifiedTensorPacker.pack_channels_stratified`, in the
Linux sandbox only) are now closed with a real control, not assumed clean by
default. The same two tests, same code, ran to completion with no timeout in
the actual `pytest -v` full-suite run on the real Windows checkout
(`579.89s`/`9:39` total wall time for the full 479-test suite, both
longevity tests reporting `PASSED`). `ARCHITECTURE_FREEZE_v1.5.md` already
documents that this benchmark is deliberately kept out of the fast/CI suite
and run only via a separate nightly/manual workflow — independent
confirmation that it was always expected to be resource-heavy, not that
something regressed.

**Classification: RESOLVED / ENVIRONMENTAL.** The Linux sandbox's 60-second
per-test ceiling was the cause, not Phoenix A's execution path — same code,
same inputs, real hardware difference (or resource ceiling) between the two
environments. **This is not evidence of a Phoenix A performance regression,
and is not evidence the benchmark passes cleanly under load in general** —
only that the specific sandbox timeout observed at session start had an
environmental cause, confirmed by a real control run rather than inferred.

**Test-result classification, stated explicitly per this session's own
bookkeeping standard** (four distinct states, not collapsed into pass/fail):
`actual failure` (assertion or exception on real logic) / `actual
performance problem` (real code is too slow under its own real constraints)
/ `environment limitation` (this case — sandbox resource ceiling, not code)
/ `not tested` (no attempt made). Leaving a result in an undifferentiated
UNRESOLVED state is itself a small ledger gap — worth naming and closing
explicitly rather than letting it sit as ambiguous "some test somewhere
failed" residue.

---


## Attack campaigns, not "the next N attacks"

One claim can take multiple attacks from different families; the useful unit of coverage is the (claim, family) pair, not a flat attack count. First-pass coverage matrix — **not exhaustive by design**, populated only with what's actually been run:

| Claim | Orphan | Asymmetry | Substitution | Omission | Duplication | Boundary crossing | Semantic inflation |
|---|---|---|---|---|---|---|---|
| CH-001 (decision ancestry) | ✓ found→fixed (Check 6) | ✓ found→fixed (Check 6) | ✓ clean, structural (no shared content beyond join key) | ✓ found→fixed (Check 7) | ✓ found→logged (duplicate audits, same as CH-004/6) | ✓ found→fixed (Check 1, earlier) | ✓ found→documented |
| CH-003 (module identity cross-reference) | — | — | — | ✓ found→documented (`GAP-005`, schema-level) | — | — | — |
| CH-002 (sequence ordering) | — | — | — | — | — | ✓ found→fixed (superseded an earlier premature clean verdict — see write-up) | — |
| CH-004/CH-006 (policy provenance, both directions) | ✓ found→fixed | ✓ found→fixed | ✓ clean (`test_swapped_...`) | ✓ found→fixed (`checks_run`) | ✓ found→logged (evidence ceiling reached, stays logged) | ✓ clean (generation-mismatch tests) | ✓ found→documented, closed 2026-08-10 (provenance to a real record ≠ correctness of that record's own opaque inputs — `policy_hash`/`capability_snapshot_hash` never independently re-derived — see write-up) |
| SE-002/SE-003 (historical schema classification, recognition-is-not-verification) | ✓ n/a, traced fresh (no composed edges — leaf/single-record-type claim) | ✓ clean, confirmed by execution (both real classifiers provably share one symmetric `_classify()` helper) | ✓ clean, confirmed by execution (cross-record-type payload correctly `UNRECOGNIZED`) | ✓ found→fixed, confirmed by execution (`classify_*_payload()` had no guard of its own against non-dict input, relying entirely on both real callers already checking first — fixed with a direct guard) | ✓ found→fixed, confirmed by execution (two historical schemas sharing an identical field set silently resolved by list order — fixed with an import-time uniqueness assertion) | ✓ n/a, traced fresh (no generation-scoping concept exists in this module) | ✓ confirmed genuine positive, not merely absent (the docstring's three-way `UNRECOGNIZED` epistemic humility survives verbatim to the real downstream message) |
| HC-001 (registration hash) | ✓ clean (no composition structure — leaf claim, nothing for an edge to dangle from) | ✓ clean (write path never persists `attempt_hash` at all; read path always recomputes via the real constructor at every layer — traced through `module_registration_audit.py`, `module_registration_audit_persistence.py`, `module_registration_audit_log.py`) | ✓ found→documented (binding can be entirely absent, not just collision-prone) | ✓ found→documented | ✓ clean (log-level duplicates are independently tamper-evident entries; no dedup/collapse logic exists that the claim depends on) | ✓ clean (no `generation_id` on this record type by design; no historical schema variants either, per `SE-002`'s own boundary note) | ✓ found→documented (compound with `GAP-005`) |
| HC-003 (audit hash) | ✓ clean (`audit_hash` not used as a join key/reference anywhere in this codebase — no edge for an Orphan attack to target) | ✓ clean (write path never persists `audit_hash`; read path always recomputes via the real constructor — traced through `execution_audit_persistence.py` and `execution_audit_log.py`) | ✓ clean (all three opaque references — `input_hash`/`prior_state_hash`/`output_hash` — traced individually; each validated only as a well-formed digest, never as the *correct* hash for a genuine upstream object, same internal-consistency boundary already documented, now confirmed for all three explicitly rather than one) | ✓ clean (resolved 2026-08-07) | ✓ clean (log-level duplicates independently tamper-evident, no dedup logic the claim depends on) | ✓ clean (`generation_id` participates in `audit_hash`'s own derivation, confirmed directly in `execution_audit_persistence.py`'s docstring — tampering with it is caught exactly like any other field, no boundary for a single record's own tamper-evidence to cross) | ✓ clean (existing boundary text's "internal consistency, not external authenticity" framing already forecloses the inflation risk; no new angle found) |
| MB-002 (segmentation) | — | — | — | ✓ clean | ✓ clean | ✓ clean (malformed transitions) | — |
| MB-003 (cross-generation) | — | — | — | — | — | (this claim *is* a boundary-crossing theorem) | ✓ found→documented |
| PG-001 (graph model itself) | ✓ found→fixed (Check 5 added 2026-08-06, pre-session — see `PROVENANCE_GRAPH_MODEL.md`'s "Second finding") | ✓ same finding as Orphan, cross-referenced not double-counted (root cause was the asymmetry, artifact was the orphan) | ✓ found→fixed (Check 5 verified key co-occurrence only, not decision identity; found and fixed 2026-08-08, confirmed via direct construction and execution both before and after the fix — see write-up) | ✓ clean, confirmed via direct construction and execution against the REAL `verify_causal_history()` (a `PolicyDecisionRecord` for a deliberately unregistered module, satisfying everything Check 4/5 need — Check 3 catches it directly, since the same `DecisionRecord` object is visible to every check in the same pipeline run — see write-up) | ✓ clean, confirmed via direct construction and execution (real duplicate `DecisionRecord`s at a shared key, a real orphan hidden among the noise, correctly isolated with exactly one failure — see write-up) | ✓ clean, confirmed via direct construction and execution (a real `decision_hash` collision built across two genuine generations; confirmed the compound `(sequence_id, generation_id)` dict key prevents the collision from ever reaching the hash-comparison stage — see write-up) | ✓ found→documented (graph-level document never carried forward `CH-001`'s own "key co-occurrence, not content correlation" caveat to the composed-graph claim — see write-up) |
| CB-001 (cold boot reconstruction) | ✓ found→fixed (`reconstruct_cold_boot()` double-read the three logs — once directly, once inside `verify_causal_history()`'s own internal re-read — with no invariant connecting the two; confirmed via adversarial construction and execution that a caller could receive `reconstruction_valid=True` over a returned history never fully validated; fixed via single-read/shared-snapshot semantics, `verify_causal_history_from_records()` — see write-up) | ✓ n/a, traced not assumed (no new cross-record relationship exists at this composition layer distinct from `PG-001`'s already-exhaustive coverage of the underlying checks — five candidate angles considered and ruled out — see write-up) | ✓ clean, confirmed via real file I/O and genuinely swapped log paths through the real `reconstruct_cold_boot()` (schema-shape validation one layer down catches it — specific `DecisionLogCorruptionError` naming the exact missing field and classification detail) | ✓ found→documented (`reconstruction_valid` depends on all six unconditionally-run checks, the contract originally named only two — see the earlier `CB-001` "Finding" section) | ✓ clean, confirmed via execution (the same real path passed to all three parameters triggers the identical schema-mismatch protection as Substitution) | ✓ clean, confirmed via a real, deliberate multi-generation history (`sequence_id` legitimately resetting across two generations — both generations' records correctly present, `reconstruction_valid=True`, zero failures, no false conflation) | ✓ same finding as Orphan, cross-referenced not double-counted (`reconstruction_valid` could be over-read as covering the full returned history — the two-read design never guaranteed that) |
| CH-007 (decision execution completeness) | ✓ clean (leaf check, two flat lists, no composed structure of its own — same shape as `HC-001`/`HC-003`) | ✓ clean, traced fresh against real source (the hypothesized `CH-001`/`CH-007` strict-vs-lax split does not exist — `CH-001` uses the identical set-membership logic, confirmed directly from its own body, not the matrix's summary language) | ✓ found→fixed, Finding #1 (the trailing exemption compared each decision's `sequence_id` against the group's max value only, never asking whether that max was uniquely held — two allowed decisions sharing it both received the exemption, one genuinely incomplete; fixed by requiring unique occupancy — see write-up) | ✓ found→fixed, Finding #2, confirmed distinct from Finding #1 (evidence of continuation was computed only over allowed decisions — a denied decision at a later `sequence_id`, real proof the engine reached that frame, was invisible to the check; fixed by computing the true last position over all decisions — see write-up) | ✓ clean, confirmed via execution (same real path to all three parameters, multi-module sharing a sequence, duplicate audits — all behave correctly) | ✓ clean, confirmed via a real, deliberate generation-transition construction (a genuine `sequence_id` collision built across two generations — independent groups correctly stay independent) | ✓ documented as a claim-boundary caveat tied to the two fixes above (passing means no *non-exempt, non-ambiguous* incomplete decision was found, not that none was ever silently abandoned) |
| CH-008 (no contradictory decisions) | ✓ n/a, traced fresh (leaf/single-record-type claim, no composed edges — the first non-cross-record claim attacked this session) | ✓ n/a, traced fresh (`allowed_keys`/`denied_keys` built by identical, symmetric logic from the same input list — no directional relationship exists) | ✓ clean, confirmed via execution (same-`decision_hash` and different-`decision_hash` contradictions both caught identically) | ✓ clean, confirmed via execution (composition probe against `CH-007`'s fresh terminal-boundary fix — both checks fire independently with zero interference, the unique allowed decision at the contradictory key correctly not double-flagged) | ✓ clean, confirmed via execution (multiple denied records fabricated at one key still correctly detected, though reported at key- not record-granularity — see Semantic Inflation) | ✓ clean, confirmed via execution (different-generation keys correctly stay independent) | ✓ found→documented, two substantive observations not a generic caveat (message doesn't distinguish same-hash from different-hash contradiction; reporting is at key granularity, one fabricated record and thirty produce the identical single failure — see write-up) |
| HC-004 (PolicyDecisionRecord's two hash layers) | ✓ n/a, traced fresh (leaf record, no composed edges of its own; the one real composition question, `CH-003` + `HC-004`, confirmed to be the same question already answered by `PG-001`, not assumed equivalent) | ✓ found→documented, confirmed by execution across multiple variants (the chain is strictly one-directional — `decision_hash`-scope changes always propagate to `entry_hash`, `entry_hash`-scope changes never propagate back; cross-referenced with the Semantic Inflation finding below, not a second independent defect) | ✓ clean, confirmed via `inspect.signature` (neither `entry_hash` nor `decision_hash` can even be attempted as a constructor argument — `field(init=False)` structurally enforced, not merely read from the class definition) | — (leaf hash-tamper-evidence claim; no omission surface distinct from the Semantic Inflation finding) | ✓ clean, confirmed via execution (two independently-constructed records from identical inputs produce identical hashes with no cross-instance state or collapse; log-level duplication is `CH-004`/`CH-006`/`PG-001` territory) | ✓ clean, confirmed via execution (`decision_hash` correctly unaffected by `generation_id`; `entry_hash` correctly distinguishes generations) | ✓ found→documented, the campaign's headline result, confirmed by direct construction (outer-only and inner-only tampering both change `entry_hash` identically — only `decision_hash`, checked separately, discriminates which layer was corrupted; "independently tamper-evident" holds in the narrow sense, not the stronger one a reader might assume — claim wording corrected, no code changed) |
| MB-004 (candidate lineage construction) | ✓ clean (three mechanisms jointly close it — see Eleventh finding) | ✓ found→documented (list position trusted as chronological order, unprovable under current schema — see Twelfth finding, Corollary to Theorem 2) | ✓ found→fixed (adjacent segments sharing a `generation_id` now rejected, `PG-001` precedent) | ✓ found→fixed (segment/result cross-check added, same precedent) | ✓ found→fixed (non-adjacent duplicate `generation_id` now rejected via global-uniqueness pass, subsuming the earlier adjacent-only check — see Thirteenth finding) | ✓ found→fixed (segment-label-vs-content mismatch, root cause in Phase 2, same precedent) | ✓ found→documented (ordering caveat added to module docstring, parallel to the existing identity-continuity caveat — see Fourteenth finding) |

Legend: **found→fixed** = real gap, closed with regression test. **found→pending** = real finding, disposition decided but not yet built/resolved. **found→documented** = real, correctly-scoped limitation, now written down. **clean** = attacked, survived, often confirming existing documentation. **⚠ blocked** = attack designed, execution blocked pending a fact-check this methodology refuses to skip. **—** = not yet attempted; absence of evidence, not evidence of absence.

This shorthand predates, and is preserved unchanged by, the formal ATTACK RESULT / DISPOSITION taxonomy introduced above — each finding's full write-up now also carries its two-axis tag; the matrix cells themselves are left in their original shorthand rather than retrofitted cell-by-cell, since the shorthand already cross-references each finding's full entry.

The empty cells are the actual backlog now, not a vague "keep going."

---

## Explicitly out of scope for this document

- No code changes beyond the one small `MB-003` documentation addition already made.
- HC-003 is resolved (2026-08-07) — see above. No longer out of scope.
- Duplication (CH-004/CH-006) — decided 2026-08-08: stays logged, not built. The production persistence call site that would settle the retry-legitimacy question outright isn't in this sandbox, and that fact-finding is now exhausted, not merely paused.
- The omission and duplication findings against CH-004/CH-006 are logged, not fixed — no decision made here about whether uniqueness assertion is worth adding to either check, or whether `checks_run` is worth building.
- No claim that seven families is an exhaustive taxonomy — it is the set that explains every finding made so far, not a proof that no eighth family exists.

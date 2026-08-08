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

## Two additional findings, surfaced by applying Omission and Duplication to CH-004/CH-006

Not requested, but a natural extension once the taxonomy existed — applying two of the seven families to the two directional checks just built.

**Omission — resolved 2026-08-08.** `verify_causal_history()`'s own docstring states the deliberate contract explicitly: `passed=True` means *all requested checks passed*, not *all applicable checks passed* — "behavior is IDENTICAL to before Check 4 existed." The distinguishing signal (`policy_decision_record_count` staying `None` when Checks 4/5 didn't run) already existed and was already documented — the finding was never that no signal exists, only that it's *indirect*: a caller checking only `.passed`, the obviously-named field, would never notice it. Built: `checks_run: FrozenSet[str]`, populated with a stable string identifier for every check that actually executed, always including the six that always run, plus the two optional ones when `policy_decision_log_path` is supplied. This adds no new information over what `policy_decision_record_count` already implied — it adds discoverability: a field literally named `checks_run` doesn't require already knowing the indirect inference. Two regression tests confirm the exact set in both the with- and without-policy-log cases. **[finding: implementation defect / disposition: fixed + regression]** — a mild one (adds discoverability, not new information), but still a concrete code change with a regression test, not a documentation-only outcome.

**Duplication — decision made 2026-08-08: stay logged, not built. This is a resolved "insufficient evidence to act" state, not an unresolved one.** Check 4's matching logic (`policy_by_key.setdefault(key, []).append(p)`, then `any(...)` over the matches) accepts *any* number of matching `PolicyDecisionRecord`s at a given key — it asserts "at least one," never "exactly one." A duplicated, byte-identical `PolicyDecisionRecord` appended twice would pass Check 4 without comment. The retry-legitimacy investigation (2026-08-07) checked every file with sandbox access to the append path — `policy_decision_record_log.py` (its own docstring explicitly disclaims "crash safety, atomic writes, or concurrent-writer coordination... those remain separate, harder questions"), and `deterministic_execution_engine.py`, which never calls `append_policy_decision_record()` (or any `append_*`) at all — it only builds in-memory lists; real persistence happens outside this file. No other file in the sandbox calls any `append_*` function except tests setting up fixtures. **That investigation was already exhausted — there is no further fact-finding available without the production persistence call site, which genuinely isn't in this sandbox and cannot be requested without knowing what file it would even be.** The honest conclusion stands exactly where it was left: no retry logic exists anywhere in accessible code, narrowing the risk to "a bug in an unseen caller, or deliberate fabrication" — but this does not amount to evidence that duplicates are categorically impossible in the real architecture, and tightening to "exactly one" without that evidence risks breaking a legitimate pattern this project simply cannot see. **Decision: remain at "logged, not built." This is the responsible conclusion given the actual evidence ceiling, not a deferred one** — revisiting it would require new source material, not more analysis of what's already here. **[finding: insufficient evidence / disposition: logged / pending evidence]**

---

## Attack campaigns, not "the next N attacks"

One claim can take multiple attacks from different families; the useful unit of coverage is the (claim, family) pair, not a flat attack count. First-pass coverage matrix — **not exhaustive by design**, populated only with what's actually been run:

| Claim | Orphan | Asymmetry | Substitution | Omission | Duplication | Boundary crossing | Semantic inflation |
|---|---|---|---|---|---|---|---|
| CH-001 (decision ancestry) | ✓ found→fixed (Check 6) | ✓ found→fixed (Check 6) | ✓ clean, structural (no shared content beyond join key) | ✓ found→fixed (Check 7) | ✓ found→logged (duplicate audits, same as CH-004/6) | ✓ found→fixed (Check 1, earlier) | ✓ found→documented |
| CH-003 (module identity cross-reference) | — | — | — | ✓ found→documented (`GAP-005`, schema-level) | — | — | — |
| CH-002 (sequence ordering) | — | — | — | — | — | ✓ found→fixed (superseded an earlier premature clean verdict — see write-up) | — |
| CH-004/CH-006 (policy provenance, both directions) | ✓ found→fixed | ✓ found→fixed | ✓ clean (`test_swapped_...`) | ✓ found→fixed (`checks_run`) | ✓ found→logged (evidence ceiling reached, stays logged) | ✓ clean (generation-mismatch tests) | — |
| HC-001 (registration hash) | — | — | ✓ found→documented (binding can be entirely absent, not just collision-prone) | ✓ found→documented | — | — | ✓ found→documented (compound with `GAP-005`) |
| HC-003 (audit hash) | — | — | — | ✓ clean (resolved 2026-08-07) | — | — | — |
| MB-002 (segmentation) | — | — | — | ✓ clean | ✓ clean | ✓ clean (malformed transitions) | — |
| MB-003 (cross-generation) | — | — | — | — | — | (this claim *is* a boundary-crossing theorem) | ✓ found→documented |
| PG-001 (graph model itself) | ✓ found→fixed | ✓ found→fixed | — | — | — | — | — |
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

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

## The meta-principle this methodology already proved about itself

**Claims, models, and implementations are all attack surfaces — not just implementations.** Check 5's finding wasn't only an implementation gap; `PROVENANCE_GRAPH_MODEL.md` itself named a composition mechanism ("composing through `DecisionRecord`") that didn't actually exist yet. The model was wrong, not just incomplete. That means this methodology has to periodically attack its *own* documents — `PROVENANCE_GRAPH_MODEL.md`, `MODE_B_CLAIMS_REGISTRY.md`, `VERIFICATION_COVERAGE_MATRIX.md`, and this file — the same way it attacks code, on the theory that a formal model describing a graph an adversary is meant to reason against is itself a claim that can be false.

The corollary for this document specifically: it must hold itself to the verification standard it's formalizing. `HC-003` staying flagged rather than resolved is not a gap in this methodology's output — it *is* the methodology's output, working correctly. A version of this document that speculated about `HC-003` to look more complete would itself be an instance of semantic inflation.

---

## First wave of applied attacks

Five claims, as raised. Verdicts vary deliberately — this is meant to show the methodology's actual output distribution, not a curated set of wins.

### HC-001 — real finding, not previously stated this precisely
**Attack:** can I change something that matters operationally but isn't included in `attempt_hash`?
`ModuleRegistrationAttemptRecord` persists `manifest_hash` — a *reference* to the declared manifest, not the manifest's content, and certainly not the actual loaded module code. Two structurally different module implementations that happen to declare identical capabilities and `runtime_api` version would produce the same `manifest_hash`, and `HC-001`'s tamper-evidence says nothing about which one actually ran. **This is the same "internal consistency, not external authenticity" boundary `REPLAY_GENERATION_MODEL.md`'s Theorem 1 already states for hash chains generally — but it had never been stated for `HC-001` specifically.** Not a bug; a boundary worth adding to `HC-001`'s row in `VERIFICATION_COVERAGE_MATRIX.md`. Disposition: formally document limitation.

### HC-003 — RESOLVED 2026-08-07 against real source, not guessed
**Attack:** are there semantically important fields excluded from `audit_hash`'s coverage?
Originally flagged, not guessed at — resolved once `execution_audit_contract.py` was actually read. **Result: no field is excluded.** `_compute_audit_hash()` hashes all 9 fields, confirmed directly (`generation_id` and `frame_timestamp_ns` both included, not assumed). Deterministic metrics specifically: `output_hash = result.module_hash`, and `ExecutionResult.module_hash` (`execution_module_contract.py`) already bakes in the filtered, sorted, deterministic subset of `metrics` before `ExecutionAuditRecord` ever sees it — covered transitively, via the same opaque-hash-reference pattern every field in this record uses, not by `ExecutionAuditRecord` inspecting metrics directly. The one real, now-precisely-grounded boundary: `__post_init__` validates `output_hash` is a well-formed 32-byte digest, never that it's the *correct* `module_hash` for a genuine `ExecutionResult` — internal consistency, not external authenticity, same as everywhere else in this hash chain. Disposition: documentation confirmation, refined with the verified mechanism (`VERIFICATION_COVERAGE_MATRIX.md` updated).

### CH-002 — SUPERSEDED 2026-08-07: the "clean pass" verdict was premature
**Original attack:** can I construct a history that is globally nonsensical while remaining locally ordered? Yes — two engines' records interleaved in one log file, each internally sequence-ordered, with `frame_timestamp_ns` values that contradict the interleaving. Check 2 doesn't catch this, but `CH-002`'s Boundary column already stated exactly that limitation, so this was recorded as documentation confirmation.

**That verdict was too narrow, not wrong on its own terms but incomplete.** `sequence_id` obviously interacts with generation boundaries — that's the whole axis Check 1's fix and Check 6 both operate on — and Boundary Crossing was never actually tried against `CH-002` specifically, even though it had just been used successfully against `CH-001`. The real gap (below) was found by accident, via a Check 6 test, not by this methodology's own deliberate coverage. **Worth recording honestly: a "clean pass" only means the attacks actually run found nothing — not that every relevant attack was tried.** The campaign matrix's empty cells are the backlog for exactly this reason; this is the first concrete case of a filled cell turning out to have been filled too early.

**Real finding, fixed:** `_check_sequence_ordering()` tracked `last_seen` keyed purely by `module_id`, with zero `generation_id` awareness — the identical class of gap Check 1 had before its own fix, but more severe in consequence: Check 1's gap needed a coincidental cross-generation collision to misfire; this one fired **unconditionally on every administrative reset**, since `sequence_id` legitimately resets to 0 each time. Any real multi-generation history for the same module — not an adversarial construction, ordinary healthy operation — would have been guaranteed a false "out of causal order" violation. Fixed by scoping the join key to `(module_id, generation_id)`, mirroring Check 1's and Check 6's shape. Two new regression tests: the exact false-positive scenario (`test_sequence_numbering_resetting_across_a_real_generation_boundary_is_not_flagged`) and a sanity check that genuine within-generation violations are still caught.

Disposition: fix + regression test. Reclassifies from "documentation confirmation" to "found→fixed," Boundary Crossing family.

### MB-002 — clean pass across five sub-attacks
**Attack:** missing records, duplicate sequence_ids, empty segments, boundary records, malformed transitions — does segmentation accept any impossible pattern?
- *Missing records (a sequence_id gap within one segment):* accepted by `segment_by_generation()` — it never checks sequence continuity. **Correctly layered, not a gap**: Phase 2's replay enforces monotonic sequencing via the real `KernelStateMachine` (`test_non_monotonic_frame_execution_rejected`), so a genuine gap fails at Phase 2, not silently at Phase 1.
- *Duplicate sequence_id within one segment:* same answer — Phase 1 doesn't check it, Phase 2's replay does.
- *Empty segments:* structurally impossible by construction — `segment_by_generation()`'s algorithm never flushes an empty batch.
- *Boundary records (empty history, single-record history):* already tested directly (`test_empty_history_returns_empty_list`, `test_single_generation_returns_one_segment`).
- *Malformed `generation_id` (wrong length/type):* caught earlier, at `ExecutionAuditRecord`'s own construction validation — correctly out of Phase 1's scope.

No new findings. This is the "found nothing, and that's useful evidence" case the methodology predicted might happen — five sub-attacks, five confirmations that the layering between Phase 1 and Phase 2 is where it should be. Disposition: documentation confirmation (all five).

### MB-003 — real epistemic risk, semantic inflation family
**Attack:** can any implementation accidentally turn an unknowable relationship into a claimed one?
Not in current code — `CandidateLineageEdge.explanation()`'s wording is disciplined ("PLAUSIBLE, not proven"), and no aggregation or confidence-scoring exists to inflate. **But there is a real naming risk for future code built on top of this:** `SegmentVerificationResult.fully_verified` proves only within-segment continuity (Theorem 1). Nothing in that property's name warns a future integration — a dashboard, a report generator, an alerting layer — against reading "both adjacent segments are `fully_verified`" as implying the *boundary between them* is also verified, when `MB-003` explicitly says it structurally cannot be. This is the most realistic risk in the whole Mode B design: not that current code overclaims, but that a future caller could misread two true, narrow statements as implying a third, false, broader one. Preventive note added to `MODE_B_CLAIMS_REGISTRY.md`'s `MB-003` entry. Disposition: formally document limitation (done).

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

Disposition: formally document limitation (`GAP-005` added, both documents updated with the corrected classification), not fixed.

---

## Fourth finding: CH-001's mirror image — fixed with Check 6

**Attack (Orphan + Asymmetry, CH-001):** if every `ExecutionAuditRecord` must have a corresponding `DecisionRecord`, can a `DecisionRecord` exist without the corresponding audit record? This was predicted before the attack ran: the same directionality pattern that made Check 5 productive against `CH-004` was applied deliberately to `CH-001`, on the theory that a high-information attack beats random test generation.

Traced directly against `deterministic_execution_engine.py`'s real `process_frame()` (2026-08-07), not guessed: `DecisionRecord` (`allowed=True`) is appended to the decision log **unconditionally**, before `module.execute()` is ever called. Any uncaught exception from `module.execute()` — a genuine module bug, or a deliberately hostile module — means the line constructing `ExecutionAuditRecord` never runs. The live kernel correctly transitions to `FAULTED` (`process_frame()`'s own catch-all `except Exception` handler), but nothing backfills an audit record for the frame that never completed. The allowed decision stays persisted, permanently, with no matching audit record — invisible to Checks 1 through 5, since Check 1 only ever iterates `audit_records` checking each has a matching decision, never the reverse.

**A real nuance, caught before it became a false-positive bug:** not every allowed-decision-with-no-audit is wrong. If `module.execute()` throws, there genuinely is nothing to build an audit record *from* — no `ExecutionResult` was ever returned. The *last* allowed decision for a `(module_id, generation_id)` having no audit record is the legitimate "execution crashed, nothing came after" case — directly mirroring `kernel_state_replay.py`'s own `KernelReplayReport.fully_verified` property, which already treats a history that legitimately ends at a fault as fully verified. What's actually wrong is a missing audit record *with later decisions or audits for the same module/generation proving execution continued past it* — that's demonstrably not a trailing crash.

**A second nuance, applying an earlier lesson to new code rather than repeating the mistake it came from:** the "last decision" computation is scoped per `(module_id, generation_id)`, not `module_id` alone — grouping by module only would wrongly flag a legitimate trailing-crash decision in one generation just because a *later* generation reused the same module successfully. That's the exact class of cross-generation conflation Check 1's original fix closed, and it would have been silently reintroduced here without this scoping.

**Fix:** Check 6 (`_check_decision_execution_completeness`) added to `causal_history_verifier.py`, always runs (not optional, unlike Checks 4/5 — it only needs the two always-available logs). Four new tests: the core mid-stream-gap attack (`test_mid_stream_decision_with_no_audit_is_caught`), the trailing-exemption clean case (`test_trailing_decision_with_no_audit_is_not_flagged`), the generation-scoping proof (`test_trailing_exemption_is_scoped_per_generation_not_globally` — the specific test designed to catch the bug this fix's own design was built to avoid), and a trivial single-decision sanity check.

Disposition: fix + regression test (matching Check 1 and Check 5's precedent — a real finding gets the same discipline as any bug, not deferred as future work because it came from a review pass).

---

## Fifth finding: HC-001's authenticity gap can be total, not partial — verified against real source

**Attack (Substitution family, continuing HC-001's coverage):** the original `HC-001` finding established that `manifest_hash` is a *reference*, not the manifest's content — two different implementations declaring identical capabilities could collide on one hash. That finding assumed a `manifest_hash` exists to collide on. This attack checks a sharper question: does the binding have to exist at all?

Verified directly against `module_registration_audit.py` (2026-08-07, not inferred from test names): `manifest_hash: Optional[bytes] = None`, and `__post_init__` only validates the field's shape *if it is present* — there is no cross-check requiring `manifest_hash` when `success=True`. A registration attempt with `success=True` and `manifest_hash=None` is fully valid and passes every check this record type has. The source docstring confirms this is deliberate: *"not every caller will have a manifest hash on hand, and this field existing or not does not change the validity of the record."*

**What this means precisely:** a successful `ModuleRegistrationAttemptRecord` can carry **zero cryptographic reference to any manifest at all**. `CH-003` would still treat it as valid registration evidence for any later decision/audit record citing that `module_id` — with nothing, not even an imperfect hash, connecting the registration to what actually got loaded. This is a strictly stronger gap than the original finding: not "the binding could theoretically collide," but "the binding can be absent by design."

**What this does NOT mean:** `attempt_hash` itself is not weakened — `HC-001`'s core claim (tamper-evidence across every field) remains fully true even when `manifest_hash` is `None`; the absence is hashed as an explicit sentinel byte, same as every other optional-but-absent field in this codebase's pattern. This is a completeness boundary on what the record can attest to, not a defect in what it does attest to.

**Not proposed as a fix.** The source docstring states this is deliberate, not an oversight — making `manifest_hash` required would be a real behavior change contradicting an explicit design decision, and I don't know how many real callers rely on being able to omit it. Matches `HC-001`'s original disposition: formally document limitation, not fix.

**Compound semantic-inflation risk, worth naming alongside `GAP-005`:** a future dashboard or report showing "module X: registration verified" could easily be read as "module X's identity is cryptographically confirmed" — when in fact (a) the registration may carry no manifest binding at all, per this finding, and (b) even a well-formed registration says nothing about whether the module was later retired or faulted, per `GAP-005`. Two narrow, individually-accurate claims compounding into a false broad one is exactly the shape `MB-003`'s semantic-inflation warning was written to prevent — the same discipline applies here.

Disposition: formally document limitation (`VERIFICATION_COVERAGE_MATRIX.md`'s `HC-001` row updated with the precise mechanism; the original matrix row had never actually been updated with the first `HC-001` finding either, corrected in the same pass).

---

## Sixth finding: MB-004 never verified its own most basic precondition (Substitution family)

**Attack (highest-information empty cell in the campaign matrix, selected deliberately):** `MB-004` had zero attempted families before this — flagged by the GPT dispatch as high-value and confirmed by inspection to be genuinely untested, unlike every other row with at least one attempt. Applying the directionality lesson that made `CH-006` and `CH-007` productive (2/2 hit rate this session): does `construct_candidate_lineage()` verify every precondition it depends on, the same way it verifies the one it already defends?

Verified directly against `candidate_lineage_construction.py`'s real source (2026-08-08): the function raises `ValueError` if `segments` and `verification_results` have mismatched lengths — a defended precondition. But it never checked a comparably load-bearing one: that adjacent entries in `segments` actually represent *different* generations. `generation_segmentation.py`'s `segment_by_generation()` structurally guarantees this for real Phase 1 output — that's what makes two list entries separate segments in the first place — but `construct_candidate_lineage()` itself never re-verified it, trusting the caller completely on this one specific point while explicitly not trusting them on the length point.

**Concrete construction:** two genuinely valid, independently-verified segments (both real, correctly hash-chained, both `fully_verified=True`) that happen to share one `generation_id`, assembled as adjacent list entries — bypassing `segment_by_generation()` entirely. Before the fix, this silently produced a `CandidateLineageEdge` with `from_generation_id == to_generation_id`: not a data-integrity failure (nothing here is tampered with), but a "boundary" that doesn't represent any real generation transition at all, presented via `.explanation()` exactly as if it were a genuine candidate transition.

**Disposition, following the `PG-001` precedent directly:** this is adversarial-fabrication-only — Phase 1 itself can never produce this input in the normal pipeline. That was true of the original `PG-001` orphan finding too, and this project's standing answer is the same one given there: an adversarial-only finding still gets fixed with the same discipline as an operational bug, not merely documented, because "not currently exploitable through the normal pipeline" and "not exploitable at all" are different claims, and this function is a public API a caller could call directly. Fixed with a `raise`, matching the existing length-check's own pattern exactly. New regression test: `test_adjacent_segments_sharing_a_generation_id_raise_value_error`, built from two real engine runs (not fabricated data), confirming the malformed pair is rejected outright.

---

## Seventh finding: CH-001's Omission surface — a contradictory decision pair goes unweighed

**Attack (Omission family, deliberately targeting CH-001's remaining blank cell):** `CH-001` had Boundary Crossing and Orphan/Asymmetry both attacked and fixed already; Omission was the one family left untried, and the claim's own subject matter — "every audit has a corresponding decision" — points directly at it: what evidence required for that relationship can disappear while the verifier still passes?

Traced against `_check_decision_ancestry()`'s real source: the match condition is `if key in denied_keys and key not in allowed_keys` for the denied-only case, falling through to `elif key not in allowed_keys` otherwise. **A key present in *both* `allowed_keys` and `denied_keys` simultaneously satisfies neither branch** — the first requires the key's *absence* from `allowed_keys`, the second requires the same. The audit is silently accepted as validly matched. The denial evidence doesn't get weighed against the allowed decision; it disappears from consideration the instant any allowed decision exists at that key, regardless of a contradictory denial sitting right next to it.

**Why this is a real, not merely theoretical, gap:** in normal operation, exactly one decision is ever made per frame — a key can never legitimately appear in both sets. The only ways to produce this state are a genuine data-integrity failure or deliberate fabrication: append one fake `allowed=True` `DecisionRecord` at the same key as a real denied one, and the entire verifier treats the frame as legitimately authorized, with the denial silently omitted. Exactly the kind of "laundering" attack this project's whole verification apparatus exists to prevent.

**Fix:** Check 7 (`_check_no_contradictory_decisions`) added, always runs (needs only `decision_records`, no optionality). Validates `decision_records`' own internal consistency directly — independent of whether any audit even references the contradictory key, catching the fabrication at its source rather than only its downstream effect on Check 1. Two regression tests: the core attack (contradictory pair, no audits needed at all, since this is purely a decision-log integrity concern) and a false-positive check confirming a denial and a later allowance at *different* sequence_ids — ordinary, legitimate history — is not flagged.

Disposition: fix + regression test, same discipline as every other real finding this campaign has produced.

---

## Eighth finding: CH-001's remaining three cells, all traced to one structural fact

**Context:** `CH-001` had Orphan, Asymmetry, Omission, and Boundary Crossing already attacked and fixed. The three remaining cells — Substitution, Duplication, Semantic Inflation — turn out to share a single root cause, confirmed directly against both record types' real field lists: `DecisionRecord` and `ExecutionAuditRecord` share **no fields beyond the three-part join key itself** (`sequence_id`, `module_id`, `generation_id`). `decision_hash` (`DecisionRecord`-only) refers to the *policy* decision, not the frame; `input_hash`/`output_hash`/`success`/`frame_timestamp_ns`/`error_message` (`ExecutionAuditRecord`-only) have no counterpart on the decision side. Check 1's matching logic is therefore pure key co-occurrence — it was never designed to, and cannot, cross-validate any content between the two records.

### Substitution — clean, and structurally so, not incidentally

**Attack:** can a genuinely valid `DecisionRecord` be relied upon by the wrong audit?

There is nothing to substitute. Substitution requires shared content that could be swapped between two contexts — `CH-004`'s swap attack worked because `decision_hash` is genuinely shared, checkable content between `DecisionRecord` and `PolicyDecisionRecord`. `CH-001` has no analogous shared content at all beyond the key itself, so there is no vector for this family to exploit. Worth recording as a structural clean pass, not a "nothing found, move on" — a future reader shouldn't need to re-derive why this family doesn't apply here.

### Duplication — real, same shape as the CH-004/CH-006 finding, a new instance

**Attack:** can two `ExecutionAuditRecord`s exist at the identical `(sequence_id, module_id, generation_id)` key, both silently accepted?

Yes. Check 1's loop iterates `audit_records` independently, checking each one's key membership in `allowed_keys` with no tracking across iterations — two audits sharing a key would each pass individually. **Check 6 doesn't catch this either**: `_check_decision_execution_completeness()`'s `audit_keys` is also a *set* comprehension, so it only ever asks "does at least one audit exist at this key," identical `>= 1` semantics to Check 1. A duplicated, byte-identical `ExecutionAuditRecord` is invisible to both checks that touch this relationship.

Investigated the same way as `CH-004`/`CH-006`'s Duplication finding, because it's the same append path: no retry logic exists anywhere in the code actually available (`execution_audit_log.py`, `deterministic_execution_engine.py` — confirmed earlier this session, the production persistence call site itself isn't in this sandbox). Same honest limit applies: cannot rule out an unseen external caller retrying, but no legitimate retry mechanism was found. Logged, not built — same disposition as its sibling finding, for the same reason.

### Semantic inflation — real, and it's the direct consequence of the Substitution finding's cause

**Attack:** can "`CH-001` VERIFIED" be read as a stronger claim than it makes?

Yes, precisely because of the structural fact above: `CH-001` proves a `DecisionRecord` and an `ExecutionAuditRecord` share a key — it does **not** and structurally *cannot* prove the decision's authorization has anything to do with the audit's actual content, since `DecisionRecord` carries none. A future integrator reading "decision ancestry verified" could easily infer "this specific execution's inputs and outputs were authorized," when the honest claim is only "an allowed decision object existed for this attempt identifier." This is worth a documented warning for the same reason `MB-003` and the `HC-001`/`GAP-005` compound risk got one — not a defect in the check, a defect in how its result could be narrated.

### Disposition summary

Substitution: documentation confirmation (structural, not incidental). Duplication: logged, not built (same reasoning as `CH-004`/`CH-006`'s sibling finding). Semantic inflation: formally document limitation. No code changes this turn — `CH-001` is now the most thoroughly attacked claim in the campaign, 7 of 7 families attempted, four real fixes, one structural clean pass, two documented limitations.

---

## Ninth finding: MB-004's second attack, Omission — a cross-check that never existed

**Attack (continuing MB-004's campaign, Omission family, per the reasoning "what evidence can disappear between verified segments and candidate edge while the constructor still produces an apparently valid edge"):** `construct_candidate_lineage(segments, verification_results)` takes two separate parameters. Does anything verify `verification_results[i]` actually describes `segments[i]`?

First hypothesis, checked against real source and ruled out before building anything: could a hand-constructed, zero-record `GenerationSegment` reach edge construction, given `replay_and_verify_state_hashes(())` is confirmed (via `test_empty_history_is_trivially_fully_verified`) to report `fully_verified=True` for empty input? No — `GenerationSegment.sequence_id_range` does `self.records[0].sequence_id`, which `IndexError`s on an empty segment, so `verify_segments()` itself crashes before `construct_candidate_lineage()` is ever reached. Ruling this out is worth recording, not silently discarding — it's what redirected the investigation to the real finding.

**The real finding, tracing exactly which fields the function reads from which parameter:** `current_segment, current_result = segments[i], verification_results[i]` — but only `current_result.generation_id` and `current_result.fully_verified` feed edge construction; `segments[i].generation_id` is read *nowhere*. Meanwhile `_last_record_is_fault(current_segment)` reads `segments[i]`'s actual records directly. **Nothing ever cross-checks that these two came from the same place.** A caller supplying `segments_a` (genuinely real, generation A's actual records) paired with `results_b` (genuinely real, generation B's actual, valid `verify_segments()` output) — each individually completely legitimate — gets an edge whose reported identity comes from generation B while its supporting fault-evidence comes from generation A's real last record. Two uncorrelated pieces of data presented as one coherent artifact.

**Fix:** an upfront validation loop, checked for every index before any edge construction begins — `segments[i].generation_id != verification_results[i].generation_id` raises immediately, matching the existing length-check's and same-generation-check's own pattern. New regression test built entirely from real objects (two real generations, each independently run through `verify_segments()`), swapped in the call — no hand-constructed data anywhere, the violation is purely in the pairing.

Disposition: fix + regression, same `PG-001` precedent as the first MB-004 finding — adversarial-fabrication-only (Phase 1's own pipeline always pairs correctly by construction), still fixed rather than merely documented, since this is a public API a caller could invoke directly.

---

## Two additional findings, surfaced by applying Omission and Duplication to CH-004/CH-006

Not requested, but a natural extension once the taxonomy existed — applying two of the seven families to the two directional checks just built.

**Omission — resolved 2026-08-08.** `verify_causal_history()`'s own docstring states the deliberate contract explicitly: `passed=True` means *all requested checks passed*, not *all applicable checks passed* — "behavior is IDENTICAL to before Check 4 existed." The distinguishing signal (`policy_decision_record_count` staying `None` when Checks 4/5 didn't run) already existed and was already documented — the finding was never that no signal exists, only that it's *indirect*: a caller checking only `.passed`, the obviously-named field, would never notice it. Built: `checks_run: FrozenSet[str]`, populated with a stable string identifier for every check that actually executed, always including the six that always run, plus the two optional ones when `policy_decision_log_path` is supplied. This adds no new information over what `policy_decision_record_count` already implied — it adds discoverability: a field literally named `checks_run` doesn't require already knowing the indirect inference. Two regression tests confirm the exact set in both the with- and without-policy-log cases.

**Duplication — decision made 2026-08-08: stay logged, not built. This is a resolved "insufficient evidence to act" state, not an unresolved one.** Check 4's matching logic (`policy_by_key.setdefault(key, []).append(p)`, then `any(...)` over the matches) accepts *any* number of matching `PolicyDecisionRecord`s at a given key — it asserts "at least one," never "exactly one." A duplicated, byte-identical `PolicyDecisionRecord` appended twice would pass Check 4 without comment. The retry-legitimacy investigation (2026-08-07) checked every file with sandbox access to the append path — `policy_decision_record_log.py` (its own docstring explicitly disclaims "crash safety, atomic writes, or concurrent-writer coordination... those remain separate, harder questions"), and `deterministic_execution_engine.py`, which never calls `append_policy_decision_record()` (or any `append_*`) at all — it only builds in-memory lists; real persistence happens outside this file. No other file in the sandbox calls any `append_*` function except tests setting up fixtures. **That investigation was already exhausted — there is no further fact-finding available without the production persistence call site, which genuinely isn't in this sandbox and cannot be requested without knowing what file it would even be.** The honest conclusion stands exactly where it was left: no retry logic exists anywhere in accessible code, narrowing the risk to "a bug in an unseen caller, or deliberate fabrication" — but this does not amount to evidence that duplicates are categorically impossible in the real architecture, and tightening to "exactly one" without that evidence risks breaking a legitimate pattern this project simply cannot see. **Decision: remain at "logged, not built." This is the responsible conclusion given the actual evidence ceiling, not a deferred one** — revisiting it would require new source material, not more analysis of what's already here.

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
| MB-004 (candidate lineage construction) | — | — | ✓ found→fixed (adjacent segments sharing a `generation_id` now rejected, `PG-001` precedent) | ✓ found→fixed (segment/result cross-check added, same precedent) | — | — | — |

Legend: **found→fixed** = real gap, closed with regression test. **found→pending** = real finding, disposition decided but not yet built/resolved. **found→documented** = real, correctly-scoped limitation, now written down. **clean** = attacked, survived, often confirming existing documentation. **⚠ blocked** = attack designed, execution blocked pending a fact-check this methodology refuses to skip. **—** = not yet attempted; absence of evidence, not evidence of absence.

The empty cells are the actual backlog now, not a vague "keep going."

---

## Explicitly out of scope for this document

- No code changes beyond the one small `MB-003` documentation addition already made.
- HC-003 is resolved (2026-08-07) — see above. No longer out of scope.
- Duplication (CH-004/CH-006) — decided 2026-08-08: stays logged, not built. The production persistence call site that would settle the retry-legitimacy question outright isn't in this sandbox, and that fact-finding is now exhausted, not merely paused.
- The omission and duplication findings against CH-004/CH-006 are logged, not fixed — no decision made here about whether uniqueness assertion is worth adding to either check, or whether `checks_run` is worth building.
- No claim that seven families is an exhaustive taxonomy — it is the set that explains every finding made so far, not a proof that no eighth family exists.

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
Distinct from Orphan: omission is about a *missing* piece whose absence goes unflagged, not an *extra* piece with no connection. See the CH-004/CH-006 finding below for a real, current instance of this risk.

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

Retroactively checked against every finding below: Check 1 and Check 5 both terminated at "fix + regression." `HC-001` and `MB-003` both terminated at "formally document limitation" — a real, accurate limitation that was simply never written down. `CH-002` terminated at "documentation confirmation" — the attack succeeded technically but the boundary already said so. The loop holds; it wasn't being followed explicitly, but nothing found this session actually violated its structure.

## The meta-principle this methodology already proved about itself

**Claims, models, and implementations are all attack surfaces — not just implementations.** Check 5's finding wasn't only an implementation gap; `PROVENANCE_GRAPH_MODEL.md` itself named a composition mechanism ("composing through `DecisionRecord`") that didn't actually exist yet. The model was wrong, not just incomplete. That means this methodology has to periodically attack its *own* documents — `PROVENANCE_GRAPH_MODEL.md`, `MODE_B_CLAIMS_REGISTRY.md`, `VERIFICATION_COVERAGE_MATRIX.md`, and this file — the same way it attacks code, on the theory that a formal model describing a graph an adversary is meant to reason against is itself a claim that can be false.

The corollary for this document specifically: it must hold itself to the verification standard it's formalizing. `HC-003` staying flagged rather than resolved is not a gap in this methodology's output — it *is* the methodology's output, working correctly. A version of this document that speculated about `HC-003` to look more complete would itself be an instance of semantic inflation.

---

## First wave of applied attacks

Five claims, as raised. Verdicts vary deliberately — this is meant to show the methodology's actual output distribution, not a curated set of wins.

### HC-001 — real finding, not previously stated this precisely
**Attack:** can I change something that matters operationally but isn't included in `attempt_hash`?
`ModuleRegistrationAttemptRecord` persists `manifest_hash` — a *reference* to the declared manifest, not the manifest's content, and certainly not the actual loaded module code. Two structurally different module implementations that happen to declare identical capabilities and `runtime_api` version would produce the same `manifest_hash`, and `HC-001`'s tamper-evidence says nothing about which one actually ran. **This is the same "internal consistency, not external authenticity" boundary `REPLAY_GENERATION_MODEL.md`'s Theorem 1 already states for hash chains generally — but it had never been stated for `HC-001` specifically.** Not a bug; a boundary worth adding to `HC-001`'s row in `VERIFICATION_COVERAGE_MATRIX.md`. Disposition: formally document limitation.

### HC-003 — open question, flagged rather than guessed
**Attack:** are there semantically important fields excluded from `audit_hash`'s coverage?
Tracing this requires knowing exactly what `ExecutionAuditRecord.from_execution()` does with `ExecutionResult.metrics` — specifically, whether the *deterministic* subset of metrics (the same filtering `ExecutionResult.module_hash` already applies, excluding `*_latency_us` and `telemetry_*` keys) makes it into `ExecutionAuditRecord` at all, or whether it's dropped entirely at the audit-record boundary. I do not have `execution_audit_contract.py`'s `from_execution()` freshly verified in this conversation — everything I'd say here would be reconstructed from partial memory of a file I haven't re-read this session. Given how the Check 5 syntax error and the Phase 3 fault-trigger guess both went this session, I'm not willing to assert a finding here without checking the real source first. **Flagged, not resolved** — worth checking `execution_audit_contract.py` directly before writing anything into the matrix. Disposition: blocked, pending fact-check this methodology refuses to skip.

### CH-002 — clean pass, confirms the existing boundary is accurate
**Attack:** can I construct a history that is globally nonsensical while remaining locally ordered?
Yes, straightforwardly — two engines' records interleaved in one log file, each internally sequence-ordered, with `frame_timestamp_ns` values that contradict the interleaving. Check 2 would not catch this. **But this is not a new finding — `CH-002`'s Boundary column already states exactly this** ("does not interleave the two logs by wall-clock time... no reliable shared clock"). The attack confirms the existing documentation is precise, not loose. Disposition: documentation confirmation.

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

## Two additional findings, surfaced by applying Omission and Duplication to CH-004/CH-006

Not requested, but a natural extension once the taxonomy existed — applying two of the seven families to the two directional checks just built.

**Omission — contract verified, not guessed; disposition pending.** `verify_causal_history()`'s own docstring states the deliberate contract explicitly: `passed=True` means *all requested checks passed*, not *all applicable checks passed* — "behavior is IDENTICAL to before Check 4 existed." The distinguishing signal (`policy_decision_record_count` staying `None` when Checks 4/5 didn't run) exists and is documented. What it doesn't clear is the bar of being *impossible to misunderstand*: a caller checking only `.passed` — the obviously-named field — would never notice the signal. Candidate fix, additive and non-breaking: a `checks_run: FrozenSet[str]` field naming which checks actually executed. Not built yet — disposition decided, execution pending a decision on whether to build now or log.

**Duplication — real, current, disposition explicitly NOT assumed.** Check 4's matching logic (`policy_by_key.setdefault(key, []).append(p)`, then `any(...)` over the matches) accepts *any* number of matching `PolicyDecisionRecord`s at a given key — it asserts "at least one," never "exactly one." A duplicated, byte-identical `PolicyDecisionRecord` appended twice would pass Check 4 without comment. **Whether this is actually wrong is not yet established.** Every append path observed this session (`append_policy_decision_record` and siblings) is a single, unwrapped append with no retry logic seen anywhere — weak evidence toward "duplicates would only arise from a caller bug or fabrication, not legitimate retry semantics," but not a confirmed absence of retry logic elsewhere in the codebase. This is deliberately left as an open question, not a proposed fix, per the explicit caution that persistence systems can have legitimate reasons for duplicate artifacts.

---

## Attack campaigns, not "the next N attacks"

One claim can take multiple attacks from different families; the useful unit of coverage is the (claim, family) pair, not a flat attack count. First-pass coverage matrix — **not exhaustive by design**, populated only with what's actually been run:

| Claim | Orphan | Asymmetry | Substitution | Omission | Duplication | Boundary crossing | Semantic inflation |
|---|---|---|---|---|---|---|---|
| CH-001 (decision ancestry) | — | — | — | — | — | ✓ found→fixed | — |
| CH-002 (sequence ordering) | — | — | — | — | — | ✓ clean (documented) | — |
| CH-004/CH-006 (policy provenance, both directions) | ✓ found→fixed | ✓ found→fixed | ✓ clean (`test_swapped_...`) | ✓ found→pending | ✓ found→pending | ✓ clean (generation-mismatch tests) | — |
| HC-001 (registration hash) | — | — | — | ✓ found→documented | — | — | — |
| HC-003 (audit hash) | — | — | — | ⚠ blocked, needs source | — | — | — |
| MB-002 (segmentation) | — | — | — | ✓ clean | ✓ clean | ✓ clean (malformed transitions) | — |
| MB-003 (cross-generation) | — | — | — | — | — | (this claim *is* a boundary-crossing theorem) | ✓ found→documented |
| PG-001 (graph model itself) | ✓ found→fixed | ✓ found→fixed | — | — | — | — | — |

Legend: **found→fixed** = real gap, closed with regression test. **found→pending** = real finding, disposition decided but not yet built/resolved. **found→documented** = real, correctly-scoped limitation, now written down. **clean** = attacked, survived, often confirming existing documentation. **⚠ blocked** = attack designed, execution blocked pending a fact-check this methodology refuses to skip. **—** = not yet attempted; absence of evidence, not evidence of absence.

The empty cells are the actual backlog now, not a vague "keep going."

---

## Explicitly out of scope for this document

- No code changes beyond the one small `MB-003` documentation addition already made.
- HC-003 is flagged, not resolved — needs `execution_audit_contract.py` verified fresh before writing a finding into the matrix.
- The omission and duplication findings against CH-004/CH-006 are logged, not fixed — no decision made here about whether uniqueness assertion is worth adding to either check, or whether `checks_run` is worth building.
- No claim that seven families is an exhaustive taxonomy — it is the set that explains every finding made so far, not a proof that no eighth family exists.

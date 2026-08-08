# PROVENANCE_GRAPH_MODEL.md

**Status: formalizes existing, tested checks — and found one real gap in the process, not just a documentation gap.** `causal_history_verifier.py`'s four checks already prove specific relationships between the four record types. This document draws those relationships as an explicit graph: nodes, edges, and — critically — which edges are proven *directly* by one check versus proven only *transitively* by composing two checks together. Doing that precisely surfaced a genuine correctness gap in Check 1 (see "Headline finding" immediately below) that has been sitting in the codebase, unnoticed, since before `generation_id` existed.

---

## Headline finding: Check 1 is not generation-aware, and the other checks are

**Status: RESOLVED 2026-08-06.** Original finding preserved below verbatim, since it was accurate when written; the fix and its evidence follow.

`_check_decision_ancestry()` (Check 1) joins `DecisionRecord` to `ExecutionAuditRecord` on `(sequence_id, module_id)` — nothing else. `_check_policy_decision_provenance()` (Check 4), built later in this same session, joins `DecisionRecord` to `PolicyDecisionRecord` on `(sequence_id, generation_id)` specifically, precisely because `decision_hash` alone was proven unsafe to join on across generations (see `PHOENIX_VERIFICATION_STATE.md` Gap 2 / `policy_decision_record_contract.py`'s own docstring). Check 1 predates `generation_id` entirely and was never revisited when the field was added to both `DecisionRecord` and `ExecutionAuditRecord`.

**Concrete failure scenario, not hypothetical:** `sequence_id` resets to zero after every administrative reset (`test_administrative_reset_clears_sequence_counters`). The same `module_id` routinely persists across a reset — a module doesn't get re-registered under a new identity just because the kernel faulted and reset. So a `DecisionRecord` from generation A, sequence_id 5, and an `ExecutionAuditRecord` from generation B, sequence_id 5, for the same `module_id`, will share the exact key Check 1 joins on. Check 1 would report them as causally linked — decision leads to audit — when they are from two entirely different kernel lifetimes.

This directly undermines part of what `generation_id` was introduced to close (Gap 1b) — it just was never applied to this specific check.

**Fix:** `generation_id` added to Check 1's join key, mirroring Check 4's shape exactly, including the same "generation mismatch" vs. "no corresponding record at all" diagnostic distinction Check 4 already made. `test_decision_and_audit_sharing_sequence_and_module_but_different_generation_is_caught` constructs the exact scenario above — same `sequence_id`, same `module_id`, deliberately different `generation_id` — and confirms it is now caught and reported specifically as a generation mismatch, not silently accepted and not collapsed into the generic "no decision" message. All pre-existing Check 1 tests use a single fixed `generation_id` throughout, so none needed to change; the fix is additive to the join key, not a behavior change for any already-tested case.

---

## Second finding: PolicyDecisionRecord orphans were invisible to every check

**Status: RESOLVED 2026-08-06, found via adversarial review, closed same day.** This document's edge tables (below) named `PolicyDecisionRecord.module_id → ModuleRegistrationAttemptRecord` as transitive-only, composed from Check 4 + Check 3. Adversarial review asked a more basic question first: is there *any* check verifying `PolicyDecisionRecord → DecisionRecord` at all, in either direction? There was not.

Check 4 verifies `DecisionRecord → PolicyDecisionRecord` — every decision traces to a real policy record. Nothing verified the reverse: a `PolicyDecisionRecord` could be fabricated at a `(sequence_id, generation_id)` where no real `DecisionRecord` was ever made, for a module that was never registered, and it was invisible to all four checks simultaneously — Checks 1–3 never inspect `policy_decision_records` at all, and Check 4 only ever walks *from* `decision_records`. This is the asymmetry class of attack: A is checked against B, but B is never checked against A.

**Fix:** Check 5 (`_check_policy_decision_orphans`) added to `causal_history_verifier.py` — the literal reverse of Check 4, same join key `(sequence_id, generation_id)`, walked in the opposite direction. `test_orphan_policy_decision_record_with_no_matching_decision_is_caught` constructs exactly the attack above (fabricated `PolicyDecisionRecord`, nothing in any other log) and confirms it is now caught. `test_orphan_check_does_not_false_positive_on_correlated_records` confirms genuinely correlated records are unaffected.

This is a second, independent instance of the same lesson Check 1's fix already taught: a graph model is only as good as its most recent review. Both findings came from taking this document's own stated boundaries literally and asking whether the implementation actually matched them — Check 1's gap was found by re-deriving the join keys; this one by asking, for every directed edge in the tables below, whether its reverse had ever been checked.

---

## Third finding: Check 5 verified key co-occurrence, not decision identity

**Status: RESOLVED 2026-08-08, found via a full seven-family adversarial calibration attack against this document itself, distinct from the MB-004 campaign (see ADVERSARIAL_METHODOLOGY.md's PG-001 section for the full family-by-family trace).** Check 5 closed the Second finding above — a `PolicyDecisionRecord` with no `DecisionRecord` at all is now caught. But Check 5's join condition, traced directly against its own source, was `(sequence_id, generation_id)` key membership only. Nothing in its body ever compared `module_id` or `decision_hash`.

Check 4 (the reverse direction) already defends against exactly this shape of attack — it additionally requires `decision.decision_hash == p.policy_decision.decision_hash` among same-key candidates before accepting a match, precisely because `decision_hash` encodes `module_id` (confirmed directly: `ExecutionPolicyDecision._compute_decision_hash()` hashes `self.module_id.encode("utf-8")` as its second field). Check 5 had no equivalent second condition, making the two directions of this same edge asymmetric in what they actually verify, not just in which direction they walk.

**Concrete failure scenario, confirmed by direct construction and execution, not just traced:** a genuinely valid `DecisionRecord` for `module_B` and a genuinely valid `PolicyDecisionRecord` wrapping a real `ExecutionPolicyDecision` for `module_A` — two individually-correct objects, different modules, different `decision_hash` values — sharing only `(sequence_id, generation_id)`. Before this fix, Check 5 reported zero failures for this pair: it confirmed *some* `DecisionRecord` existed at that key, never that the specific `DecisionRecord` it found was the one this `PolicyDecisionRecord` actually describes.

**Fix:** Check 5 now requires `decision_hash` equality among same-key candidates, mirroring Check 4's own pattern exactly — the fix makes the two directions of this edge symmetric in what they verify, not only in which direction they walk. `test_orphan_check_rejects_a_different_modules_decision_at_the_same_key` constructs the exact scenario above and confirms it is now caught. `test_orphan_check_still_passes_clean_on_genuinely_correlated_pair_after_identity_fix` confirms a genuinely correlated pair is unaffected.

---

## Fourth finding: the graph-level claim never carried forward what each edge actually proves

**Status: DOCUMENTED, 2026-08-08 — found in the same calibration attack as the Third finding, a different family (Semantic Inflation, not Substitution).** This is not a defect in any check or edge — every edge listed in the tables below is, as of the Third finding's fix, correctly and symmetrically verified. This finding is about what this document's own opening claim ("draws those relationships as an explicit graph") licenses a reader to conclude from that fact.

`VERIFICATION_COVERAGE_MATRIX.md`'s own `CH-001` row already states the precise boundary for one edge: *"`DecisionRecord` and `ExecutionAuditRecord` share no fields beyond the join key itself — this check proves key co-occurrence only, never that the decision's authorization relates to the audit's actual content."* That caveat is real, correct, and has never been generalized to this document — the document that actually defines the graph `PG-001` refers to. A reader of this document alone, without also having that specific matrix row in view, could reasonably read "an explicit, checkable graph" as a stronger content-level causal guarantee than any single edge, or the graph as a whole, actually establishes.

**The precise distinction, worth stating explicitly because it is easy to conflate:**
- **Implementation question:** does this edge actually connect the correct records? (Answered per-edge, above — yes, as of the Third finding.)
- **Claim-boundary question:** what does successfully constructing an edge prove about the records it connects? Every edge in this graph proves *positional/key correspondence*, verified now down to content-hash identity where that's checkable (Checks 4/5) — never that the connected records' *authorization content* relates to each other beyond what their respective hashes already encode. `DecisionRecord` and `ExecutionAuditRecord` in particular share no fields at all beyond their join key — Check 1 (and its reverse, Check 7) can never inspect a relationship between the decision's *reasoning* and the audit's *outcome*, because `DecisionRecord` carries no content that could be compared against `ExecutionAuditRecord`'s content in the first place.

**Do not read any edge in this graph, or the graph as a whole, as proving that an audit's actual outcome was causally determined by its decision's actual authorization reasoning.** What is proven is that a real, matching, correctly-identified record of each type exists at the correct position in the history — a real, narrower, and still valuable claim, but a different one than "the graph proves causal correctness."

---

## Fifth finding (traced, not new): a second transitive path exists, symmetric to the first, never previously named

**Status: DOCUMENTED, 2026-08-08 — found while tracing Asymmetry against this document's own transitive-edges table.** The table above names exactly one two-hop composed path: `PolicyDecisionRecord → DecisionRecord` (Check 5) → `ExecutionAuditRecord` (Check 1). Its reverse — `ExecutionAuditRecord → DecisionRecord → PolicyDecisionRecord` — was never named anywhere in this document, even though the table exists specifically to make composed paths visible rather than implicit.

**Traced to confirm whether this reverse path is actually covered, not merely unnamed:** it is, fully, by two already-existing *direct* checks composed, not by anything new. Check 1's own reverse-walk (it starts from `ExecutionAuditRecord` and looks up the matching `DecisionRecord`) plus Check 4 (`DecisionRecord → PolicyDecisionRecord`, direct) together establish exactly this path. Unlike the first transitive path — which depended on Check 5, a check that didn't exist until the Second finding closed it — this second path has been fully covered since Check 4 was first built, simply never written down as its own named composition. No new check needed; this is a completeness gap in this document's own table, not in the verification behavior.

**Asymmetry, reviewed across the whole graph as a structural completeness check (not requiring execution, since it's a question of which edges have reverse checks at all, not a runtime property):** every edge requiring bidirectional verification has it — `DecisionRecord`↔`ExecutionAuditRecord` via Checks 1/7; `DecisionRecord`↔`PolicyDecisionRecord` via Checks 4/5, now identity-symmetric per the Third finding above. The one edge without a reverse (Check 3) correctly has none, since registration-to-reference is inherently many-to-one, the same reasoning already established for `CH-003`'s own Asymmetry verdict. This review is separate from, and should not be conflated with, the Second finding's original Asymmetry discovery (Check 4 existing with no reverse at all) — that was a genuine attack that found a real gap; this is a structural review confirming no further such gaps remain among the edges this document names.

---

## Sixth finding: Boundary Crossing and Duplication, confirmed clean by direct construction and execution against the fixed Check 5

**Status: CONFIRMED CLEAN, 2026-08-08 — a self-correction.** An earlier pass through these two families for this document reasoned about Check 5's logic by reading it, without constructing or running anything. Per this project's own `CH-002` lesson — reasoning that code "looks safe" is exactly the failure mode that let a severe bug sit undetected once already — both families were re-attacked with genuine constructions, executed, before being recorded as clean.

**Boundary Crossing:** `decision_hash` does not encode `generation_id` (confirmed directly against `ExecutionPolicyDecision._compute_decision_hash()`), so two genuinely valid `DecisionRecord`s for the same module, with identical policy content, in two different generations, produce **identical `decision_hash` values** — built and confirmed by execution. Ran the fixed Check 5 against this collision two ways: with both generations' decisions present (correctly passes clean), and — the case that would actually expose a defect — with *only* the wrong-generation decision present, policy record wanting the other generation's key specifically. Result: correctly rejected despite the identical hash, because `decisions_by_key`'s dict key is `(sequence_id, generation_id)`, checked by exact tuple equality *before* any hash comparison runs — a cross-generation collision structurally cannot reach the hash-comparison stage at all.

**Duplication:** built two genuinely different `DecisionRecord`s at the exact same `(sequence_id, generation_id)` — a legitimate-shaped duplicate, different policy content, different `decision_hash` values — then two `PolicyDecisionRecord`s: one genuinely matching one of the duplicates, one a genuine orphan matching neither. Ran the fixed Check 5 against both duplicates plus both policy records together: exactly one failure reported, for the genuine orphan only. The real match was found among duplicate noise; the real orphan was not masked by unrelated duplicate candidates sharing its key.

Neither family found a defect. Recorded here specifically to distinguish this from the earlier, weaker "traced" claim — this is now the same evidentiary standard as the Third finding's Substitution defect: real objects, real check logic, actually executed.

---

## Seventh finding: the transitive registration composition, empirically confirmed against the real pipeline, not just traced

**Status: CONFIRMED CLEAN, 2026-08-08.** The "Not yet built / not yet decided" section below has always framed one question as genuinely open: whether to formalize the `PolicyDecisionRecord.module_id → ModuleRegistrationAttemptRecord` composition (Check 4 + Check 3) as a sixth, direct check, or leave it documented-but-implicit. Earlier passes through this document's Omission family cited that open question without attacking it — accurately noting the design decision was unmade, but not testing whether the *composition itself*, as it actually runs today, holds.

**The precise question attacked:** can a `PolicyDecisionRecord` ultimately reference an unregistered module while every current graph check nevertheless passes? Built the direct construction: a genuine `ExecutionPolicyDecision` and matching `DecisionRecord` for a module deliberately never registered, satisfying everything Check 4/5 require. Ran the real, unmodified `verify_causal_history()` — not `_check_module_identity_cross_reference()` called alone — with only the four disk-read functions substituted for direct in-memory objects; every check function and the orchestration itself ran unmodified. Result: caught, immediately, by Check 3, with no other check contributing noise to the result.

**Why the composition holds, traced to the actual mechanism rather than asserted:** `verify_causal_history()` reads `decision_records` once and passes that identical list to every check that needs it. The `DecisionRecord` required to satisfy Check 4/5's `decision_hash` match for a given module is the *same* `DecisionRecord` object Check 3 independently inspects in the same pipeline run. There is no path where a decision real enough to satisfy the transitive composition could exist without also being directly visible to Check 3. "Transitive, not direct" describes how this document's own edge table structures the *proof* — it is not, and was never, a description of a gap in what the full pipeline actually enforces together.

**This does not resolve the still-open design question below.** Whether to formalize this composition as an explicit sixth check remains a legitimate, separate decision — about documentation clarity and defense-in-depth against a future change to Check 4 or Check 3 in isolation, not about whether the property holds today. It does now hold with direct experimental confirmation behind it, not only architectural reasoning.

---

## Nodes

Four record types, each already independently proven internally consistent (own hash, own construction invariants) by their respective contract/persistence test suites:

- `ModuleRegistrationAttemptRecord` — no `generation_id` field. Structurally outside the generation-aware part of the graph: module registration is a separate lifecycle system, independent of kernel generation, by design (not an oversight — `module_lifecycle.py`'s own docstring frames registry/lifecycle as deliberately separate from kernel state).
- `DecisionRecord` — has `sequence_id`, `module_id`, `generation_id`.
- `ExecutionAuditRecord` — has `sequence_id`, `module_id`, `generation_id`.
- `PolicyDecisionRecord` — has `sequence_id`, `generation_id`; `module_id` lives one level down, at `policy_decision.module_id`.

## Edges — proven directly

| Edge | Join key | Check | Evidence |
|---|---|---|---|
| `DecisionRecord` → `ExecutionAuditRecord` | `(sequence_id, module_id, generation_id)` — generation_id added 2026-08-06, see resolved headline finding above | Check 1 | `test_audit_record_with_no_decision_at_all_is_caught`, `test_audit_record_matching_only_a_denied_decision_is_caught`, `test_decision_and_audit_sharing_sequence_and_module_but_different_generation_is_caught` |
| `DecisionRecord.module_id`, `ExecutionAuditRecord.module_id` → `ModuleRegistrationAttemptRecord` (successful) | set membership, no generation dimension (registration has none) | Check 3 | `test_module_id_with_no_registration_record_is_caught`, `test_module_id_with_only_failed_registration_is_caught` |
| `DecisionRecord` → `PolicyDecisionRecord` | `(sequence_id, generation_id)`, plus `decision_hash` equality | Check 4 | `test_missing_policy_decision_record_is_caught`, `test_policy_decision_generation_mismatch_is_caught`, `test_policy_decision_hash_mismatch_is_caught`, `test_swapped_valid_policy_decision_records_are_caught` |
| `PolicyDecisionRecord` → `DecisionRecord` | `(sequence_id, generation_id)` — added 2026-08-06, see "Second finding" above | Check 5 | `test_orphan_policy_decision_record_with_no_matching_decision_is_caught`, `test_orphan_check_does_not_false_positive_on_correlated_records` |

## Edges — proven only transitively (composition, not direct)

| Edge | How it's actually proven | Fragility |
|---|---|---|
| `PolicyDecisionRecord.policy_decision.module_id` → `ModuleRegistrationAttemptRecord` | NOT checked directly — Check 4 proves `policy_decision.module_id == decision.module_id` (since `decision_hash` encodes `module_id`, per `ExecutionPolicyDecision._compute_decision_hash()`; a mismatch would produce a different hash), and Check 3 separately proves `decision.module_id` is registered. Composing the two gives the result. | **Real fragility, not just theoretical.** Neither check's docstring states this dependency. If Check 4 is ever weakened (e.g., `decision_hash` comparison dropped or loosened) or Check 3 is ever made optional independently of Check 4, this transitively-proven property breaks silently — nothing would flag it, since no test or check directly targets this edge. **Check 5 does not change this fragility assessment** — Check 5 proves a `DecisionRecord` exists at all for a given `PolicyDecisionRecord`, and, as of the Third finding above, that it's genuinely the correct one by `decision_hash`; it still says nothing about `module_id`-to-registration equality, which remains solely Check 4 + Check 3's concern, composed. Do not read Check 5's identity fix as having strengthened this particular transitive claim — it strengthens a different edge entirely. |
| `ExecutionAuditRecord` → `DecisionRecord` → `PolicyDecisionRecord` (the reverse of the path below) | NOT named anywhere in this document until the Fifth finding (2026-08-08) — but fully covered since Check 4 was first built, by composing Check 1's own reverse-walk (`ExecutionAuditRecord` → matching `DecisionRecord`) with Check 4 (`DecisionRecord` → `PolicyDecisionRecord`, direct). | **Not fragile in the same way as the row above** — both composing checks are always-run (Check 1) or already well-tested (Check 4), and neither depends on Check 5's existence the way the forward path does. Named here for the same reason the SHALL clause below requires: an unnamed transitive path is invisible to a future reviewer, whether or not it happens to be safe today. |

**Before Check 5, no edge existed between `PolicyDecisionRecord` and `ExecutionAuditRecord` at all — not even the transitive composition this document originally claimed.** The original text here said the only path was "composing through `DecisionRecord`," but that composition requires a directed edge running `PolicyDecisionRecord → DecisionRecord`, and no such edge existed before Check 5 — Check 4 only ever established the opposite direction (`DecisionRecord → PolicyDecisionRecord`). The original claim was correct in spirit (nothing connected the two node types) but named a mechanism that didn't actually exist yet. **As of Check 5, the composition is real**: `PolicyDecisionRecord → DecisionRecord` (Check 5, direct, and — as of the Third finding above — identity-verified, not just key-verified) → `ExecutionAuditRecord` (Check 1, direct) is now a genuine two-hop transitive path, newly enabled — not previously present under a different description.

## Not an edge — per-node-type invariant, not cross-type

Check 2 (sequence ordering) doesn't belong in the edge table above — it's a constraint *within* one record type's log (`DecisionRecord` sequence_ids non-decreasing per `module_id`; separately, same for `ExecutionAuditRecord`), not a relationship *between* two record types. Worth naming explicitly so it isn't mistaken for a missing edge in the tables above — it was never meant to be one.

---

## SHALL / SHALL NOT — what this graph model requires going forward

**SHALL:**
- Any cross-record-type edge involving two record types that both carry `generation_id` SHALL include `generation_id` in its join key. Check 4 already did this correctly; Check 1 did not until the 2026-08-06 fix above — this rule is now satisfied by both.
- A transitively-proven edge (see table above) SHALL be documented as transitive, naming which two checks compose to prove it, at the point either check is modified. The undocumented `PolicyDecisionRecord.module_id` → registration dependency is the concrete example this project already has of why: it exists, it's real, and until this document, it was invisible.
- **Any directed check (A verified against B) SHALL be evaluated for whether its reverse (B verified against A) is also needed** — added 2026-08-06, per the Check 5 / "Second finding" episode above. A directed edge existing in one direction is not evidence the reverse is unnecessary; it is only evidence the reverse was never asked about. This is now a standing question to ask whenever a new check is added, not a one-off fix specific to Check 4/Check 5.

**SHALL NOT:**
- A check joining two generation_id-bearing record types SHALL NOT be assumed safe merely because it predates `generation_id`'s introduction. Check 1 was the proof this assumption failed in practice, not in theory — now fixed.
- This document's earlier draft stated it "SHALL NOT be read as having fixed Check 1" — that constraint applied while the gap was open. It no longer applies; the fix landed in the same session this document was written, with its own test.

---

## Not yet built / not yet decided

- **Check 1's generation_id gap is fixed** (2026-08-06) — see resolved headline finding above. What remains open is whether the same discipline should be re-audited across any future check that joins two generation_id-bearing record types, as a standing review practice rather than a one-off fix.
- **PolicyDecisionRecord orphans are fixed** (2026-08-06, Check 5) — see "Second finding" above. **This is a different, separate question from the one below** — do not read Check 5 as having resolved it.
- **Still genuinely undecided: whether to formalize the composition dependency (`PolicyDecisionRecord.module_id` → registration, via Check 4 + Check 3) as a sixth, direct check**, versus leaving it as a documented-but-implicit transitive property. Check 5 checks a *different* relationship (existence of a matching `DecisionRecord`, not `module_id`-level registration). Both remain legitimate options for this still-open question; this document names the choice without making it. **What has changed (2026-08-08, see Seventh finding above): the property itself is now empirically confirmed to hold against the real pipeline, not only architecturally reasoned about.** This narrows the design question to defense-in-depth and documentation clarity against a *future* independent change to Check 4 or Check 3 — it does not mean the composition might currently be failing silently.
- **No graph data structure has been built.** This document is the model stated in prose and tables, checked against real code and tests — not a `ProvenanceGraph` class, not a traversal API, not a visualization. Whether any of those are worth building depends on what the graph model is actually needed *for*, which hasn't been named yet.

## Explicitly out of scope for this document

- No decision on the transitive-edge formalization question (the `PolicyDecisionRecord.module_id` → registration composition dependency — formalize as a sixth, direct check, or leave documented-but-implicit). Not the same question Check 5 resolved.
- No claim about `KernelStateEnvelope`'s relationship to this graph — `state_hash` consistency remains Gap 1's separate, still-open question (see `COLD_BOOT_RECONSTRUCTION_CONTRACT.md`), and is not folded into this record-level provenance model.

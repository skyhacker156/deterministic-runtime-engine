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
| `PolicyDecisionRecord.policy_decision.module_id` → `ModuleRegistrationAttemptRecord` | NOT checked directly — Check 4 proves `policy_decision.module_id == decision.module_id` (since `decision_hash` encodes `module_id`, per `ExecutionPolicyDecision._compute_decision_hash()`; a mismatch would produce a different hash), and Check 3 separately proves `decision.module_id` is registered. Composing the two gives the result. | **Real fragility, not just theoretical.** Neither check's docstring states this dependency. If Check 4 is ever weakened (e.g., `decision_hash` comparison dropped or loosened) or Check 3 is ever made optional independently of Check 4, this transitively-proven property breaks silently — nothing would flag it, since no test or check directly targets this edge. **Check 5 does not change this fragility assessment** — Check 5 proves a `DecisionRecord` exists at all for a given `PolicyDecisionRecord`; it says nothing about `module_id` equality, which remains solely Check 4's concern via `decision_hash`. Do not read Check 5's addition as having strengthened this particular transitive claim. |

**Before Check 5, no edge existed between `PolicyDecisionRecord` and `ExecutionAuditRecord` at all — not even the transitive composition this document originally claimed.** The original text here said the only path was "composing through `DecisionRecord`," but that composition requires a directed edge running `PolicyDecisionRecord → DecisionRecord`, and no such edge existed before Check 5 — Check 4 only ever established the opposite direction (`DecisionRecord → PolicyDecisionRecord`). The original claim was correct in spirit (nothing connected the two node types) but named a mechanism that didn't actually exist yet. **As of Check 5, the composition is real**: `PolicyDecisionRecord → DecisionRecord` (Check 5, direct) → `ExecutionAuditRecord` (Check 1, direct) is now a genuine two-hop transitive path, newly enabled — not previously present under a different description.

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
- **Still genuinely undecided: whether to formalize the composition dependency (`PolicyDecisionRecord.module_id` → registration, via Check 4 + Check 3) as a sixth, direct check**, versus leaving it as a documented-but-implicit transitive property. Check 5 checks a *different* relationship (existence of a matching `DecisionRecord`, not `module_id`-level registration). Both remain legitimate options for this still-open question; this document names the choice without making it.
- **No graph data structure has been built.** This document is the model stated in prose and tables, checked against real code and tests — not a `ProvenanceGraph` class, not a traversal API, not a visualization. Whether any of those are worth building depends on what the graph model is actually needed *for*, which hasn't been named yet.

## Explicitly out of scope for this document

- No decision on the transitive-edge formalization question (the `PolicyDecisionRecord.module_id` → registration composition dependency — formalize as a sixth, direct check, or leave documented-but-implicit). Not the same question Check 5 resolved.
- No claim about `KernelStateEnvelope`'s relationship to this graph — `state_hash` consistency remains Gap 1's separate, still-open question (see `COLD_BOOT_RECONSTRUCTION_CONTRACT.md`), and is not folded into this record-level provenance model.

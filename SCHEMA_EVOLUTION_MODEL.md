# SCHEMA_EVOLUTION_MODEL.md

**Status: design note, pre-implementation.** Nothing in this document is built. No `schema_version` field exists in any persisted record today. This exists to settle what a version bump actually claims to preserve before anything is added — matching the same discipline `REPLAY_GENERATION_MODEL.md` applied to Mode B before any of its phases were coded.

**The reframe this note is built around:** schema evolution is not a serialization problem, it is a truth-preservation problem. A version bump can mean three genuinely different things, and this codebase has, so far, only ever formally tracked one of them.

---

## Three axes, not one

**Serialization version — "can I parse this?"**
Does the persisted JSON's *shape* (which keys exist, what type each holds) match what the current code expects to read.

**Hash format version — "what bytes were committed?"**
Does the current code compute a given hash from the same byte sequence a historical record was computed from. This is about the hash function's input, not about whether the record can be loaded at all.

**Semantic version — "does this record mean the same thing?"**
Does a given field's presence, absence, or value carry the same real-world meaning it used to, independent of whether its bytes or its JSON shape changed at all.

These are independent. A change can move on any one axis, any combination, or none. Conflating them is exactly the failure mode this note exists to prevent — see the worked examples below, all drawn from this session's actual history, not hypotheticals.

---

## Current state, audited precisely (not assumed)

### Hash format version: EXISTS, narrowly, as a collision-avoidance mechanism only

Four instances currently in the codebase:
- `KernelStateMachine.STATE_HASH_FORMAT_VERSION = 1`
- `DecisionRecord.RECORD_HASH_FORMAT_VERSION = 2` (bumped from 1 during the `generation_id` migration)
- `PolicyDecisionRecord.ENTRY_HASH_FORMAT_VERSION = 1`
- `ExecutionAuditRecord` gained "its first version byte" in the same migration pass, per `decision_record_contract.py`'s own docstring (exact constant name not independently confirmed here — that docstring is the source for this claim, not direct inspection of `execution_audit_contract.py`).

Each is packed as a leading byte into its respective hash computation. **This is the entire mechanism.** None of these constants drive any branching logic anywhere in the codebase — nothing reads a stored format-version value and chooses between two code paths. Their only actual function: guarantee that if the set of fields feeding a hash ever changes, the resulting hash changes too, so a record from an old schema can never coincidentally collide with a differently-shaped record from a new one.

**This project has already, explicitly, decided the scope of this mechanism.** `decision_record_contract.py`'s own docstring states it plainly: the `generation_id` migration "intentionally invalidates prior record hashes... version identifiers distinguish formats rather than attempting backward hash compatibility." A hash-format-version bump does not provide, and was never intended to provide, a way to reproduce an *old* hash for legacy verification. This note treats that as settled project policy, not an open question — see the SHALL clauses below, which formalize it rather than reopen it.

### Serialization version: DOES NOT EXIST

No record type's `*_to_json()` writes a `schema_version` (or equivalent) key. No `*_from_json()` reads one. "Can I parse this?" is answered today purely by trial: every field is read via unconditional `payload["field_name"]` indexing, across all four record types' persistence modules, with no exception. A missing key raises a bare `KeyError`, which every corruption-detection test in this codebase (`*LogCorruptionError`) currently treats identically to genuine data corruption — there is no path today that distinguishes "this JSON is corrupt" from "this JSON is a valid, older schema version this code no longer recognizes." Those are different failure modes and this codebase cannot currently tell them apart.

**Deeper prerequisite gap, found while auditing this:** every dataclass field across all four record types (`ModuleRegistrationAttemptRecord`, `DecisionRecord`, `ExecutionAuditRecord`, `PolicyDecisionRecord`, and the embedded `ExecutionPolicyDecision`) is declared with **no default value** — including fields typed `Optional[...]`, like `ExecutionPolicyDecision.max_allowed_invocations` and `ExecutionAuditRecord.error_message`. `Optional[X]` here means "the runtime value may be `None`," not "the constructor parameter may be omitted" — both are still required positional/keyword arguments at construction time. This means, as the code is actually written today, there is no precedent anywhere in this codebase for a field that can be safely added without breaking every existing caller's constructor call. Achieving that would require two coordinated changes, not one: the dataclass field needs an explicit default, **and** the corresponding `*_from_json()` needs to read it via `payload.get("field_name", default)` instead of `payload["field_name"]`. Today, every `*_from_json()` function in this codebase uses unconditional indexing exclusively. Adding a default to the dataclass alone would not be enough.

### Semantic version: DOES NOT EXIST as a code-level concept; exists only as a document convention

The only place this project has ever formally tracked a meaning change is `PHOENIX_VERIFICATION_STATE.md`'s own "preserve the old text, add a dated correction in place" convention — used for Gap 1 (2026-08-04) and Gap 1b (2026-08-05). That convention has never had a code-level counterpart. Nothing in any contract module's `__post_init__`, hash computation, or persistence layer tracks or asserts "this field's meaning changed on this date."

---

## Worked examples from this project's actual history, classified by axis

| Change | Serialization | Hash format | Semantic |
|---|---|---|---|
| `generation_id` migration | YES — new required field on 3 record types, every old JSON became unparseable | YES — `RECORD_HASH_FORMAT_VERSION` 1→2, `STATE_HASH_FORMAT_VERSION` first introduced | YES — Gap 1b's finding flipped from "state_hash colliding across a reset is expected" to "it's a bug" to "it's now fixed, differing is expected" |
| `PolicyDecisionRecord` addition | YES — an entirely new record type / file, but existing types' shapes untouched | NO — none of the three existing record types' format-version constants changed | NO — `DecisionRecord`'s own meaning is unchanged; a new, independent fact was added alongside it |
| `observed_invocation_count` on `ExecutionPolicyDecision` | Present in the payload (serialized, persisted, round-trips) | Deliberately absent from `decision_hash`'s byte computation | This is itself the semantic finding (Gap 1b/Gap 2): a field can be real, persisted, and inspectable, while being completely invisible to every hash the codebase computes over that record |

The `generation_id` migration moved on all three axes simultaneously — that is the direct, mechanical explanation for why it produced 152 initial test failures and required the scope of work this whole session covered. `PolicyDecisionRecord`'s addition moved on serialization only (a new file existing at all), and landed at 393/393 with zero regressions specifically *because* it left the other two axes untouched for every pre-existing record type. That contrast is the practical argument for tracking these three axes separately going forward, rather than treating "a schema changed" as one undifferentiated event.

---

## SHALL / SHALL NOT — per axis

### Serialization version

**SHALL**, once implemented:
- Every persisted record type's JSON payload SHALL include an explicit `schema_version` integer field. Not present in any record type today.
- A `*_from_json()` function SHALL branch on `schema_version` before assuming any field's presence, absence, or meaning — replacing today's actual behavior, where an unconditional field lookup conflates "this is genuinely corrupt data" and "this is an older, still-valid schema version" into the same undifferentiated `KeyError`/`*LogCorruptionError`.
- A dataclass field intended to be added in a backward-compatible way SHALL be given an explicit default value at the class definition. This is not currently true of any field on any of the four record types.
- The corresponding `*_from_json()` SHALL read that field via `payload.get("field_name", default)`, not `payload["field_name"]`. Both this and the previous point are required together — neither alone is sufficient, and neither is true of any existing persistence module today.

**SHALL NOT:**
- `schema_version` SHALL NOT bump for a change that doesn't affect the parseable wire shape of the payload (a docstring edit, an internal variable rename that never touches a JSON key). It tracks the wire format, not the implementation.

### Hash format version

**SHALL:**
- Any change to which fields, field order, or byte-packing feeds a hash computation SHALL bump that hash's own `*_FORMAT_VERSION` constant — the pattern already established and already followed correctly across `KernelStateMachine`, `DecisionRecord`, and `PolicyDecisionRecord`.

**SHALL NOT:**
- A hash-format-version bump SHALL NOT be treated as providing, or ever intended to provide, the ability to reconstruct an *old* hash for legacy verification. This project has already decided this explicitly (see `decision_record_contract.py`'s own docstring, quoted above) — this note formalizes that decision as standing policy for every record type, not just the one it was first stated for. Revisiting this is possible but SHALL be a deliberate, separately-argued decision, not something a future version bump quietly assumes.
- A hash-format-version bump SHALL NOT be conflated with a `schema_version` bump or treated as sufficient evidence that meaning is unchanged. The three axes move independently — see the worked examples above, particularly `PolicyDecisionRecord`'s addition (serialization moved, hash format and meaning did not) and `observed_invocation_count` (serialization moved, hash format deliberately did not, and that gap between them *is* the semantic finding).

### Semantic version

**SHALL:**
- Any change to what a persisted value, a hash collision, or a field's presence/absence *means* — independent of whether its bytes or its JSON shape changed at all — SHALL be documented in the relevant contract module's docstring, using the same "preserve the old text verbatim, add a dated correction in place" convention `PHOENIX_VERIFICATION_STATE.md` already established for Gap 1 and Gap 1b. Do not silently rewrite the old claim; show both.
- A semantic change SHALL be flagged even when it requires zero code change. The reset-epoch-observability precedent is the clean example: the meaning of "`state_hash` collides across a reset" flipped from "expected" to "a bug" without a single byte of hash computation changing at the moment the *finding* was made — the code fix (the `generation_id` migration) came later and separately. The document correction was itself a necessary, distinct act, not a byproduct of the code change.

**SHALL NOT:**
- SHALL NOT assume a stable `schema_version` or an unchanged hash-format-version implies unchanged meaning. A future change could alter what a field is permitted to represent (e.g., redefining what the string `"ALLOWED"` may legitimately mean as a `reason` value) without touching serialization or hash bytes at all. A quiet diff on the other two axes is not evidence this one held.

---

## Resolved: the "archival boundary" policy

**This question does not have the same shape as `REPLAY_GENERATION_MODEL.md`'s deferred `GenerationTransitionRecord` question, and should not be deferred the same way.** That question was "should we build more persistence surface area before a demonstrated need" — waiting costs nothing there, since nothing is built either way in the interim. This question is "what does a decision already made, twice, implicitly, become as precedent if it is never named as policy" — and that is not cost-neutral to leave open. Every schema change made under an undecided policy silently adopts whatever the last change happened to do as the new default. Today that default is already "no backward compatibility, ever" (`decision_record_contract.py`'s stated fact about the `generation_id` migration specifically) — but it has never been elevated from "what happened once" to "what this project has decided will always happen." Left undecided, a second and third migration compound the cost of ever reversing course later: `v1 → v2` today becomes `v1 → v2 → v3 → v4 → v5`, each an independent unmigratable break, if nobody ever states the policy that governs all of them.

**Decision: Phoenix SHALL treat every hash-invalidating migration as an explicit, documented archival boundary.** Not a declared support window — that would mean building real dispatch/migration capability now, which is a genuine reversal of the already-stated no-backward-compatibility policy and should only happen as its own deliberate, separately-argued decision if it ever happens at all, not as a default assumed by leaving this question open. The archival-boundary framing requires no new mechanism. It requires a documentation discipline this project has already practiced once (informally, for `generation_id`) and is now naming as a standing requirement for every future one.

**SHALL**, as of this decision:
- Phoenix SHALL NOT attempt backward-compatible reads across a hash-invalidating migration. Already true in practice; now stated as permanent policy, not an artifact of how `generation_id` happened to be handled.
- Every hash-format-version bump SHALL be accompanied, at the time of the bump, by an explicit "ARCHIVAL BOUNDARY" note in both (a) the affected contract module's own docstring and (b) `PHOENIX_VERIFICATION_STATE.md`, stating: the specific version transition, the fact that logs written before it cannot be read by code written after it, and the git commit/tag at which the last pre-boundary-compatible code existed — so historical data remains *recoverable by checking out that point*, not silently lost, even though it is not readable by current tooling.
- A hash-format-version bump SHALL NOT land without this note existing alongside it in the same change. Documentation-after-the-fact (roughly what happened with `generation_id` — the policy surfaces in `decision_record_contract.py`'s docstring, which is good, but was never a required, named convention any future migration was bound to follow the same way) is no longer sufficient going forward.

**SHALL NOT:**
- This decision SHALL NOT be read as resolving whether Phoenix ever builds real backward-compatible reads (the `schema_version`-dispatch mechanism specified earlier in this document). That remains a separate, later decision — see "when to revisit" below, unchanged from the original framing.

**When to revisit (unchanged in substance, now scoped correctly):** the open question is no longer "should Phoenix ever support backward-compatible reads" left fully undecided — it is now specifically "should Phoenix ever *reverse* the archival-boundary policy just adopted, in favor of building real migration support." That reversal should wait for a real, demonstrated need (an actual historical log that needs reading by current tooling), matching `REPLAY_GENERATION_MODEL.md`'s standard for new persistence surface area — because building the dispatch mechanism genuinely is more infrastructure, unlike deciding the archival-boundary policy itself, which required none.

---

## Explicitly out of scope for this document

- No code changes. No `schema_version` field has been added to any record type. No `*_from_json()` function has been changed to use `.get()`.
- The archival-boundary POLICY is decided (see above). The MECHANISM for enforcing it — e.g., an automated check that a hash-format-version bump's commit also includes the required ARCHIVAL BOUNDARY documentation — is not built. This is a process discipline for now, not tooling.
- No claim that any of this is close to buildable within a particular timeframe — this document defines what a version bump on each axis would have to satisfy, not an implementation sketch or a timeline.
- The exact constant name for `ExecutionAuditRecord`'s hash-format-version byte is cited from `decision_record_contract.py`'s docstring, not from direct inspection of `execution_audit_contract.py` — worth confirming directly before this note is treated as fully audited rather than mostly audited.

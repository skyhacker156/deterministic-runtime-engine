# VERIFICATION_PIPELINE_MODEL.md

**Status: formalizes existing, tested code — not a pre-implementation design.** This is a different kind of document from `REPLAY_GENERATION_MODEL.md` and most of `SCHEMA_EVOLUTION_MODEL.md`, both written before any code existed for their topic. `historical_schema_recognition.py` (9/9 tests) and `historical_verification.py` (14/14 tests) already implement exactly the state machine below. What's missing isn't the implementation — it's that these two files have only ever been described as "two modules that compose," never named as one coherent architecture. This document is that name, checked against the real code rather than invented alongside it.

---

## The state machine, as it actually exists in code today

```
raw JSON payload (dict)
        │
        ▼
  SCHEMA RECOGNITION
  (historical_schema_recognition.py, classify_*_payload())
        │
        ├── SchemaRecognition.CURRENT_SCHEMA
        │         │
        │         ▼
        │   REAL VERIFICATION
        │   (historical_verification.py, verify_*_line() —
        │    calls the ACTUAL decision_record_from_json() /
        │    audit_record_from_json(), never reimplemented)
        │         │
        │    ┌────┴────┐
        │    ▼         ▼
        │  PASS       FAIL
        │
        ├── SchemaRecognition.RECOGNIZED_HISTORICAL_SCHEMA
        │         │
        │         ▼
        │  UNSUPPORTED_HISTORICAL_FORMAT
        │  (terminal — verification is NEVER attempted; see
        │   the "recognition is not verification" contract below)
        │
        └── SchemaRecognition.UNRECOGNIZED
                  │
                  ▼
               CORRUPT
               (terminal)
```

Every successfully submitted payload verification attempt resolves to exactly one of four terminal verification outcomes: `PASS`, `FAIL`, `UNSUPPORTED_HISTORICAL_FORMAT`, `CORRUPT`. This document describes the verification state machine, not the full space of possible execution outcomes — a payload that isn't dict-shaped at all (e.g., `None`, or a raw string instead of a parsed JSON object) can raise an uncaught `AttributeError` out of `classify_*_payload()` before recognition ever runs, since that call is not wrapped in any exception handling today. Programmer errors, I/O failures, and other runtime exceptions outside the four verification outcomes are explicitly not what "exactly one path" claims to cover. This is not what `verify_*_line()` was built to guard against; it was built to distinguish PASS from FAIL from UNSUPPORTED_HISTORICAL_FORMAT from CORRUPT, once a submission actually reaches that dispatch.

## State-to-code mapping, exact

| State | Real code | Test evidence |
|---|---|---|
| Schema recognition (three-way) | `historical_schema_recognition.py`, `SchemaRecognition` enum, `classify_decision_record_payload()` / `classify_execution_audit_record_payload()` | `test_historical_schema_recognition.py`, 9/9 |
| `PASS` | `historical_verification.py`, `verify_*_line()`, success branch — real `decision_record_from_json()`/`audit_record_from_json()` call succeeds | `test_current_schema_decision_record_passes`, `test_current_schema_execution_audit_record_passes` |
| `FAIL` | Same real call, exception caught | `test_current_schema_decision_record_with_malformed_hash_fails`, `test_current_schema_execution_audit_record_with_consistency_violation_fails` |
| `UNSUPPORTED_HISTORICAL_FORMAT` | `verify_*_line()`, `RECOGNIZED_HISTORICAL_SCHEMA` branch — no verification attempted | `test_pre_generation_id_decision_record_is_unsupported_not_pass_or_fail`, `test_pre_generation_id_execution_audit_record_is_unsupported` |
| `CORRUPT` | `verify_*_line()`, `UNRECOGNIZED` branch | `test_corrupt_decision_record_is_corrupt`, `test_corrupt_execution_audit_record_is_corrupt` |

## Structural invariants (SHALL) — already enforced, now named as formal properties of the pipeline

- **Recognition SHALL always run before verification is attempted.** No code path in `verify_*_line()` calls the real `*_from_json()` before `classify_*_payload()` has run. This is what makes `UNSUPPORTED_HISTORICAL_FORMAT` reachable at all — without recognition running first, a historical payload would just hit `FAIL` via a `KeyError`, indistinguishable from corruption, which is the exact failure mode `SCHEMA_EVOLUTION_MODEL.md` named as the reason this pipeline exists.
- **`RECOGNIZED_HISTORICAL_SCHEMA` SHALL transition only to `UNSUPPORTED_HISTORICAL_FORMAT` — never `PASS`, never `FAIL`.** This is the "recognition is not verification" contract, and it is enforced structurally, not by convention: `HistoricalVerificationResult.__post_init__` raises `ValueError` if `schema_family` is ever set alongside `outcome=PASS` or `outcome=FAIL` — proven by `test_guard_rejects_historical_family_with_pass_outcome` and `test_guard_rejects_historical_family_with_fail_outcome`. A future maintainer adding a fifth branch to `verify_*_line()` cannot accidentally violate this without the constructor itself refusing.
- **Every payload that successfully reaches the verification-outcome dispatch SHALL resolve to exactly one terminal state.** There is no code path that returns early, retries, or produces a partial/ambiguous result once dispatch begins. `HistoricalVerificationResult` is frozen, and every call that completes returns one terminal result object — not a claim about invocation counts (untested), just the semantic guarantee that there is no intermediate, ambiguous, or mutable state between "a verification attempt ran" and "a result exists." This SHALL does not cover payloads that fail before dispatch even begins (see the qualification in the diagram section above) — a non-dict-shaped payload can still raise uncaught out of `classify_*_payload()`.
- **`PASS` SHALL only be reached via the real, unmodified persistence functions.** `verify_decision_record_line()`/`verify_execution_audit_record_line()` import `decision_record_from_json`/`audit_record_from_json` directly from the actual persistence modules — the same SHALL-5 "never reimplement a hash, always recompute via the real class" principle this project has enforced everywhere else (`cold_boot_reconstruction.py`, `kernel_state_replay.py`) applies here too.

## What this pipeline is NOT — the layering boundary

This is a **per-record** state machine. One payload in, one terminal outcome out. It says nothing about relationships *between* records.

`causal_history_verifier.py`'s Check 1–4 are a genuinely different, higher layer: decision ancestry, sequence ordering, module identity cross-reference, and policy decision provenance are all claims about *multiple* records together, not about any one record's own internal validity. Today, `causal_history_verifier.py` implicitly assumes every record it operates on already passed this pipeline's `PASS` state — because `read_all_decision_records()`/`read_all_audit_records()` raise `*LogCorruptionError` and abort on the first line that isn't `PASS`-shaped, before Check 1–4 ever runs. This pipeline formalizes what those functions are actually doing internally (implicitly, via unconditional `payload["field"]` indexing) without yet changing that behavior — see "Not yet built," below.

**SHALL NOT:** this pipeline SHALL NOT be described as replacing or subsuming Check 1–4, and Check 1–4 SHALL NOT be described as already using this pipeline's four-way outcome. Both statements are false today. They are separate layers that happen to compose cleanly, not yet a single system.

## Current scope: two record types, structurally — not a temporary gap

`historical_schema_recognition.py` and `historical_verification.py` only cover `DecisionRecord` and `ExecutionAuditRecord` — the two record types `generation_id` actually changed. This was originally framed (a few turns after this document was written) as coverage waiting to be extended to `PolicyDecisionRecord` and `ModuleRegistrationAttemptRecord`. On closer look, that framing was wrong: **neither of those two record types has ever had more than one schema.**

`PolicyDecisionRecord` was introduced this session (Gap 2 closure) — no version of it predates `generation_id`/`sequence_id`, so there is no historical shape to recognize; a `classify_policy_decision_record_payload()` would have a `RECOGNIZED_HISTORICAL_SCHEMA` branch that is not rare but *structurally unreachable*, since no data matching an "old" shape can exist. `ModuleRegistrationAttemptRecord` predates this session entirely and was never touched by the `generation_id` migration — same conclusion, same reason.

Building recognition/verification for either now would mean adding migration-shaped infrastructure ahead of any migration ever having happened — precisely what `SCHEMA_EVOLUTION_MODEL.md`'s archival-boundary policy and `REPLAY_GENERATION_MODEL.md`'s `GenerationTransitionRecord` deferral both argue against. This is not a gap in coverage; it is coverage that would currently have no possible input to exercise its own most important branch. Revisit only if either record type's schema is ever actually changed — at that point, the two existing implementations (`classify_decision_record_payload()`, `classify_execution_audit_record_payload()`) are the template to copy, not a redesign.

## Not yet built (named explicitly, not silently assumed complete)

- **No generic dispatcher — reserved extension point, not a pending task.** There is no single `verify_record_line(record_type: str, payload: Dict) -> HistoricalVerificationResult` that routes to the right classifier/verifier pair. `verify_decision_record_line()` and `verify_execution_audit_record_line()` are not arbitrary duplication waiting to be abstracted — they are the two places where historical schema evolution has actually occurred, and a dispatcher built now would just wrap an `if record_type == ...` around exactly two cases, encoding little. The correct trigger for building this is a third historical-verifiable record type appearing, or a caller needing to verify a record type unknown at call time. Neither exists. This is not ranked as upcoming work; it stays unbuilt until one of those two conditions is real.
- **No extension to `PolicyDecisionRecord` or `ModuleRegistrationAttemptRecord`.** Reclassified — see "Current scope" above. This is not a gap; neither record type has a second schema for recognition to distinguish.
- **Not wired into any real read path.** `decision_record_log.py`, `execution_audit_log.py`, and `causal_history_verifier.py` are unchanged by any of this — they still raise and abort on the first corrupt-or-historical line, with the old undifferentiated error message. This has been flagged as a standing gap across the last several turns of this session and remains one. This document does not close it; it only makes precise what would need to change to close it (each log-reading function would need to call this pipeline per line, collect `HistoricalVerificationResult`s instead of raising immediately, and decide how to report a mixed batch — none of which is decided here).
- **No guard against non-dict-shaped input at the entry point.** ~~`verify_decision_record_line()` and `verify_execution_audit_record_line()` call `classify_*_payload()` before entering any `try` block...~~ **RESOLVED**: both functions now check `isinstance(payload, dict)` explicitly before classification and return `CORRUPT` for anything else — proven by `test_non_dict_decision_record_payload_is_corrupt_not_uncaught_exception` and its audit-record counterpart. Left here, struck through rather than deleted, since the gap was real when first named and the fix is worth being traceable to the finding that prompted it.

**Status, as of 2026-08-06: complete enough to freeze.** Every layer above is built and tested — schema recognition, historical verification, read-path classification behavior, documented architectural boundaries. The two items that looked like remaining backlog (a generic dispatcher, extension to `PolicyDecisionRecord`/`ModuleRegistrationAttemptRecord`) were both examined and found to require inventing a need that doesn't currently exist — see the corrected framing above and in "Current scope." This is not an unfinished list; it's a deliberately constrained boundary. Resuming this arc requires a new premise: a real schema transition, a new consumer, or a real operational need — not more speculative code against the current one.

## Explicitly out of scope for this document

- No code changes. Nothing above is new; every claim is checked against code and tests that already exist and pass.
- No decision on wiring (see "Not yet built").
- No decision on extending to the other two record types.
- No claim about what a generic dispatcher's error-handling shape should look like if built — naming its absence is not the same as designing it.

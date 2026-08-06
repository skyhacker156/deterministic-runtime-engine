# VERIFICATION_INTEGRATION_CONTRACT.md

**Status: design note, pre-implementation.** No code changes yet. `decision_record_log.py` and `execution_audit_log.py` are unmodified as of this document. This precedes and constrains the wiring work — no integration code should be written against a claim not listed here as SHALL, matching `COLD_BOOT_RECONSTRUCTION_CONTRACT.md`'s own convention.

**What this resolves:** the "wire the pipeline into a real read path" item has been named as a standing gap across several turns without ever being decomposed. It is actually two different questions that got bundled together:

1. Should the existing `read_all_decision_records()`/`read_all_audit_records()` behave differently — different return type, different exception type, different stop-on-first-failure behavior?
2. Should their error *messages* be enriched with `VERIFICATION_PIPELINE_MODEL.md`'s recognition output when they fail?

This document answers (1) with "no, not yet" and (2) with "yes, precisely like this" — and specifies (2) exactly enough to implement without further design decisions.

---

## Scope

**In scope:** `read_all_decision_records()` in `decision_record_log.py`, `read_all_audit_records()` in `execution_audit_log.py`. Nothing else.

**Explicitly NOT touched by this integration:**
- `causal_history_verifier.py` — needs zero code changes. It calls the two functions above and lets their exceptions propagate uncaught today; that remains true. The exception it propagates just carries a better message.
- `cold_boot_reconstruction.py` — same reasoning, zero changes.
- Every existing test's assertions on successful reads — unchanged, since success-path behavior is not touched at all.
- The one existing test that already asserts on the failure message's shape (`test_corrupt_middle_line_raises_with_line_number`, both files) — see "Backward compatibility, proven" below for why it still passes unmodified.

This is a small blast radius by design. Two files change. Nothing downstream of them needs to know anything happened.

---

## The central fork, resolved

Three shapes were possible for this integration. Only one is being built now.

**Option A — message enrichment only (CHOSEN for this step).** `read_all_*()` keeps its exact current signature, return type, exception type, and stop-on-first-failure behavior. The only change: when it's about to raise `*LogCorruptionError`, it first attempts classification (not full verification — see below) on the failing line, and appends the result to the exception message. Zero API surface change. Zero behavior change for any caller that isn't specifically reading the exception's string.

**Option B — return-type change (REJECTED for this step, not ruled out forever).** `read_all_*()` stops treating the first bad line as fatal, continues reading the whole file, and returns something richer than `List[DecisionRecord]` — e.g., successfully-parsed records plus a parallel list of per-line outcomes for the rest. This is a real, breaking API change: every caller expecting `List[DecisionRecord]` back (`causal_history_verifier.py`, `cold_boot_reconstruction.py`, every existing test) would need to change. Rejected for *this* step specifically because the immediate, named goal — stop misdiagnosing old-but-valid data as corruption — doesn't require it. Not rejected permanently; see "Deliberately deferred" below.

**Option C — new, additive, non-aborting reader function (NAMED, NOT BUILT).** Add `read_all_decision_records_with_verification()` (or similar) as a *second*, new function alongside the untouched original — classifies and verifies every line, never stops early, returns a full per-line report. This is the shape that would actually deliver `VERIFICATION_PIPELINE_MODEL.md`'s "generic dispatcher" value for log-auditing use cases (as opposed to causal-checking use cases, which want to abort on bad data, not tolerate it). This is real, additive, and matches this project's own established pattern (extend via a new entry point, don't modify the old one — same shape as `with_generation()` alongside `__init__()`, Check 4's optional parameter alongside the original three checks). Named explicitly here as the answer to "what would Option B look like done safely" — not built in this step, because it's a distinct capability serving a distinct consumer (a log auditor, not a causal verifier), not a prerequisite for the message-enrichment goal.

**Why Option A first:** it is strictly smaller than C, delivers the actually-named value (stop misdiagnosing recognized-historical data as corruption) immediately, and touches nothing Option C would also need to touch later — building A does not constrain or complicate building C afterward.

---

## Exact algorithm for Option A

Applies identically to both files, substituting the record type's own classifier.

```
except Exception as e:
    classification_note = ""
    try:
        payload = json.loads(line)
        if isinstance(payload, dict):
            classification = classify_decision_record_payload(payload)  # or classify_execution_audit_record_payload
            classification_note = " " + classification.explanation()
    except Exception:
        pass  # line isn't even valid JSON syntax -- no dict to classify, message stays as today
    raise DecisionLogCorruptionError(
        f"Line {line_number} of '{path}' failed to parse as a valid "
        f"DecisionRecord: {e}.{classification_note}"
    ) from e
```

**Two-stage distinction, load-bearing:** the original exception `e` caught by the outer `except` could be a `json.JSONDecodeError` (the line isn't valid JSON syntax at all) or a `KeyError`/`*ValidationError` (valid JSON, wrong or missing fields). Only the second case can be classified — there's no dict to inspect if the JSON itself doesn't parse. The inner `try`/`except` handles this: if the line truly isn't JSON, classification is skipped silently and the message is exactly what it is today. This is not a gap; a genuinely malformed line (not JSON at all) is not what recognition is for — it's actually corrupt, and the original message already says so correctly.

**Uses `classify_*_payload()`, not `verify_*_line()` — deliberately.** By the time this code runs, `decision_record_from_json()`/`audit_record_from_json()` has *already* been attempted and has *already* failed (that's why we're in the `except` block). Calling `verify_*_line()` here would redundantly re-attempt that same real construction a second time inside its `PASS`/`FAIL` branch, for no benefit — we already know it won't succeed. Only recognition (which schema, if any, does this match) adds information at this point; verification has already run and already failed. This keeps the integration's new dependency to `historical_schema_recognition.py` only — `historical_verification.py` is not imported by either log module under this design.

---

## SHALL / SHALL NOT

**SHALL:**
- `read_all_decision_records()` and `read_all_audit_records()` SHALL keep their exact current signatures and return types (`List[DecisionRecord]`, `List[ExecutionAuditRecord]`).
- Both SHALL continue to raise on the first unparseable line — stop-on-first-failure behavior is unchanged by this integration.
- The raised exception SHALL remain the same class (`DecisionLogCorruptionError`, `AuditLogCorruptionError`) — only its message changes.
- The message's existing prefix (`"Line {N} of '{path}' failed to parse as a valid {Type}: {original_error}"`) SHALL be preserved verbatim, with classification detail appended after it, never replacing it.
- Classification SHALL run only inside exception handling, never on the success path — a line that parses cleanly is never classified; there is nothing to diagnose.

**SHALL NOT:**
- This integration SHALL NOT change either function's return type. That is Option B, explicitly not this step.
- This integration SHALL NOT introduce a new exception type or hierarchy. A caller doing `except DecisionLogCorruptionError` today continues to catch exactly what it catches today.
- This integration SHALL NOT call `verify_*_line()` or attempt real record construction a second time — classification only, per the reasoning above.
- This integration SHALL NOT be described as making `causal_history_verifier.py` "verification-pipeline-aware." It remains completely unaware of any of this; it just happens to receive a better exception message when one of its two read calls fails.

---

## Backward compatibility, proven

`test_corrupt_middle_line_raises_with_line_number` (both `test_decision_record_log_append.py` and `test_execution_audit_log_append.py`) asserts:

```python
with pytest.raises(DecisionLogCorruptionError, match="Line 3"):
    read_all_decision_records(temp_log_path)
```

`pytest.raises(..., match=...)` performs `re.search` against the exception's string form. Since the existing `"Line 3 of ..."` prefix is preserved verbatim and only trailing text is appended, this match continues to succeed regardless of what classification detail follows it. Both tests require zero modification. This is stated here as a specific, checked claim, not an assumption to verify later.

The test data in that specific test (`"{not valid json\n"`) is also the two-stage distinction's own worked example: this line fails `json.loads()` in the inner `try` too, so classification is skipped entirely and the message is byte-for-byte identical to today's. That test's existing assertion is not just compatible with this design — it exercises the exact branch where nothing changes at all.

---

## Deliberately deferred

- **Option B** (return-type change) — not ruled out, not scheduled. Would need its own separate contract if pursued, since it's a breaking change to every caller of the two functions in scope here.
- **Option C** (new additive non-aborting reader) — named precisely enough to build later without re-deriving its shape, not built now. Natural candidate for the next `VERIFICATION_PIPELINE_MODEL.md` "not yet built" item to close, after this one.
- Any change to `causal_history_verifier.py` itself to make it "verification-pipeline-aware" beyond incidentally receiving a better exception message — not designed, not needed for this step.

## Explicitly out of scope for this document

- No code changes. `decision_record_log.py` and `execution_audit_log.py` are unmodified as of this document.
- No test code — the implementation step should add tests proving the enriched message appears for a recognized-historical line and is absent/unchanged for a genuinely-unparseable-JSON line, mirroring `test_corrupt_middle_line_raises_with_line_number`'s own shape.
- No decision on Option B or Option C beyond naming them precisely enough to pick up later.

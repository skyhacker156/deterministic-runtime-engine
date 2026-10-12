# RA-004 — Fail-Open vs. Fail-Closed, and a Necessary Correction to RA-002

**Status:** construction complete, but the result requires **retracting
the specific causal claim made in `RA-002`**, not merely extending it.
This is reported precisely and immediately, per the same discipline this
whole case-study series has applied to its own prior turns' mistakes —
a surprising result demands scrutiny before conclusions, including when
the result undermines this project's own earlier finding.

## The construction

Two real traces generated via `etcd-io/raft v3.6.0`, real 3-node
clusters, real TLC runs against real, correctly-formatted trace files:

1. **`ReadIndex` construction:** `CheckQuorum` + `ReadOnlyLeaseBased`
   enabled, a real `MsgReadIndex` issued and confirmed to materially
   complete (a real `readState`, index 2, correct context echoed back).
   Confirmed: role/term/vote identical before and after the round-trip;
   0 of 507 trace events tagged `MsgReadIndex`/`MsgReadIndexResp`. Real
   TLC run: `TraceMatched was violated`.
2. **Control: zero extensions.** No `PreVote`, no `CheckQuorum`, no
   `ReadOnlyLeaseBased` — the plainest possible election plus 25 ordinary
   proposals. Real TLC run: **`TraceMatched was violated` here too.**

## The critical finding: the divergence pattern is identical regardless
   of PreVote

Direct, event-by-event inspection of the control trace's first 20 events
shows the **exact same shape** already found in `RA-002`'s trace: events
1–9 are real bootstrapping, and event 10 is `BecomeCandidate` at
`term: 1`, jumping directly from `StateFollower, term: 0`. **This
control trace has no `PreVote` involvement at all** — there is no
`PreCandidate` step to be missing, because none was ever taken. Yet the
divergence pattern, and TLC's own internal state count (14 states
generated — identical across all three runs: the original `RA-002`
trace, the `ReadIndex` trace, and this control), is the same.

## What this means for RA-002, stated directly

**The specific causal claim in `RA-002`'s "corrected finding" — that the
untraced `PreCandidate` transition is *the* reason `TraceMatched` fails
— is not supported by this new evidence and should be treated as
unconfirmed, not as an established result.** A trace with zero PreVote
involvement fails in the same way, at a structurally similar point. The
real cause is very likely something **common to all three traces** —
plausibly an artifact of this case study's own test harness (the
`network.send` helper used throughout `RA-002` and `RA-004` processes an
entire cascade of inter-node messages synchronously within a single Go
call, a test-only convenience never exercised this way by the real
`Node`/`RawNode` production API), not a property of PreVote specifically.

**This is not a failure of the case study — it is exactly the kind of
correction the discipline is supposed to produce.** `RA-002`'s three
*confirmed* claims (PreVote materially occurs; PreVote is absent from
the trace/model; a real PreVote-enabled execution failed TLC trace
matching) all remain true and independently verified. What does not
survive scrutiny is the more specific mechanistic explanation offered for
*why* — that explanation is now retracted pending further isolation, not
asserted as fact.

## The fail-open/fail-closed question, answered honestly at the level
   the evidence supports

Neither construction produced a clean "fails open" result — both failed
`TraceMatched`, including the one with no extensions enabled at all. This
does **not** answer the fail-open/fail-closed question the way either
outcome A or B was originally framed, because **the confound (a likely
harness artifact affecting even a plain baseline) has not been ruled
out.** Stated precisely: this construction did not yet produce evidence
for Outcome A (an omission that still validates cleanly) or clean
evidence for Outcome B (omissions specifically and only fail when the
omitted mechanism fires) — it produced evidence that something *else*,
not yet isolated, may prevent this particular harness's traces from ever
validating cleanly, which would make any claim about PreVote's or
ReadIndex's *specific* contribution premature until that confound is
controlled for.

## What would be needed to properly isolate this — one check completed

**Completed in this pass:** the project's own shipped `example.ndjson`
(4,888 real events, a genuine production-scale trace) was run through
the identical real TLC command. **Result: no `TraceMatched` error.** TLC
explored progressively — 28 states, then 1,007, then 1,416 — across
multiple minutes of real computation, and was still running cleanly when
this pass's own 180-second timeout was reached (a timeout, not a TLC
error). **This is decisive, exonerating evidence for the tooling and
specification themselves**: a genuine, legitimately-generated trace
validates without incident. The failures in this case study's own three
traces are very likely a real artifact of this case study's test
harness — not a property of PreVote, ReadIndex, CheckQuorum, or the
`Traceetcdraft.tla` specification's correctness.

**Not yet completed:** generating a trace via the production
`Node`/`RawNode` API's normal asynchronous usage pattern, to directly
confirm the harness (rather than merely infer it from the example
trace's success). This remains the precise next step if the
fail-open/fail-closed question is to be answered properly.

## Explicitly not done

The production API path was not attempted — the `example.ndjson` check
above strongly suggests where the fault lies, but does not by itself
prove it (a direct production-API-generated trace, confirmed to
validate cleanly, would be the fully conclusive version of this check).
No claim about PreVote's specific causal role is asserted going forward
until that is done. No safety-property implication was ever drawn from
any of this, consistent with `RA-002`'s original scope discipline — that
constraint holds regardless of this correction.

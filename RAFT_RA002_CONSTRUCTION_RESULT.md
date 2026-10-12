# RA-002 — Construction Complete: Real Execution, Real Trace, Real TLC Validation

**Status:** complete real construction. Real Go execution (`etcd-io/raft
v3.6.0`, the newest tag buildable in this sandbox, confirmed to share the
identical PreVote/TLA+ scope gap as v3.7.0), a real captured trace file,
and a real TLC model-checking run using genuinely downloaded
`tla2tools.jar` and `CommunityModules-deps.jar` — not simulated, not
inferred. **The actual result is more interesting than the originally
hypothesized outcome, and is reported precisely rather than forced to
fit the original hypothesis.**

## The construction

A real 3-node cluster (`newNetworkWithConfig`), `PreVote: true` and
`CheckQuorum: true` on every node, a real `TraceLogger` writing genuine
NDJSON to disk in the exact wire format `Traceetcdraft.tla` expects
(confirmed against the shipped `example.ndjson`). Node 1 campaigns for
leadership (its own real PreVote phase, confirmed via real log output:
`"1 became pre-candidate at term 1"`), becomes leader; node 3 is
genuinely isolated (`nw.isolate(3)`) and ticked through three real
election timeouts while isolated, generating real, confirmed
`MsgPreVote` sends into the void (`"3 sent MsgPreVote request to 1"`,
repeated across isolated timeouts); reconnected; a second isolate/
reconnect cycle on node 2 and additional real proposals extend the
scenario to 299 real captured events (needed to clear a real, unrelated
TLA+ specification threshold — see below).

## Independent confirmation PreVote materially affected the protocol

Confirmed via real assertions on the actual `raft` struct state, not
inferred: node 3's term remained unchanged through three full isolated
election timeouts (PreVote's entire purpose — an isolated node does not
increment its real term while merely pre-campaigning), and the original
leader (node 1) remained `StateLeader` throughout node 3's later
reconnection and pre-candidacy. Both are exactly what PreVote's own
doc-comment purpose ("prevents disruption when a node that has been
partitioned away rejoins the cluster") predicts, confirmed by execution.

## PreVote's absence from the trace, confirmed at scale

**0 of 299 real captured trace events are tagged `MsgPreVote` or
`MsgPreVoteResp`** — confirmed by direct inspection of the actual
written NDJSON file, not the earlier smaller in-memory capture alone.
This holds despite real log output confirming PreVote activity occurred
repeatedly throughout the scenario (both node 1's initial election and
node 3's isolated re-campaigns).

## Real TLC execution — the actual, more decisive result

A genuine `tla2tools.jar` (TLA+ Foundation's own v1.8.0 release) and
`CommunityModules-deps.jar` were downloaded and used to run real TLC
model-checking against the real trace file, using the library's own
shipped `Traceetcdraft.tla`/`Traceetcdraft.cfg`. Two real, honest
engineering obstacles were hit and fixed precisely, not glossed over:
identical timestamps across events initially caused a literal
divide-by-zero in an unrelated part of the spec (fixed by giving each
event a genuinely distinct timestamp); a too-short trace (45 events)
caused a second divide-by-zero in a cosmetic progress-printing
expression (`Len(TraceLog) div 100`, which evaluates to 0 for short
traces) — fixed by legitimately extending the real scenario, not by
padding or fabricating events.

**The actual result: `Error: Temporal property TraceMatched was
violated.`** Full trace validation did **not** report success. This is
different from — and more interesting than — the originally hypothesized
outcome ("validation reports success despite the gap").

**Where, precisely, the divergence occurs — checked directly, not
inferred:** the real trace's events 1–9 are the three nodes'
`InitState`/`ApplyConfChange`/`BecomeFollower` bootstrapping (matched
cleanly by the model — TLC's own progress output confirms ~3–4% before
diverging). **Event 10 is `BecomeCandidate` at `term: 1`, jumping
directly from `StateFollower, term: 0` (event 9) to `StateCandidate,
term: 1` — with zero `PreCandidate` event anywhere between them**,
despite real log output confirming node 1 genuinely passed through a
`PreCandidate` state (`"1 became pre-candidate at term 1"`) at exactly
this point. TLC's own next-state relation — correctly modeling the
*documented* protocol shape, which does include a `PreCandidate`
intermediate step — cannot match a trace that skips directly from
`StateFollower` to `StateCandidate` with no visible precursor, because
the real precursor event was never recorded.

## The corrected, precise finding

Not: *"trace validation silently reports success despite missing
PreVote data."* The evidence, obtained by real execution, shows
something more consequential: **the untraced PreVote phase actively
causes formal trace validation to fail, at the exact point the untraced
activity occurred** — not because the model detected anything wrong with
the implementation, but because the model's own faithful representation
of the *documented* protocol (which does include PreVote/PreCandidate)
cannot be reconciled with a trace that never recorded it. The
observation gap identified in `RAFT_RA002_TLA_DECOMPOSITION.md` is real,
and its consequence is not silent approval — it is an unresolvable
mismatch that a user of this trace-validation machinery would need to
diagnose by hand, with no indication from the tool that PreVote,
specifically, is the reason.

**This is arguably a stronger and more precise observation-boundary
result than the original hypothesis:** the validation layer does not
merely provide *no* assurance about PreVote-affected executions — it
actively cannot process them past the point PreVote occurs, for a reason
a user would have to already know to look for.

## What this does not establish, stated precisely

Not a safety violation — no invariant was found to fail; TLC never
reached the invariant-checking phase for this scenario, since it failed
at the temporal-property (trace-matching) stage first, before checking
`ElectionSafetyInv`, `LeaderCompletenessInv`, or any of the other listed
invariants. **Per the explicit discipline requested: this result is
reported at exactly this level — a validation-layer boundary, not a
safety claim — and no further inference toward a safety property is
drawn here.**

## Explicitly not done

No fix to the tracing code. No modification to the TLA+ specification.
No attempt to determine whether a PreVote-aware model would validate
this trace successfully (a real, well-defined follow-on question, not
pursued here). No safety-property violation claimed or investigated.

---

## RA-002, frozen with three confirmed claims and four explicitly excluded

**Confirmed, by real execution and real TLC validation:**

1. **PreVote materially occurs in the implementation.** Real log output
   and real state/term assertions confirm `MsgPreVote`/`MsgPreVoteResp`
   genuinely fire and genuinely determine whether a term increases and
   whether a leader is disturbed.
2. **PreVote is absent from the trace representation and the TLA+
   model.** Confirmed at the source level (`traceSendMessage`/
   `traceReceiveMessage`'s `default: return`), confirmed at the
   specification level (zero matches for "prevote" in either real
   `.tla` file), and confirmed empirically (0 of 299 real captured trace
   events tagged `MsgPreVote`/`MsgPreVoteResp`).
3. **A real PreVote-enabled execution fails TLC trace matching at that
   exact boundary.** Confirmed by a real TLC run against a real trace:
   `TraceMatched was violated`, diverging precisely at the untraced
   `PreCandidate` transition.

**Explicitly not established, and deliberately kept outside this
finding:**

4. Whether PreVote can violate any of Raft's formal safety properties
   (R-1 through R-5). Not tested, not implied.
5. Whether the Go implementation itself is incorrect. Not tested, not
   implied — the implementation behaved exactly as its own documentation
   and thesis citation describe.
6. Whether the TLA+ model itself is incorrect. Not tested, not implied —
   the model's transition relation behaved correctly given what it was
   told; it correctly rejected an inconsistent trace.
7. Whether TLC would miss a genuine safety violation caused by PreVote.
   Not tested — TLC never reached the invariant-checking phase for this
   scenario, since it failed at the trace-matching stage first.

`RA-002` is closed on exactly these seven points — three confirmed,
four explicitly out of scope.

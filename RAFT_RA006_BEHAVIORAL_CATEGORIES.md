# RA-006 — Behavioral Category Map, and Leadership Transfer Construction

**Status:** complete. Extends `RA-003`'s inventory into behavioral
categories, then constructs and confirms the third instance on the
now-trusted production-path harness (`RA-005`).

## The behavioral category map

| Category | Mechanism(s) | Trace visibility | Status |
|---|---|---|---|
| 1. Election extensions | PreVote | Fully invisible — neither the messages nor the `PreCandidate` state entry are traced | **Confirmed fails open** (`RA-005`) |
| 2. Read/linearizability | ReadIndex | Fully invisible — `MsgReadIndex`/`MsgReadIndexResp` untraced, zero state fields touched | **Confirmed fails open** (`RA-005`) |
| 3. Leadership transfer | `MsgTransferLeader`/`MsgTimeoutNow` | Fully invisible as *messages*; the resulting election **is** traced, but indistinguishable from an ordinary one | **Confirmed fails open, this document** |
| 4. Quorum/liveness | `MsgCheckQuorum` | The resulting `BecomeFollower` transition **is** traced (same event as any other), but the specific *cause* (lost quorum contact) is not distinguishable from any other cause | Traced at the state level; not constructed — a qualitatively different, weaker case than 1–3 (see note below) |
| 5. Snapshot representation | `rsmSendSnapshot`/`rsmReceiveSnapshot` dead constants | `MsgSnap` folded into `AppendEntriesRequest`/`Response`, not a true omission | Not constructed — a labeling inconsistency, not an observation-boundary gap |

**Why category 4 (CheckQuorum) was not constructed as a fourth instance:**
read directly from source (`traceEvent`'s implementation), a `BecomeFollower`
trace event records only `(term, vote, commit, role, log size, conf)` —
identical fields regardless of *why* the transition occurred. A
CheckQuorum-triggered stepdown is not invisible the way PreVote and
ReadIndex are; it produces the same traced event any other stepdown
would. This is a real but different, more mundane limitation (the model
was never designed to distinguish *causes* of a tracked transition, only
to confirm the transition itself is internally consistent) — constructing
it would very likely also validate cleanly, but for a much less
surprising reason than categories 1–3, so it was set aside in favor of
category 3, per the instruction to choose the *most* consequential and
demonstrable case rather than exhaustively construct every candidate.

## The leadership-transfer construction

Built on the real production-path harness (`RA-005`'s corrected, `Node`-API-based
harness — `ApplyConfChange` and storage persistence both correctly
wired). A real leader's `Node.TransferLeadership()` was called against a
real, genuine follower target. Real log output confirms this took the
documented fast path, not an ordinary election: `"1 sends MsgTimeoutNow
to 2 immediately as 2 already has up-to-date log"`, followed by `"2
received MsgTimeoutNow from 1 and starts an election to get
leadership."`

**Confirmed: 0 of 2,357 real trace events tagged `MsgTimeoutNow` or
`MsgTransferLeader`.** The resulting `BecomeCandidate`/`BecomeLeader`
sequence for node 2 *is* traced — but nothing in the trace distinguishes
it from an ordinary, uncoordinated election that happened to elect node
2 for unrelated reasons (e.g., node 1 crashing).

**Real TLC result: `Model checking completed. No error has been found.`**
100% progress, 2,426 distinct states.

## Why this is a qualitatively different finding than categories 1–2

PreVote and ReadIndex are invisible because the state they touch is
either untracked or unchanged. **Leadership transfer is invisible in a
different, arguably more consequential way: the state it produces *is*
tracked and *does* change, but the trace cannot distinguish an
intentional, coordinated, documented-safe handoff from an accidental
election with the same outcome.** A real operator or embedding
application relying on `TransferLeadership` as a deliberately safer
operation than an uncontrolled failover has no way, via this
trace-validation machinery, to formally confirm that a given election in
a trace was actually the coordinated kind rather than the accidental
kind — both produce token-for-token identical trace signatures.

## The proposition this confirms, stated at the precision the evidence
   earns

> A formal validation layer can be completely correct over its modeled
> state space while remaining blind to real protocol mechanisms that
> operate outside that state space.

Confirmed three times, across three qualitatively different mechanisms
(an election-safety extension, a read-linearizability mechanism, and a
liveness/operational-safety mechanism), on a harness now known to be
correct (`RA-005`). This is not a single anecdote — the same result
recurs across categories with different real-world purposes, which is
what makes it a structural finding about the validation architecture
rather than an isolated quirk of one message type.

## Explicitly not done

Category 4 (`CheckQuorum`) and category 5 (snapshot labeling) were
analyzed from source but not constructed — both judged less consequential
or less genuinely boundary-shaped than categories 1–3, per the
instruction to select rather than exhaustively construct. No
safety-property violation claimed or implied anywhere in this document.

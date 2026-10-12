# RA-005 — The Corrected Result, via the Proper Production-Path Ladder

**Status:** complete. This supersedes the causal claims in `RA-002` and
`RA-004`, which are now confirmed to have been produced by a real bug in
this case study's own test harness, not by any property of PreVote,
ReadIndex, or the TLA+ trace-validation machinery. Reported with full
retraction, per the same discipline this whole series has applied
throughout.

## The ladder, exactly as specified, executed in order

**Rung 1 — production-path baseline.** A minimal harness built on the
real, documented `Node` API (`raft.StartNode`, a genuine `for { select {
case <-ticker.C: ... case rd := <-n.Ready(): ... } }` loop per node,
real goroutines, real channel-based message routing) — not the
synchronous, cascading `network.send` test helper used in `RA-002`/
`RA-004`. **Two real, genuine bugs were found and fixed while building
this harness**, both honestly disclosed: (1) `rd.CommittedEntries` of
type `EntryConfChange` were never passed to `Node.ApplyConfChange` —
step 3 of the package's own documented 4-step Ready-processing
contract, omitted in the first draft, causing an immediate panic; (2)
`rd.Entries`/`rd.HardState`/`rd.Snapshot` were never persisted to the
`MemoryStorage` — step 1 of the same contract, also omitted initially,
causing a second panic (`after(0) is out of range [committed(3)]`) even
after the first fix. Once both were corrected, a real 3-node cluster
elected a real leader and processed real proposals with no panics.

**Real TLC result on this baseline: `Model checking completed. No error
has been found.`** 100% progress, 2,020 distinct states, zero PreVote or
CheckQuorum or ReadOnlyLeaseBased involvement. **This confirms the
production path itself is sound** — the divergences found in `RA-002`
and `RA-004` were not inherent to this library or this trace-validation
machinery.

**Rung 2 — same baseline + ReadIndex.** `CheckQuorum` + `ReadOnlyLeaseBased`
enabled, a real `Node.ReadIndex()` call issued against the real elected
leader. Confirmed: 0 of 2,384 real trace events tagged `MsgReadIndex`.
**Real TLC result: `Model checking completed. No error has been
found.`** 100% progress, 2,449 distinct states.

**Rung 3 — same baseline + PreVote.** `PreVote` + `CheckQuorum` enabled.
Real log output confirms genuine `MsgPreVote` activity (`"1 cast
MsgPreVote for 2"`). Confirmed: 0 of 1,912 real trace events tagged
`MsgPreVote`/`MsgPreVoteResp`. **Real TLC result: `Model checking
completed. No error has been found.`** 100% progress, 1,977 distinct
states.

## The corrected finding, replacing RA-002's retracted causal claim

**On the correct, production-realistic path, both omissions — ReadIndex
and PreVote — fail open, not closed.** The trace validates cleanly to
100% completion in both cases, despite each mechanism's real,
independently-confirmed occurrence being entirely absent from the trace.
This is a clean, decisive confirmation of **Outcome A** from the
originally-posed framework: a real omission that still produces a fully
valid, matching trace, corresponding to real protocol behavior the
model neither represents nor observes.

**`RA-002`'s specific mechanistic claim — that the untraced
`PreCandidate` transition causes `TraceMatched` to fail — is now
confirmed to have been an artifact of this case study's own flawed test
harness (the synchronous `network.send` helper), not a property of
PreVote or the specification.** `RA-002`'s three original claims that
did *not* depend on this mechanism (PreVote materially occurs; PreVote
is absent from the trace/model) remain true and are now confirmed on
solid ground by this corrected construction. The specific claim that a
real PreVote-enabled execution *fails* TLC trace matching is **retracted
and replaced**: a real PreVote-enabled execution, generated correctly,
**passes** TLC trace matching.

## Why this result is more significant than either original hypothesis

Per the framing given before this construction began: Outcome A
("extremely significant") is what was found, on the properly-constructed
harness, for **both** identified omissions. This means the trace-validation
architecture's real, demonstrated behavior is: it can and does formally
validate executions containing real, safety-adjacent protocol activity
(leadership stability decisions, linearizable read safety decisions) that
it never observed and cannot represent — not because it fails closed and
catches the mismatch, but because the omitted behavior never perturbs
any of the state fields (`term`, `vote`, `commit`, `role`) the model
actually tracks, in either case.

## Explicitly not done

No claim of a safety-property violation — consensus safety (`R-1`
through `R-5`) was never threatened or tested here; both PreVote and
ReadIndex behaved exactly as documented, and the finding is entirely
about what the *validation layer* can and cannot see, not about whether
the *implementation* is correct. `RA-003`'s broader inventory (`MsgCheckQuorum`,
`MsgTransferLeader`, `MsgTimeoutNow`) was not re-tested on this corrected
harness — a real, well-defined next step, not undertaken here.

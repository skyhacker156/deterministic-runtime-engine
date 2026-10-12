# RA-001 — Can `restore()` Ever See `StateLeader`?

**Status:** decomposition complete and near-conclusive from source. A
real Go test was written to empirically confirm it, but **live
execution is blocked by a genuine Go 1.26 language-syntax requirement**
this sandbox cannot satisfy without a disproportionate undertaking
(bootstrapping the Go compiler itself from source) — reported honestly,
matching the same discipline applied to the FoundationDB rebuild
decision, not forced or glossed over.

## The six decomposition questions, answered from real source

**1. What exact state transition would have to occur for `restore()` to
see `StateLeader`?** None was found. `restore()` is only ever reached via
`handleSnapshot`, which has exactly two real call sites in the entire
codebase (`raft.go`): one inside `stepCandidate` (which calls
`r.becomeFollower(...)` *before* calling `handleSnapshot`), and one
inside `stepFollower` (already in follower state). Both structurally
guarantee `r.state == StateFollower` by the time `restore()` runs.

**2. Can it arise through legitimate Raft message processing?** Traced
three layers deep, all confirming no: (a) `Step()`'s shared pre-processing
demotes any node to follower on receipt of *any* message — including
`MsgSnap` — carrying a higher term than its own, *before* dispatching to
any state-specific handler; (b) `stepLeader`'s own switch statement
(read in full, every `case` enumerated) has **no case for `MsgSnap` at
all** — only `MsgSnapStatus` (an acknowledgment of a snapshot the leader
itself sent) — meaning a same-or-lower-term `MsgSnap` arriving at a
leader is silently dropped, never reaching `handleSnapshot`; (c) the
public library API (`Node`/`RawNode`, both read directly) exposes no
method that calls `restore()` other than through the same `Step()`
pipeline already traced — no bypass exists.

**3. Can it arise through snapshot installation?** Covered by (2) above —
snapshot installation is only ever message-driven in this library, and
every message-driven path is accounted for.

**4. Can it arise during leadership transition?** `stepLeader`'s
`MsgTransferLeader` handling (read in full) only calls `sendTimeoutNow`
or `sendAppend` — no interaction with snapshot handling. Leadership
transfer changes who becomes leader on the *other* end; it does not
create a window where the current leader processes a snapshot.

**5. Is the guard merely defensive dead code, or is there a reachable
sequence the existing tests don't cover?** Per (1)–(4): the evidence
strongly suggests the guard's precondition (`restore()` invoked while
`r.state == StateLeader`) is genuinely unreachable through the library's
own message-processing and public API surface — not merely untested, but
structurally prevented by three independent mechanisms. This is stronger
than "the tests don't cover it"; it's "there may be nothing to cover."

**6. If reachable, what happens after the guard fires?** Not applicable
given (5)'s finding — the guard's own behavior (force-demote to a new
term, refuse to apply) was read and is straightforward, but was not
empirically exercised, since no path to reach it was found.

## The construction attempted

A real Go test (`ra001_leader_restore_test.go`) was written against the
actual, unmodified `etcd-io/raft v3.7.0` source — not a mock, not a
simplified stand-in — exercising exactly the two most adversarial-looking
conditions: a real leader (via `becomeCandidate`/`becomeLeader`)
receiving a real `MsgSnap` through the real `Step()` entry point, once
with a higher term and once with the same term. The test asserts on the
node's resulting state and commit index, logging which of the three
outcomes (A/B/C, per the pre-registered framework) each condition
produced.

## Why it could not be run

`go.etcd.io/raft/v3`'s `go.mod` requires Go ≥1.26. This sandbox has Go
1.24.4 (the newest available via `apt`; `apt-cache policy` confirms
`golang-go` tops out at 1.22, and the manually-installed `golang-1.24`
package was the newest usable). **This is not a version-string
formality** — confirmed directly by attempting the same `go.mod`-downgrade
workaround that worked earlier in this case-study series (for Temporal's
SDK): downgrading the `go` directive to 1.24 allowed dependency resolution
to proceed, but compilation itself failed with real syntax errors (e.g.,
`raftpb/confchange.go:62`: `NodeId: new(c.GetNodeId())`) — a call to the
built-in `new()` with a *value* argument rather than a *type*, a genuine
Go language feature not present in Go 1.24. This codebase actually uses
new 1.26 syntax throughout (confirmed present in `raft.go` itself, e.g.
`new(term)`-style calls read earlier in this case study without
recognizing them as this feature), not merely a declared-but-unused
version bump.

**Go 1.26 source is available via `github.com/golang/go` (an allowed
domain), and could in principle be bootstrap-built from Go 1.24** — but
this is a disproportionate undertaking for this specific question, in
the same category of decision the FoundationDB rebuild required. Not
attempted, per the same discipline: don't let infrastructure escalate
into unwarranted sunk-cost chasing when the source-level evidence is
already strong. `go.mod` was restored to its original, unmodified state
after this was confirmed.

## Current status, stated precisely

**Outcome A (unreachable under legitimate protocol transitions) is
strongly supported by source-level analysis — three independent
mechanisms, each read in full, each confirming the same conclusion.**
This has **not** been empirically confirmed by live test execution, and
that gap is stated honestly rather than papered over with the strength
of the source-level case. The real, written test remains available and
would run immediately given a Go 1.26 toolchain.

## Explicitly not done

Go 1.26 was not bootstrap-built. The written test was not executed. No
other workaround was attempted beyond the one already known to work for
a different constraint (Temporal's SDK version) and confirmed here not to
apply. `restore()`'s own post-guard behavior (question 6) was read but
not exercised, since no reachable path to it was found.

# Raft Phase 2 — Enforcement Boundary Decomposition

**Status:** decomposition only, grounded in direct reading of real
`etcd-io/raft v3.7.0` source (`raft.go`, `log.go`) and the corresponding
real tests in `raft_paper_test.go`. No construction, no adversarial case.
Per instruction, the objective here is not to break Raft — it is to
determine precisely what the implementation can observe, and therefore
what its safety machinery can actually establish.

---

## R-1 — Election Safety

**Exact implementation mechanism** (`raft.go`, `Step`, the `MsgVote`/
`MsgPreVote` case, ~line 1212): `r.Vote` is a per-server, per-term field.
`canVote` is true only if this is a repeat vote for the *same* candidate,
or the server hasn't voted this term and believes there's no leader yet.
Once a real vote is cast, `r.Vote = m.GetFrom()` is recorded — a second,
different candidate in the same term cannot obtain this server's vote.
Combined with `poll`/`r.trk.TallyVotes()` requiring a majority (via the
`quorum` package, not yet read in this pass), two non-overlapping
majorities cannot both form in one term — this is the concrete
implementation-level mechanism behind the paper's abstract "each server
votes for at most one candidate per term" argument.

**Persisted/observable state relied upon:** `r.Vote`, `r.Term` — both
part of `HardState` (confirmed via `hardState()`, line 504), meaning
these are the durable, persisted fields a real deployment relies on
surviving a crash. `r.lead` (in-memory only, reset each term via `reset`)
is also consulted (`r.lead == None` check) but is *not* itself persisted.

**What the existing test actually verifies vs. what the property formally
claims:** not yet identified precisely — `raft_paper_test.go`'s
election-related tests (`TestFollowerVote`, `TestVoter`) were named but
not yet read in this pass for their exact assertions. Flagged as the
first gap in this decomposition, not filled in by assumption.

## R-2 — Leader Append-Only

**Exact implementation mechanism** (`raft.go`, `appendEntry`, line 812):
the leader's own log-append entry point always computes the next index
as `li + 1 + i` (one past its own log's current last index) — there is
no code path here that accepts an explicit target index enabling
overwrite of an earlier position.

**A real, additional hard guard found, not merely inferred:**
`log.go`'s `maybeAppend` (line 109) contains an explicit `Panicf` if a
conflict is ever detected at an already-committed index — the
implementation treats "never overwrite a committed entry" as a checked
assertion, not merely an emergent property of how the code happens to be
structured.

**What was not checked, stated precisely rather than assumed clear:**
whether any *other* code path (snapshot `restore`, at line 1860, or
configuration-change handling) could cause a node currently believing
itself to be leader to truncate or overwrite its own log. `appendEntry`
alone was read; `restore`'s interaction with leader state was not traced
in this pass. This is a real, open gap in the decomposition, not a
confirmed absence of any such path.

## R-3 — Log Matching

**Exact implementation mechanism** (`raft.go`'s `handleAppendEntries`,
line 1791, delegating to `log.go`'s `maybeAppend`, line 109): the
follower checks `l.matchTerm(a.prev)` — does the entry at the leader's
claimed previous index have the leader's claimed previous term? If not,
the append is rejected and a `RejectHint`/`findConflictByTerm`-derived
hint is returned to help the leader converge faster — a real,
documented optimization beyond the paper's basic mechanism, not merely a
restatement of it.

**On successful match:** `findConflict` locates the first genuinely
conflicting entry in the new batch (if any) and truncates from there
before appending — directly implementing "if two logs contain an entry
with the same index and term, they are identical up through that index"
by construction: a mismatch anywhere is caught by `matchTerm` before any
append proceeds.

**Directly relevant real test, not yet fully read in this pass:**
`TestFollowerCheckMsgApp`, `TestLeaderSyncFollowerLog` — named and
located, not yet read for exact assertions. Flagged as the next step,
not assumed.

## R-4 — Leader Completeness

**Exact implementation mechanism** (`log.go`'s `isUpToDate`, line 442),
read and confirmed to match the paper's stated comparison rule
**exactly, at the code level, not merely in spirit**:

```go
func (l *raftLog) isUpToDate(their entryID) bool {
    our := l.lastEntryID()
    return their.term > our.term || their.term == our.term && their.index >= our.index
}
```

Higher last-entry term wins outright; equal term falls back to comparing
index. This is consulted directly in the vote-granting decision
(`Step`'s `MsgVote`/`MsgPreVote` case, line 1218:
`canVote && r.raftLog.isUpToDate(candLastID)`) — a voter that finds the
candidate's log *not* up-to-date simply does not grant the vote,
regardless of `canVote`'s other conditions. This is the real,
line-level implementation of the paper's election restriction.

## R-5 — State Machine Safety

**The paper frames this property as derived** from R-3 (Log Matching)
and R-4 (Leader Completeness) via a proof sketch, not as independently
enforced. **The real implementation is more explicit than that framing
suggests — worth stating precisely rather than accepting the paper's own
characterization at face value for the implementation specifically:**

`raft.go`'s `maybeCommit` (line 775) calls `raftLog.maybeCommit` with
`entryID{term: r.Term, ...}` — always the leader's *current* term.
`log.go`'s `raftLog.maybeCommit` (line 455) contains a direct, explicit
gate: `if at.term != 0 && at.index > l.committed && l.matchTerm(at)` —
the commit index is **only** advanced if the entry at that index matches
the term being committed at (the leader's current term). This is the
real, concrete implementation of the paper's Figure 8 problem resolution
(a leader cannot conclude an entry from a *previous* term is committed
purely by counting replicas — confirmed directly against the paper's own
section reference).

**Directly confirmed by a real, existing test:**
`TestLeaderOnlyCommitsLogFromCurrentTerm` (read in full, lines 749–780) —
its own comment cites "Reference: section 5.4.2" of the paper directly.
The test constructs a 2-node cluster with pre-existing entries at terms 1
and 2, becomes leader at term 3, and confirms directly: replicating
entries at the previous-term indices (1, 2) to a majority does **not**
advance the commit index (`wcommit: 0` in both cases), while replicating
an entry at the *current* term (index 3) does (`wcommit: 3`). This is a
precise, real, paper-section-cited test that verifies exactly the
mechanism read in source — a clean case where implementation, source
citation, and test assertion all agree, found by reading each
independently rather than assuming agreement.

**A separate function, `committedEntryInCurrentTerm` (line 2066), is
distinct from the enforcement mechanism above** — it is a read-only query
used elsewhere (call sites at lines 1365 and 2133, not yet traced to
their surrounding context in this pass) for a different purpose
(plausibly read-index or leadership-transfer safety, not yet confirmed).
Flagged precisely so this second, similarly-named function is not
conflated with the actual commit-advancement gate.

---

## What remains open, stated honestly rather than glossed over — CLOSED, per the five follow-up items

All five items below were closed with real source reads before this
decomposition was frozen, per instruction.

### 1. R-1/R-3 test bodies, read in full

**`TestFollowerVote`** (line 217): a table of `(existing vote, new
candidate, expect reject)` triples, run through the real `Step`/`MsgVote`
path. Confirms exactly the `canVote` logic already read: voting for the
same candidate twice is accepted; voting for a second, different
candidate in the same term is rejected. **`TestVoter`** (line 712): a
table directly exercising `isUpToDate`'s three cases (same last-log-term,
candidate's log strictly ahead by term, voter's log strictly ahead by
term) against real `Step`/`MsgVote` calls. Both tests confirmed to
exercise exactly the code already read — no discrepancy found between
what the test claims to verify and what it actually asserts.

**`TestFollowerCheckMsgApp`** (line 546) and **`TestLeaderSyncFollowerLog`**
(line 639): both read in full. The first directly exercises `maybeAppend`
across match/mismatch/nonexistent-entry cases, confirming the
`RejectHint`/`findConflictByTerm` mechanism precisely. The second runs a
genuinely elaborate real three-node scenario (a table of six different
divergent follower log shapes, terms `0,1,1,1,4,4,5,5,6,6,6`)
synchronized against a fixed leader log via the real network/election
machinery (`newNetwork`, `MsgHup`) — not a simplified stand-in, the real
convergence process.

### 2. R-2 — every log-mutation path traced

**Confirmed closed and clean:** exactly two call sites of the underlying
`append` primitive exist in the entire codebase — `raft.go`'s
`appendEntry` (leader, line 834, always sequential, never an explicit
target index) and `log.go`'s `maybeAppend` (follower, line 127, gated by
`matchTerm`/`findConflict`). No third path exists.

**A significant, previously-unflagged finding, found by tracing `restore`
in full:** `restore` (snapshot application, line 1860) contains an
explicit guard — `if r.state != StateFollower` — that refuses to apply a
snapshot and instead force-demotes the node to follower for a new term,
with a comment stating plainly: *"This is defense-in-depth: if the leader
somehow ended up applying a snapshot... This should never fire."*
**A real, targeted search of every `*_test.go` file in the repository
found zero tests exercising this specific guard.** The implementation
authors' own comment expresses uncertainty about whether this path is
truly unreachable by construction elsewhere — and no test verifies the
backstop itself behaves correctly if it is ever reached.

### 3. `quorum` package, read directly

**`MajorityConfig.VoteResult`** (`quorum/majority.go`, line 169):
standard majority formula (`len(c)/2 + 1`), correctly distinguishing
`VoteWon`/`VotePending`/`VoteLost`. **`JointConfig.VoteResult`**
(`quorum/joint.go`, line 61): correctly requires both underlying
majority configs to agree, with `VoteLost` dominant if either side has
lost. No defect found in either; both read in full, not sampled.

### 4. Every call site of `committedEntryInCurrentTerm`, followed

**Both call sites (lines 1365, 2133) are about linearizable `ReadIndex`
safety** — postponing a strongly-consistent read until the leader has
committed at least one entry in its own current term — **not** the core
R-5 commit-advancement gate itself, which lives entirely in
`raftLog.maybeCommit`'s own `matchTerm` check (already confirmed in the
prior pass). This closes the ambiguity flagged earlier: two genuinely
separate mechanisms exist, correctly not to be conflated.

### 5. R-6 — a full, separate source pass over the TLA+ trace-validation machinery

**The trace-injection code (`state_trace.go`) is gated behind
`//go:build with_tla`** — compiled out of the default build entirely (a
no-op stub, `state_trace_nop.go`, ships in the standard build instead).

**Trace-event coverage, read directly from source, is broader than the
README's two illustrative examples suggested:** `BecomeCandidate`,
`BecomeFollower`, `BecomeLeader`, `Commit`, `Replicate`, `ChangeConf`,
`ApplyConfChange`, `Ready`, and Send/Receive pairs for AppendEntries,
RequestVote, and Snapshot — a real, fairly comprehensive set touching
every property R-1 through R-5 relies on.

**The decisive finding: a direct search of every CI workflow file in the
repository (`test_template.yaml`, `test_amd64.yaml`, `static-analysis.yaml`,
`codeql-analysis.yml`, `govuln.yaml`, `gh-workflow-approve.yaml`) found
zero references to `with_tla` or TLA+ anywhere.** The trace-validation
machinery is real, well-documented, and reasonably comprehensive in what
it *could* observe — but is confirmed, directly, not to be part of this
project's own automated, routine verification. Whatever confidence it
could provide is not being cashed in as a standing gate; it exists as a
manual, opt-in process, exercised only when a developer deliberately
builds with the tag and runs it by hand.

---

## R-1 through R-6, frozen

The decomposition above — now closed on all five follow-up items — is
frozen. No further source reading planned before construction begins.

## Where the clearest separation lives, per the question posed

Weighing all six properties against "clearest separation between the
formal property claimed, the implementation mechanism enforcing it, and
the evidence/oracle used to determine it holds":

- **R-1, R-3, R-4** each have a tight, direct correspondence: one clear
  mechanism, one clear test exercising exactly that mechanism, no gap
  found in this pass.
- **R-5** has a *stronger*-than-expected mechanism (an explicit gate, not
  merely a derived property) with a precisely matching, paper-section-cited
  test — a clean result, not a gap.
- **R-2** has a real, genuine separation: the formal property ("leader
  never overwrites") is enforced two ways — structurally (no code path
  supports it) and defensively (`restore`'s runtime guard) — and the
  defensive layer is accompanied by the implementation's *own*
  self-admitted uncertainty ("should never happen," "should never fire"),
  with confirmed zero test coverage of that specific guard.
- **R-6** has the widest, most consequential separation found in this
  entire pass: a real, well-built, reasonably comprehensive
  formal-model-correspondence mechanism exists, but is confirmed,
  directly, to not be part of the project's own routine verification —
  the gap here isn't "the mechanism is weak," it's "the mechanism exists
  and isn't used as a standing check."

**Both R-2 and R-6 are real candidates. R-6 is the wider, more
structural separation (a whole verification layer that exists but
isn't exercised); R-2 is the narrower, more surgical one (one specific,
self-admittedly-uncertain guard, zero test coverage, tied to a single
named property).** Which one anchors `RA-001` is a separate decision,
not made here.

## Explicitly not done

No adversarial construction. No test execution beyond reading existing
test source. No modification of any kind.

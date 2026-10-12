# Case Study 3 (etcd Raft): execution plan (draft 3, to be hashed by prerun.ps1)

**Draft 3 changes (harness build, 2026-10-11, before hashing).** Each
was forced by something found while writing the harness; details in
`DEV_LOG.md`.

1. **Election randomness.** Both releases draw election timeouts from
   `crypto/rand.Reader`. The harness replaces that Reader with a seeded
   stream per trial and refuses to run if `crypto/rand.Int` ignores the
   replacement on the toolchain in use. No library code is changed.
2. **Version adapters.** v3.7.0 moved to standard protobuf (pointer
   fields), so the two builds cannot share raft-facing code. All raft
   access goes through one adapter file per release, chosen by build
   tag. The two operator module files differ only in the raft version
   line; the adapters must be reviewed side by side.
3. **Isolation and pause semantics, exactly.** A message's fate is
   decided when it is sent. Isolation and pause act when it is due for
   delivery: it is held, and released in hold order, immediately, when
   the window ends.
4. **P1a trace corrections** (section 3): the write is made by client 3,
   because client 2 still has read A outstanding and each client has one
   operation at a time; the retry is caused by delaying node 1's
   response to node 2, not by withholding confirmation; node 1's tick
   source is stalled during the partition rather than paused, because it
   must still process messages.
5. **P1a jitter** applies only to messages outside the read path
   (heartbeats and ReadIndex messages are never jittered), which is what
   "non-essential events" means.
6. **Toolchain.** Operator builds need Go 1.26 (v3.7.0 requires it).
   Whether `crypto/rand.Int` honours a replaced Reader under Go 1.26 was
   not verifiable here; the self-test checks it on the operator's
   machine before any arm.
7. **Development disclosure.** P1a was executed during development on
   development builds. Section 7 and `DEV_LOG.md` give the results. The
   reserved seeds (P1a jitter 1-20, randomized 1-3000) were not used.

Written 2026-10-11, after the selection record in
`CS3_SELECTION_DRAFT.md` and before any harness code exists. Every
number below is a proposal until this file is hashed and committed.
After that, any change is an amendment written before the affected run,
in the style of `CS2_STEP3_AMENDMENT.md`.

**Draft 2 changes (second external review, same evening).** Added the
P1a event trace with compliance labels (section 3); split attribution
into a client-history flag and a library-property flag (section 5);
timestamps redefined (section 5); network schedules generated
independently of the library version (section 4); retry timeout and P3
targeting defined (sections 4 and 6); long-delay tail added to the
network model. Writing the P1a trace also corrected an error in draft 1
that the review did not raise: the stale read in #392 is **not** the
duplicated request (section 3).

## 0. Gates before hashing

1. **Remaining prior-art search.** Done in part on 2026-10-11:
   - etcd's robustness suite (`etcd-io/etcd` `tests/robustness`, at
     `f061acd`, 2026-10-08) already checks client histories with
     Porcupine under failpoints. Its issue table lists etcd #20418,
     "stale reads caused by process pausing", found in July 2025 by
     Antithesis, affecting v3.5.0 and v3.4.20, with no reproduction
     target in the suite. Raft #392 links to #20418, so the library bug
     this study uses as its positive control was first surfaced at the
     system level by commercial deterministic simulation.
   - **Formal-work search log, 2026-10-11, closed.** Search terms:
     "etcd raft ReadIndex linearizability formal verification 2025";
     "ReadIndex raft TLA+ specification read-only linearizable reads
     model checking"; "upamanyu sharma etcd raft read index bug
     verification". Results:
     - *Cirstea, Kuppe, Merz et al., arXiv 2404.16075 (2024).* Trace
       validation method; cases are two-phase commit, a
       snapshot-isolation store, EWD 998, two Raft implementations and
       CCF. etcd is mentioned only as a user of the method. No mention
       of ReadIndex, read-only requests or linearizable reads.
     - *Davis, Demirbas, Deng (MongoDB), "LeaseGuard: Raft Leases Done
       Right", arXiv 2512.15659 (Dec 2025).* TLA+ specification and a
       Python linearizability checker for its own lease protocol. Does
       not mention ReadIndex; cites etcd issue 166 on stale lease reads;
       does not mention raft #392 or duplicate read requests. Relevant to
       lease reads, which are out of scope here.
     - *`tla/` at the pinned commits* (selection record): no ReadIndex,
       lease or CheckQuorum modelling. A second external review reached
       the same reading of the message model and trace transitions.
     - The earlier claim that an etcd issue lists linearizability and
       leases as future model extensions was not confirmed by these
       searches and is not relied on.
     - Negative result: no formal or model-based work found that covers
       etcd raft's quorum-confirmed ReadIndex path. The search covers
       three queries on one engine and is not exhaustive. The claim
       carried into the report is scoped to that: the inspected
       specification and the literature found do not model this path;
       the trace-validation method itself is prior art, not this
       study's contribution.
   - **Internal prior art.** The project's own August 2026 study
     (`RAFT_RA003_TRACE_COMPLETENESS_INVENTORY.md`,
     `RAFT_RA005_CORRECTED_RESULT.md`, summarised in
     `FOUR_SYSTEM_SYNTHESIS.md`) established first that `MsgReadIndex`
     is untraced and that trace validation passes with a real ReadIndex
     in the execution. The specification check above corroborates it.
     See the selection record, "Prior internal work".
   - **Harness note from that study.** Its synchronous test helper
     produced artifacts (`RA-004`). This harness does not use it. It
     does deliver zero-delay messages within the same tick, in send
     order; that is a legal schedule (an instantaneous network), and
     linearizability does not depend on timing, so it cannot manufacture
     a violation. It could only narrow the schedules explored, which is
     why delays and long-delay tails exist.
2. **Consequence for criterion 5, stated now and kept in the final
   report.** Porcupine is not an independent choice relative to the
   conventional baseline: etcd's own robustness tests use it. The
   oracle is independent of the library's logic, not of etcd's existing
   practice. The question this study can answer is narrower: whether a
   direct-library harness with controlled adversarial schedules and
   library-level diagnostics adds coverage beyond that baseline.
3. **FoundationDB work finished in the repository**, so this file and
   the selection record can be committed without colliding.

## 1. Targets, pinned

| Item | Value |
| --- | --- |
| Positive control | `go.etcd.io/raft/v3` `v3.6.0`, `f35a02212416d045c574e30aa59d4b07c4b8d732` |
| Main target | `go.etcd.io/raft/v3` `v3.7.0`, `b867cf13f6bc0dae21204302df97bc2355c3af55` |
| Upstream reference test | `TestReadOnlyDuplicateRequest`, added in `9b9d6ee` (2026-02-28) |
| Oracle | `github.com/anishathalye/porcupine`, version and commit recorded at harness creation |
| Toolchain | Go version recorded at harness creation; `go.sum` committed |

The harness is one module built twice, once against each library
version, with no other code difference. A diff of the two builds'
`go.mod` must show only the raft version line.

## 2. Harness design

- **API level.** `RawNode`, driven by a single-threaded deterministic
  loop, so a seed reproduces a run exactly. `Node` wraps `RawNode`; the
  application contract quoted in the selection record is documented on
  `Node.ReadIndex` and applies to the same operation. `RawNode`'s own
  comment omits the retry sentence; this is recorded, not relied on.
- **Time.** Virtual ticks. `HeartbeatTick = 1`, `ElectionTick = 10`
  (the library's suggested ratio), `CheckQuorum = true`,
  `PreVote = true`, `ReadOnlyOption = ReadOnlySafe`.
- **Storage.** `MemoryStorage` per node. No crash-restart in this
  study; crash recovery is out of scope.
- **Ready handling, exactly per the README.** Persist entries, then
  HardState, then snapshot; send messages only after; apply committed
  entries in order; then Advance. The conformance check verifies this
  order on every Ready.

## 3. P1a: the upstream #392 sequence, with compliance labels

Source: `TestReadOnlyDuplicateRequest` at `9b9d6ee`. The upstream test
drives `raft` structs directly and skips Ready handling; the harness
reproduces the same message sequence through `RawNode` with the Ready
contract obeyed. Nodes 1, 2, 3; one client attached to each.

| # | Event | Actor | Label |
| --- | --- | --- | --- |
| 1 | Node 1 elected leader, term *t*, entry committed. Commit index *c1*. | Library | n/a |
| 2 | Client 2 calls `ReadIndex(ctxA)` on node 2; node 2 forwards `MsgReadIndex(ctxA)` to node 1. | Client | Compliant |
| 3 | Node 1 broadcasts heartbeats for ctxA. Nodes 2 and 3 respond; the network holds this first round of responses. | Network | Legal delay |
| 4a | Later heartbeat rounds are answered normally and node 1 confirms ctxA. Its `MsgReadIndexResp(ctxA)` to node 2 is held. | Library, network | Legal delay |
| 4b | No `ReadState` reaches node 2 within the 10-tick timeout. Client 2 calls `ReadIndex(ctxA)` again; node 2, still following node 1, forwards a second `MsgReadIndex(ctxA)`. The network holds it. | Client, then network | Retry: compliant with the published contract of `v3.6.0` and `v3.7.0`; non-compliant only with the unreleased `release-3.6` rule added in `5a1e8a2`. Hold: legal delay. |
| 5 | Node 1 is partitioned (traffic to and from it held). Its tick source stalls; it still processes messages. | Network, environment | Legal: partition modelled as delay; timing is outside the safety model |
| 6 | Nodes 2 and 3 elect a new leader in term *t*+1 and commit its entry. | Library | n/a |
| 7 | Client 3 writes value *w* through node 3; it completes when node 3 applies it, at index *iw* > *c1*. | Client | Compliant |
| 8 | **After** step 7 completes, client 1 calls `ReadIndex(ctxB)` on node 1, which still believes it is leader of term *t*. | Client | Compliant |
| 9 | Partition heals. The first messages to reach node 1 are, in order: the held retry `MsgReadIndex(ctxA)` from 4b, then the held first-round heartbeat responses from 3. | Network | Legal reordering after delay |
| 10 | **Bug on `v3.6.0`:** node 1's read-only queue holds ctxB ahead of the re-added ctxA. The held responses give ctxA a quorum, the queue is confirmed up to and including ctxA, and ctxB is confirmed with it. Node 1 emits `ReadState{ctx: ctxB, index: c1}`. | Library | n/a |
| 11 | Node 1 has applied through *c1*, so client 1's read B returns the value as of *c1*, which does not include *w*. | Client | Compliant |

**Why the history is non-linearizable.** The write of *w* completed
(step 7) before read B was invoked (step 8), yet B returned a value
older than *w*. Every action in the trace is either library behaviour,
a legal network delay or reordering, or a caller action compliant with
the published contract of both versions.

**Correction to draft 1.** Draft 1 required the flagged `ReadState` to
carry an rctx submitted more than once. In #392 the stale `ReadState`
is ctxB, submitted once; it is confirmed by acknowledgments gathered
for the duplicated ctxA. The P1 success condition in section 7 now
says so.

**Reachability under the main workload.** Steps 4 and 9 need a held
message to survive an election, which takes more than `ElectionTick` =
10 ticks. Draft 1's network (uniform 0-5 tick delay, isolation not
specified) could not produce that, so P1b could only have measured
nothing. Section 4 adds a long-delay tail and defines isolation as
holding traffic.

## 4. Network and workload schedules

**Version independence.** Everything exogenous is generated from the
seed before the run, independently of the library, and hashed:

- the client operation list for each client: type, write value, and a
  think time before invoking it;
- the fault timeline: isolation and pause windows with start tick,
  duration and target (a node ID, or the token `LEADER` for P3);
- the per-message fate function: each message's fate (deliver, drop,
  delay *d*) is a keyed hash of (seed, sender, receiver, per-link
  sequence number), not a draw from a shared random stream.

Both library versions therefore face the same faults at the same ticks
and the same fate for the *n*-th message on each link. Once the two
versions send different messages (for example, `v3.7.0` changes
heartbeat contexts), the *n*-th message on a link may differ in content
between versions. The harness records, per seed, the first tick at
which the two versions' message sequences diverge. P1b-P2 comparisons
are interpreted with that divergence point in view.

**Per-message fate.** Drop with probability 0.05. Otherwise delay
uniform 0-5 ticks with probability 0.98, or 10-40 ticks with
probability 0.02 (the long-delay tail). Both rates are judgement, not
measurement.

**Isolation.** One node, about once per 200 ticks, for 15-40 ticks.
Each message's fate (drop or delay) is decided when it is sent. A
message to or from an isolated node that comes due for delivery is
**held**, and released in hold order, immediately, when the window
ends.

**Pause.** One node, about once per 300 ticks, for 15-40 ticks. It
neither ticks nor processes; its inbound messages queue.

**Excluded from the main workload:** network duplication of any
message. Its legality for `MsgReadIndex` is undocumented. An
exploratory arm, labelled as such, may run it after P2 and P3.

**Cluster.** Three voters, bootstrapped, leader elected and one entry
committed before the first client operation. Five voters is exploratory
only.

**Clients.** Three, one per node, one operation outstanding each. One
register, initial value 0, write values unique across the run. Mix: 70
per cent reads, 30 per cent writes.

**Write.** `Propose` on the attached node; completes when that node
applies the entry carrying the value. No retries. A write not complete
within 60 ticks is recorded as incomplete. The harness records the log
index at which each write's entry was applied.

**Read, three levels kept in the trace.**

- *Logical read:* one client operation, one unique rctx.
- *Submission:* each `ReadIndex(rctx)` call for that read, numbered.
- *ReadState:* each `ReadState` received for that rctx, with its index.

If no `ReadState` arrives within 10 ticks of a submission, the client
submits again with the same rctx, up to 5 submissions, then records the
read as incomplete. The read returns when the first `ReadState` for its
rctx has arrived and the node's applied index has reached it.

**Why 10 ticks.** Under normal fates, a leader-local read completes in
about 11 ticks at worst (wait for the next heartbeat, then a 0-5 tick
round trip each way); a follower read adds a forward and a response,
about 21 ticks at worst. A 10-tick timeout is therefore **deliberately
aggressive**: it makes retries, and so duplicate submissions, routine,
because duplicate submission is the #392 trigger. The cost is that
retries are frequent for reasons unrelated to the bug. The harness
reports, per arm, the share of logical reads with more than one
submission, so that this is visible, not hidden.

## 5. Checks

**Timestamps.** Invocation and return are stamped with a global event
counter that increases by one on every simulator event (client invoke,
client return, message delivery, tick). The simulation is single
threaded, so this counter is the actual order in which the simulated
execution happened, not an imposed one. The counter is assigned to each
invocation event and each return event separately, at the moment the
event occurs, and both values are written to the history; an operation
is never stamped as a whole.

**Oracle self-test, run before every arm.** Hand-built histories with
known verdicts, encoded by the same code path the harness uses:
(a) two overlapping writes and a read that may legally see either,
expected linearizable; (b) a write that returns before a read is
invoked, the read seeing the older value, expected non-linearizable;
(c) the same as (b) but with the read invoked before the write returns,
expected linearizable; (d) the section 3 history replayed from a
recorded P1a run, expected non-linearizable. Any mismatch halts the
arm. Cases (b) and (c) differ only in event order and are what show
that the encoding preserves real-time order without inventing it. No two events share a value,
so Porcupine's closed intervals never create or remove an ordering by
accident. The virtual tick is recorded alongside for logs and replay.

This departs from the review's suggestion to stamp with ticks alone.
Tick-only stamps would make every pair of operations that share a tick
boundary overlap, which can only hide real-time orderings the execution
did establish and so can only mask violations. The counter neither
masks nor invents them.

**Oracle (verdict).** Porcupine, single-register model. Incomplete
writes get an infinite return time. Incomplete reads are removed. A
check that hits the 60-second limit per history is recorded as
**unknown**, never as a pass.

**Attribution, two flags, both recorded:**

- **Client-history flag (observable staleness).** For each logical
  read, the lower bound is the log index of the latest write whose
  completion precedes the read's invocation. A `ReadState` index below
  that bound is flagged. This is what can make a history
  non-linearizable, and it is the flag the P1 success condition uses.
- **Library-property flag (diagnostic).** The highest commit index on
  any node at the moment of each submission. A `ReadState` index below
  it is flagged as a breach of the property the upstream test asserts.
  It is recorded because it is the library's own correctness condition,
  but it is not by itself evidence of an observable stale read: entries
  committed but not yet acknowledged to any client are concurrent with
  the read.

Each flag records the rctx, its submission count, the leader terms
involved, and which other rctxes were pending in the same leader's
read-only queue.

**Conformance.** Every Ready processed in contract order; no message
sent before its batch was persisted; reads served only after applied
index reached read index; an rctx reused only for submissions of the
same logical read. A failing trial is discarded and counted, not
analysed.

**Determinism.** Each violation, and a random 2 per cent of all
trials, is re-run from its seed; the history file must hash
identically. A mismatch halts the arm.

## 6. Arms, budgets and stopping rule

| Arm | Library | Schedule | Seeds | Ops per trial |
| --- | --- | --- | --- | --- |
| P1a | v3.6.0 | Directed: section 3 trace | 1 schedule, plus 20 seeds of timing jitter on non-essential events | as needed |
| P1b | v3.6.0 | Randomized, section 4 | 1-2000 | 300 |
| P2 | v3.7.0 | Randomized, same pre-generated schedules as P1b | 1-2000 | 300 |
| P3 | v3.7.0 | Section 4 with isolation and pause targeted at the leader | 2001-3000 | 300 |

**P3 targeting rule.** A fault window whose target is `LEADER` resolves,
at its start tick, to the node that is leader in the highest term any
node has observed. If no node is leader at that tick, the window is
skipped and recorded as skipped. The resolved target is written to the
trial's record, so the actual schedule can be replayed exactly.

A trial ends when all 300 operations have completed or are recorded
incomplete, or at 6000 ticks.

Stopping rule: every pre-registered seed in an arm is run, whatever the
early results. No seeds are added after results are seen; any extra run
is exploratory and labelled.

## 7. Success criteria and interpretation

- **P1a succeeds** if at least one directed run yields a
  non-linearizable history that replays from its seed, passes
  conformance, and shows a client-history flag on a `ReadState` whose
  rctx was submitted once and that was confirmed while a duplicated
  submission of a different rctx was pending in the same stale leader's
  queue (section 3, step 10). Otherwise the harness is judged
  insensitive and nothing further is run.
- **P1a was already exercised in development** (`DEV_LOG.md`): on a
  v3.6.0 build from release source, the canonical schedule and 20
  development jitter values (1001-1020) all met the success condition,
  and on a development-only patched copy of v3.7.0 the canonical
  schedule did not confirm read B. The outcome of the scored P1a is
  therefore expected. Its purpose is to confirm the same result on the
  pinned, unmodified builds under Go 1.26, not to test a hypothesis
  that is still open.
- **P1a validates the harness for this failure mode only.** It shows
  that the oracle, the timestamps and the flags can detect #392 when
  the schedule reaches it. It does not show that the randomized
  workload reaches it.
- **P1b is a measurement, not a gate.** Report how many of the 2000
  randomized `v3.6.0` trials show the section 3 shape. If none do, a
  clean P2 shows only that the randomized workload did not reach that
  failure mode on either version, and must be reported that way.
- **P2 and P3 predicted clean.** A clean result supports only this
  statement: a harness shown able to detect #392 found no violation
  under these pre-registered schedules on `v3.7.0`. It is not a proof of
  linearizability and not evidence that CBV outperforms conventional
  testing.
- **Any P2 or P3 violation** is triaged in this order: history well
  formed, conformance passed, deterministic replay, attribution flags.
  Only a violation that survives all four is reported as a possible
  defect, and only after manual trace review.
- **Unknown verdicts** are reported as a count. If more than 1 per cent
  of trials in an arm are unknown, the arm is reported as inconclusive.

## 8. Artifacts and hashing

Before any run: this file, the harness source, `go.mod` and `go.sum`
for both builds, the seed lists, and the pre-generated schedule file
for every seed (with a per-seed schedule hash) are hashed into
`case_study_3_raft/HASHES_BEFORE_RUN.txt` and committed. Each trial
writes its history (JSON lines) and a result row (seed, arm, verdict,
both flags, submission counts, conformance, divergence tick, ticks).
Summary scores come from a script committed before the run. As in Case
Study 2, pre-run hashes are recorded in the working session and are not
externally timestamped.

## 9. Out of scope

Crash-restart and storage faults; lease-based reads; joint-consensus
membership changes during reads; network duplication (exploratory only);
clusters other than three voters (exploratory only); etcd's server layer
and client library.

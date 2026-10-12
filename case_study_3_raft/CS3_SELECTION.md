# Case Study 3: selection record

Written 2026-10-11, before any test was run. Nothing in this file has
been executed. Source checked: git `master` at `6de20f6` (2026-10-06);
manuals on git-scm.com (git-update-ref, last updated 2.53.0; reftable,
last updated 2.43.0).

## History that this entry corrects

On 2026-08-24 a working session applied the seven steps to git's object
model and reproduced the pre-2.46.0 `transfer.fsckObjects` bundle-fetch
gap on git 2.43.0. None of it was committed: the repository has no
commits between `6704583` (2026-08-20) and `5f72a9c` (2026-10-11), and no
file mentions it. It was not pre-registered or hashed, and its evidence
no longer exists. It is recorded here as an unregistered pilot and is
not cited as evidence for anything below.

## Candidate guarantee

`git push --atomic`, per the git-push manual: either every ref is
updated, or, on error, none are. The wording is not limited to lock
failures or rejected updates.

Scope for this study: a receiving repository on the default "files"
ref backend, with the error or interruption occurring after the
transaction has begun committing.

## Five-point screen

1. **Narrow, falsifiable guarantee.** Met. A sampled ref state is either
   all-old, all-new, or mixed; mixed falsifies the claim.
2. **Enforcement boundary.** Met. `receive-pack` passes the updates to a
   ref transaction. In the files backend, `files_transaction_finish`
   (`refs/files-backend.c`, about lines 3349-3389) renames each lock file
   into place in a loop. A failure on ref *k* jumps to `cleanup:`, which
   releases the remaining locks; refs 1 to *k*-1 stay committed and are
   not restored. The reftable backend commits with one rename of
   `tables.list`.
3. **Reachable adversarial states.** Partly met. An external kill during
   the loop is physically realistic (crash, OOM kill, power loss) but has
   not yet been shown to land without debugger timing. A rename failure
   on ref *k* is reachable only by fault injection and would be labelled
   as such.
4. **Independent oracle.** Met for files: a ref reader written for this
   study parses loose ref files and `packed-refs` directly. Weaker for
   reftable unless a minimal reader is written from the published spec.
5. **Conventional baseline.** **Not met. See prior art.**

## Prior art (searched 2026-10-11)

Git's own documentation already states the limitation:

- `Documentation/BreakingChanges.adoc`, published on git-scm.com, lists
  among the reasons for moving to reftable that multi-reference writes
  are not atomic with the files backend, so git can see in-between
  states while a transaction is committing.
- `refs.h` documents `ref_transaction_commit` as committing "as
  atomically as possible" and rolling back on failure. The files-backend
  finish step does not restore refs it has already renamed, so the
  roll-back sentence overstates what that code path does.
- Ref-transaction atomicity has been discussed on the git mailing list
  since at least 2014.

What remains unstated anywhere user-facing: the git-push `--atomic`
entry (and `git replay`'s "all-or-nothing" wording) do not carry the
files-backend qualification, and BreakingChanges speaks of transient
in-between states seen by readers, not of a persistent mixed state left
behind by a crash or a failed rename.

## Predictions (to be hashed before any run, if the study proceeds)

- **P1.** Files backend, external kill during commit, *N* trials: at
  least one trial leaves a persistent mixed state.
- **P2.** Reftable backend, same procedure: no mixed states.
- **P3.** Files backend, injected rename failure on ref *k*: push reports
  failure and refs before *k* are updated.
- **Falsification rule.** If P1 shows no mixed state across the planned
  trials, with timing evidence that kills landed inside the commit
  window, P1 is recorded as false.

## Assessment against the switching rule

The rule set at selection was: switch to etcd/Raft if the limitation is
already documented to users, or if P1 is reachable only with debugger
timing. The first condition is substantially met. A conventional
reading of git's own documentation finds the core limitation without
the protocol. If the study proceeds, the most it can claim is a
documentation-scope result: two user-facing manuals state a guarantee
broader than one backend enforces, and one internal comment overstates
roll-back. It would be the third case study in a row that confirms a
gap someone else had already identified, and the second, after the
August pilot, with the same shape.

## Decision

2026-10-11, operator: **Git screened out at selection.** No step 3
construction will be run. Case Study 3 moves to etcd's Raft
implementation, which faces the same five-point screen and switching
rule before any run.

This is the first time the screen stopped a target before any execution.
It is recorded as a result of the selection procedure, not as a case
study, and makes no claim about git beyond the documentation cited
above.

---

# Case Study 3, second candidate: etcd Raft (screen, not yet run)

Source checked: `etcd-io/raft` `main` at `638f427` (2026-10-09); latest
release `v3.7.0` (2026-06-03). Go. A library that implements only the
Raft state machine; network and storage are supplied by the application.

## Candidate guarantee

The default read mode. `raft.go` (lines 61-62 and 235-236) states that
`ReadOnlySafe` guarantees the linearizability of read-only requests by
communicating with a quorum. The README adds that followers obtain a
safe read index from the leader. Unlike the lease-based mode, which is
documented as unsafe under unbounded clock drift, the safe mode carries
no stated condition.

Scope for this study: `v3.7.0`, `ReadOnlySafe`, reads issued at the
leader and forwarded from followers, under leader changes and an
asynchronous network that may drop, delay, duplicate or reorder
messages. The application side (harness) follows the README's Ready
contract exactly; a violation traced to the harness breaking that
contract is a harness bug, not a finding.

## Five-point screen

1. **Narrow, falsifiable guarantee.** Met. Every read returning through
   a `ReadState`, served after the node has applied through that index,
   must be consistent with some linearization of the full operation
   history. One non-linearizable history falsifies it.
2. **Enforcement boundary.** Met. `stepLeader` `MsgReadIndex`
   (`raft.go` about 1354-1372) answers single-voter clusters directly,
   otherwise postpones until the leader has committed an entry in its
   own term (`committedEntryInCurrentTerm`), then confirms leadership by
   heartbeat acknowledgments tracked in `read_only.go`. Followers
   forward to the leader (`raft.go` about 1764-1770). The application
   must wait until applied index reaches the returned read index.
3. **Reachable adversarial states.** Met without fault injection. The
   library treats the network as asynchronous and unreliable, and the
   application owns delivery, so any drop, delay, duplicate or reorder
   is legal input. A deterministic harness can drive any schedule.
4. **Independent oracle.** Met. A general linearizability checker
   (Porcupine) over the client-observed history of a single register.
   It shares none of the library's internal assumptions.
5. **Conventional baseline.** Met, and stronger than in either earlier
   study. Three exist:
   - The project's TLA+ specification and trace validation (`tla/`).
     Its eight invariants cover leader election, log matching, leader
     completeness and durability of committed entries. It does not
     model ReadIndex, lease reads, CheckQuorum, PreVote or leadership
     transfer (no matches in `etcdraft.tla`).
   - Unit and data-driven tests, including duplicate `MsgReadIndex`
     requests with delayed heartbeats (`9b9d6ee`, 2026-02-28).
   - etcd's system-level robustness tests, which check linearizability
     of the full key-value store and so cover reads only indirectly.

## Prior art (searched 2026-10-11)

The read path had a real linearizability bug recently. Issue #392
reported that with retried or duplicate read-only requests the read
index could be stale. PR #397 fixed it (merged 2026-03-09) by using a
unique index as the heartbeat context and one shared set of
acknowledgments; PR #398 documents that ReadIndex must not be retried
with the same request context. The fix is in `v3.7.0` and absent from
`v3.6.0`.

Consequences for this study:

- The specific known bug cannot be counted as a discovery.
- It provides a positive control: a harness and oracle that cannot
  detect #392 on `v3.6.0` are not sensitive enough to support a clean
  result on `v3.7.0`.
- See "Caller contract for P1" below for whether reproducing #392
  requires a non-compliant caller.

## Caller contract for P1 (resolved 2026-10-11, after external review)

An outside review asked whether reproducing #392 would require the
harness to break the application contract, which would make P1 a test
of invalid caller behaviour. Checked against the source:

- **The v3.6.0 contract as released** (`f35a022`, 2025-02-05,
  `node.go` lines 217-224) says only that requests can be lost and that
  retrying ReadIndex is the user's job. It places no restriction on
  reusing a request context.
- **The restriction came later.** `5a1e8a2` (2026-03-09, PR #398)
  added to the `release-3.6` branch a rule that retries must use a new
  context. No release after `v3.6.0` has been tagged on that branch, so
  the rule exists only in unreleased branch documentation, written in
  response to #392.
- **v3.7.0 lifts it.** The same comment states that from release-3.7 a
  retry may reuse the context, and the `v3.7.0` `node.go` carries the
  original retry wording with no restriction.
- **The upstream regression test** (`TestReadOnlyDuplicateRequest`,
  `9b9d6ee`) states that the duplicate can come from the network itself
  or from a user retrying ReadIndex. The maintainers' position on
  network duplication of `MsgReadIndex` is not documented; a reviewer
  on #398 said message delivery is the application's responsibility,
  and a proposal to document that it must not be duplicated was not
  adopted.

Consequence: a caller that retries ReadIndex with the same context is
compliant with the contract as published for both `v3.6.0` and
`v3.7.0`. P1 and P2 can therefore use one workload, with retries
issued by the client layer, not by network duplication. The P1 record
must say that the `v3.6.0` behaviour is compliant with the contract as
released and non-compliant with the later, unreleased branch rule.
Network duplication of `MsgReadIndex` is excluded from the main
workload because its legality is undocumented; it may be run as a
labelled exploratory variant only.

An earlier version of this draft said the harness must honour the #398
rule. That was wrong for both target versions and is withdrawn.

## Claim levels

- **Primary, end to end:** an application that follows the published
  contract and serves reads through ReadIndex produces client histories
  that are linearizable. Judged by Porcupine on client-observed
  histories.
- **Secondary, library level:** every `ReadState` returned has an index
  at least the commit index of a leader at the time the request was
  issued, which is the property the upstream test asserts. Used to
  attribute an end-to-end violation, not as an independent verdict.
- **Harness conformance:** a separate check, run on every trial, that
  the harness obeyed the Ready contract (persist before send, apply in
  order, Advance after processing, serve a read only after applied index
  reaches its read index). A trial that fails conformance is discarded
  and reported.

## Formal baseline, pinned

`tla/etcdraft.tla` is byte-identical at `v3.6.0`
(`f35a02212416d045c574e30aa59d4b07c4b8d732`), `v3.7.0`
(`b867cf13f6bc0dae21204302df97bc2355c3af55`) and `main` `638f427`;
SHA-256 prefix `15c445684529c59a`; last changed 2024-04-18 (`195edd6`).
That version's invariants are the eight listed above. No file in `tla/`
at `v3.7.0` models ReadIndex, lease reads or CheckQuorum. This is a
statement about that specification at those commits, not about formal
work on etcd generally. The external search is logged in
`CS3_EXECUTION_PLAN.md` section 0.

## Prior internal work: the August 2026 etcd raft study

**This selection is not the project's first look at etcd raft, and the
paragraph above is not the first finding about its read path.** In
August 2026 the project selected `etcd-io/raft` v3.7.0
(`RAFT_CASE_STUDY_BASELINE.md`, claims R-1 to R-6) and worked R-6,
model/implementation correspondence, in `RA-001` to `RA-006`. That work
was summarised in `FOUR_SYSTEM_SYNTHESIS.md`, committed in `5f72a9c`;
the RA files themselves were committed later, in a separate commit, so
that the synthesis's references resolve. Like the August FoundationDB
study cited in Case Study 2, it was not an application of the seven
steps and is not counted as one.

What it established that bears on this study:

- **`RA-003`** inventoried every trace call site in `raft.go` and every
  message type in the step functions. `MsgReadIndex` and
  `MsgReadIndexResp` have no trace call. ReadIndex is one of a cluster of
  untraced extensions (PreVote, CheckQuorum, leadership transfer,
  ReadIndex), while the core replication path is fully traced. The
  "Formal baseline, pinned" paragraph above re-checks that from the
  specification side at the pinned commits; it corroborates `RA-003`
  and is not a new finding.
- **`RA-005`**, on a harness built on the production `Node` API, issued
  a real ReadIndex with `CheckQuorum` and `ReadOnlyLeaseBased`. The trace
  contained 0 of 2,384 events for it, and TLC trace validation completed
  with no error. The validation layer accepts executions containing
  read-safety decisions it never observes. `FOUR_SYSTEM_SYNTHESIS.md`
  classifies this as Category 1, unobserved behaviour.
- **What it did not establish.** `RA-005` states that consensus safety
  was never tested and that its finding concerns only what the
  validation layer can see. No August construction tested whether reads
  are linearizable, used `ReadOnlySafe`, or touched issue #392. Nothing
  in it bears on P1-P3.

**How this changes the selection.** The candidate is the direct
follow-up to the August finding. August showed that etcd raft's own
model-to-implementation check cannot see ReadIndex. This study tests
whether the behaviour that check cannot see is correct, with an oracle
that does see it. That is a stronger reason for the selection than the
external screen alone, and it means the "formal baseline does not cover
the read path" point is the project's own earlier result, cited, not a
discovery made at selection.

**Selection criterion, disclosed.** The criteria exclude anything
"already examined here". etcd raft was examined in August, though not
under the seven steps and not on this claim. As with FoundationDB in
Case Study 2, the overlap is disclosed rather than treated as
disqualifying.

**Harness lessons carried over.** `RA-002` and `RA-004` were retracted
because upstream's synchronous `network.send` test helper produced
traces that failed trace validation even for a plain control (`RA-004`,
`RA-005`). Building `RA-005`'s production harness then exposed two
Ready-contract omissions of its own: committed `EntryConfChange`
entries not passed to `ApplyConfChange`, and Ready entries and
HardState not persisted to `MemoryStorage`. This study's harness avoids
the test helper, drives `RawNode` through the Ready contract, persists
entries, HardState and snapshot on every Ready, and checks that order
per Ready. It starts nodes from a snapshot that already holds the
three-voter configuration and proposes no configuration changes, so no
`EntryConfChange` entry is ever committed; the conformance check
records it if one appears.

## Predictions (to be hashed before any run)

- **P1, positive control.** On `v3.6.0`, with duplicate ReadIndex
  requests and delayed heartbeats, the harness produces at least one
  non-linearizable history. If it does not, the harness is judged
  insensitive and P2 is not run.
- **P2, main claim.** On `v3.7.0`, across the planned randomized
  schedules, no non-linearizable history occurs under `ReadOnlySafe`.
  The expected outcome is a pass: the path was reworked and reviewed
  this year.
- **P3, follower reads.** Same as P2, restricted to reads forwarded from
  followers during leader changes. Expected: pass.
- **Falsification rule.** Any non-linearizable history under P2 or P3
  that survives replay and is not traced to a harness contract breach
  falsifies the prediction.

**What counts as P1 succeeding.** Not merely a checker failure. The
violating history must replay from its seed, pass harness conformance,
and show the #392 shape: a `ReadState` for one request, submitted once,
returned with an index below the client-history bound, and confirmed
while a duplicated submission of a different request was pending in the
same stale leader's queue. A violation of any other shape does not
satisfy P1. (An earlier wording required the stale request itself to be
the duplicated one; that misread #392 and was corrected in the
execution plan, draft 2, section 3.)

**Outcome ladder.**

- P1 not reproduced: harness not shown sensitive. Stop and diagnose;
  P2 and P3 are not run or interpreted.
- P1 reproduced: sensitivity shown for the #392 failure mode under a
  workload compliant with the released contract.
- P1 reproduced, P2 and P3 clean: supports only a bounded statement,
  that this harness, able to detect #392, found no violation in the
  pre-registered `v3.7.0` workload. It does not show linearizability for
  all legal executions, and it does not show that CBV outperforms
  conventional testing.
- P2 or P3 violation: first confirm the history is well formed and the
  harness conformant, then replay and trace through the library-level
  check before claiming a defect.

**Still to be fixed before hashing.** Cluster size and initial state,
client placement, read/write mix, fault schedule (loss, delay,
reordering, leader changes), seeds, trial and operation counts,
timeouts, stopping rule, Porcupine model and treatment of incomplete
operations. These go in an execution plan written after this selection
is accepted.

## Assessment against the switching rule

Neither switching condition is met. The read guarantee is stated
without condition in the user-facing API, it is not covered by the
formal specification, and adversarial schedules are legal input. Unlike
the earlier studies, the expected result is a pass. A pass under a
harness that has first caught a known bug is a meaningful result; a
pass alone is not.

# Raft Case Study — Selection Record, Evidence Baseline, and Decomposition Map

**Status:** selection, claim freeze, and decomposition map only. No
construction, no adversarial test, no fix. Matches the discipline applied
to `T-4a`/`T-6a`/the FoundationDB baseline before any construction began.

---

## Selection

**Implementation chosen: `etcd-io/raft` v3.7.0** — the standalone Go Raft
library extracted from etcd. Confirmed from its own real README (not
inferred): "As of 2016, it is the most widely used Raft library in
production... powers distributed systems such as etcd, Kubernetes,
Docker Swarm, Cloud Foundry Diego, CockroachDB, TiDB, Project Calico,
Flannel, Hyperledger." Deliberately minimalist: "the library only
implements the Raft algorithm; both network and disk IO are left to the
user" — a real, structural difference in scope from Phoenix A (a full
execution engine), Temporal (a full workflow orchestration platform), and
FoundationDB (a full distributed database) — this is consensus alone,
nothing else, which sharpens rather than dilutes the case study.

**Why this satisfies the case-study selection criteria, checked against
real evidence, not assumed:**

1. **Genuinely deterministic execution/simulation** — real, dedicated
   test infrastructure found: `raft_paper_test.go` (tests named directly
   after paper-cited behaviors), `interaction_test.go`, and a `tla/`
   directory shipping a full TLA+ specification with trace-validation
   tooling.
2. **Persistent state whose correctness matters** — the replicated log
   itself (`log.go`, `log_unstable.go`, `storage.go`).
3. **Integrity/consistency-relevant artifacts** — terms, log indices,
   commit index, the exact artifacts named in the paper's own safety
   properties.
4. **Explicit architectural correctness claims** — confirmed directly:
   the library's own README states it is "up to date with the final Raft
   thesis," while explicitly naming one deliberate deviation (membership
   change timing) and stating its own safety justification for that
   deviation ("equivalent in terms of safety, since the old and new
   configurations are guaranteed to overlap") — an unusually
   self-aware, precisely-scoped claim, worth taking at face value and
   testing rather than assuming.
5. **Enough complexity to contain real seams** — leader election, log
   replication, membership change, and snapshotting are each real,
   separately testable subsystems (confirmed via file structure:
   `raft.go`, `confchange/`, `tracker/`, `quorum/`).
6. **A genuinely different enforcement philosophy** — confirmed, and
   this is the sharpest of the four systems studied so far. Phoenix A:
   cryptographic hash-chain provenance over one execution. Temporal:
   replay comparison against a persisted Command history. FoundationDB:
   deterministic simulation of an entire distributed system under fault
   injection. Raft: **quorum-based agreement enforced through explicit,
   named formal invariants**, with a **shipped, real TLA+ model plus
   trace-validation machinery bridging model and implementation** — a
   structurally distinct verification philosophy from all three prior
   case studies.

## Evidence Baseline — R-1 through R-6, frozen before construction

### R-1 — Election Safety

- **Exact source:** the original paper (`raft.github.io/raft.pdf`,
  Figure 3, corroborated by the Stanford ATC'14 paper).
- **Exact claim:** "At most one leader can be elected in a given term."
- **What enforces it, per the paper:** each server votes for at most one
  candidate per term (first-come-first-served within a term), and a
  candidate needs a majority of votes to become leader — two
  non-overlapping majorities cannot both exist for the same term.
- **What the implementation-level enforcement is:** not yet traced to
  `raft.go` source in this pass — the exact vote-bookkeeping code path is
  the natural first target for construction.

### R-2 — Leader Append-Only

- **Exact claim:** "A leader never overwrites or deletes entries in its
  log; it only appends new entries."
- **What the library's own test names suggest is covered:**
  `TestLeaderStartReplication`, `TestLeaderCommitEntry` — direct,
  paper-named test coverage exists; not yet read for what they actually
  assert.

### R-3 — Log Matching

- **Exact claim:** "If two logs contain an entry with the same index and
  term, then the logs are identical in all entries up through the given
  index."
- **What enforces it, per the paper:** the `AppendEntries` consistency
  check — a leader includes the term and index of the entry immediately
  preceding new entries; a follower rejects the append if it can't find a
  match.
- **Directly relevant real test found:** `TestFollowerCheckMsgApp`,
  `TestLeaderSyncFollowerLog`.

### R-4 — Leader Completeness

- **Exact claim:** "If a log entry is committed in a given term, that
  entry will be present in the logs of the leaders for all
  higher-numbered terms."
- **What enforces it, per the paper:** the election restriction — a
  voter refuses its vote if the candidate's log is less up-to-date than
  its own (compared by last-entry term, then index).
- **Directly relevant real test found:** `TestVoteRequest`, `TestVoter`,
  `TestLeaderOnlyCommitsLogFromCurrentTerm` — this last one is
  particularly notable, since it names a specific, well-known subtlety in
  Raft's commit rule (a leader cannot conclude an entry from a *previous*
  term is committed purely by counting replicas, even with a majority —
  it must commit an entry from its *current* term first). Worth reading
  directly before construction.

### R-5 — State Machine Safety

- **Exact claim:** "If a server has applied a log entry at a given index
  to its state machine, no other server will ever apply a different log
  entry for the same index."
- **What the paper states this follows from:** the conjunction of R-3
  and R-4, plus servers applying entries in log-index order — stated as
  a derived property, not independently enforced by its own separate
  mechanism. This is itself worth verifying directly in source rather
  than accepting the paper's own proof sketch as sufficient for the
  *implementation* — exactly the model-vs-implementation gap this whole
  case study exists to probe.

### R-6 — Model/implementation correspondence (the Raft analogue of F-5/F-6)

- **Exact source:** `tla/README.md`, real, shipped with the library.
- **Exact claim, quoted directly:** "The correctness of applications
  that implements a consensus algorithm is ensured by two factors: the
  correctness of the algorithm itself, and adherence of the
  implementation to algorithm specification... The first factor... is
  assured through model checking the specification. The second one...
  is fortified through trace validation, which serves to bridge the gap
  between the model and its implementation."
- **What enforces it, per documentation:** trace log points injected at
  specific state-transition points in the real Go implementation
  (`SendAppendEntries`, `BecomeLeader`, named explicitly), built with a
  `with_tla` build tag; traces are fed as NDJSON into a TLA+
  specification (`Traceetcdraft.tla`) which constrains the model's state
  space to match the traced execution.
- **What the documentation doesn't say, flagged precisely rather than
  assumed:** whether trace validation is run routinely (CI-integrated)
  or is a manual, occasional process; whether the injected trace points
  cover *every* state transition relevant to R-1 through R-5, or only a
  subset (the two named examples, `SendAppendEntries` and
  `BecomeLeader`, are illustrative, not stated as exhaustive); and —
  most directly analogous to this whole case study's recurring theme —
  whether trace validation passing establishes that the five safety
  properties *hold*, or only that the traced execution didn't visit a
  state the model doesn't recognize. This last distinction is precisely
  the `CI-005`/FDB-`ConsistencyCheck`-shaped question, and is the
  natural target for `R-6`'s eventual construction.

---

## Decomposition Map

| Claim | First question | Mechanism to inspect | Status |
|---|---|---|---|
| **R-1** Election Safety | What exactly prevents two leaders in one term? | Vote-granting logic in `raft.go` | Not started |
| **R-2** Leader Append-Only | Is this enforced structurally or only by convention? | Log-mutation call sites in `raft.go`/`log.go` | Not started |
| **R-3** Log Matching | What does the `AppendEntries` consistency check actually verify, and what can defeat it? | `raft.go`'s append-handling logic; `TestFollowerCheckMsgApp` | Not started |
| **R-4** Leader Completeness | Does the vote-granting up-to-date check actually get enforced identically to the paper's stated comparison rule? | `raft.go`'s `RequestVote` handling; `TestVoteRequest`/`TestVoter` | Not started |
| **R-5** State Machine Safety | Is this independently enforced, or purely a derived consequence of R-3+R-4 — and does the implementation actually preserve that derivation? | Apply-ordering logic; whether any direct check exists beyond R-3/R-4 | Not started |
| **R-6** Model/implementation correspondence | Does passing trace validation establish the five safety properties hold, or only that no *recognized* deviation occurred? | `tla/Traceetcdraft.tla`, the trace-injection points, whether trace validation runs in CI | Not started, but this is the claim most directly parallel to FoundationDB's `F-5`/`F-6` and Temporal's `T-1`/`T-2` oracle-independence questions — a strong candidate for where the case study's most interesting result may lie |

## Explicitly not done

No source read beyond file/test names and the directly-quoted `tla/README.md`
passage. No construction. No adversarial test. Per the standing
instruction not to assume prior case studies' failure modes transfer:
nothing here presupposes Raft has a Temporal-shaped or FoundationDB-shaped
gap — the decomposition map above is built from what Raft's own real
source and documentation state about itself, and the next step (reading
`raft.go`'s actual enforcement code for whichever claim is chosen first)
is a deliberate, separate decision.

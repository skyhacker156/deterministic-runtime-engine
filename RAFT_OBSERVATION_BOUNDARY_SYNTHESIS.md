# Raft Observation Boundary Synthesis

**Status:** synthesis of the completed Raft case study (`T-4a`-style
decomposition through `RA-006`). No further construction. This is the
freeze point for the Raft investigation.

---

## 1. What is formally modeled

The real, shipped `Traceetcdraft.tla` specification, run against real
`etcd-io/raft` execution traces via real TLC model-checking (confirmed
working, not merely described): the core replication path — leader
election via `MsgVote`/`MsgVoteResp`, log replication via
`MsgApp`/`MsgAppResp`, commit-index advancement, and configuration
changes (`ApplyConfChange`). This maps cleanly onto the five formal
safety properties from the original Raft paper (`R-1` through `R-5`,
`RAFT_PHASE2_ENFORCEMENT_DECOMPOSITION.md`), each of which was traced to
a specific, real enforcement mechanism in source and a specific,
real test that exercises exactly that mechanism — no gaps found across
that base layer.

## 2. What is implemented but omitted

Confirmed by direct source reading (`RAFT_RA002_TLA_DECOMPOSITION.md`,
`RAFT_RA003_TRACE_COMPLETENESS_INVENTORY.md`) and then independently
confirmed by real execution and real TLC validation on a corrected
production-path harness (`RA-005`, `RA-006`):

- **PreVote** (election-safety extension, thesis section 9.6) — messages
  and the `PreCandidate` state entry are both entirely absent from the
  trace vocabulary and the TLA+ model.
- **ReadIndex** (`ReadOnlyLeaseBased` mode) — a real, materially
  consequential linearizable-read mechanism that touches zero traced
  state fields and produces zero trace events.
- **Leadership transfer** (`MsgTransferLeader`/`MsgTimeoutNow`) — the
  coordinating messages are entirely untraced.

All three were confirmed, on the corrected harness, to **fail open**:
real, independently-verified occurrence, zero trace footprint, and a
full, 100%-progress, error-free TLC validation of the resulting
execution.

## 3. What is represented but causally ambiguous

A structurally different, fourth case, found but deliberately not
constructed further (`RAFT_RA006_BEHAVIORAL_CATEGORIES.md`): **`CheckQuorum`**-triggered
leader stepdown. Unlike categories in section 2, the resulting
`BecomeFollower` transition *is* traced — but `traceEvent`'s own
implementation (read directly) records only the resulting state
(`term`, `vote`, `commit`, `role`), not the cause. A quorum-loss-driven
stepdown is trace-identical to any other stepdown. This is not
invisibility; it is **collapse of distinct causes into one observable
signature** — a different failure mode of the same underlying
phenomenon, worth naming separately rather than folding into the same
bucket as PreVote/ReadIndex/transfer.

The leadership-transfer finding itself also has a causal-ambiguity
dimension worth restating here: the *resulting election* is fully
traced, but is indistinguishable from an accidental one. It belongs in
both section 2 (the coordinating messages are omitted) and this section
(the resulting state is ambiguous as to cause).

A fifth, minor item: `rsmSendSnapshot`/`rsmReceiveSnapshot` are declared
trace-event constants never actually emitted — `MsgSnap` is silently
recorded as an ordinary `AppendEntriesRequest`/`Response`. A labeling
inconsistency between the vocabulary's apparent design and its actual
behavior, not a genuine observation-boundary gap.

## 4. What the validation results actually establish

**Precisely, and no further:** for the tested constructions, on a
harness now confirmed correct, real executions containing real,
independently-verified PreVote, ReadIndex, and leadership-transfer
activity each produced a complete, error-free TLC validation. This
establishes that the trace-validation layer's assurance is scoped
strictly to the state space it tracks — it says nothing, and was never
designed to say anything, about mechanisms operating outside that
space. **No safety-property violation was found, attempted, or implied
anywhere in this case study.** Every construction stopped at the
validation-layer boundary, exactly as scoped from `RA-002` onward.

---

## The RA-002 retraction, included as evidence of method, not as noise

This case study's evidentiary record includes a real, documented
self-correction, preserved here deliberately:

1. **Hypothesis:** PreVote's untraced `PreCandidate` transition causes
   `TraceMatched` to fail (`RA-002`, first construction).
2. **Adversarial construction:** a real 3-node cluster, PreVote enabled,
   real trace captured, real TLC run — result: `TraceMatched was
   violated`, diverging at the exact untraced transition. The hypothesis
   appeared confirmed.
3. **Confound discovered:** a clean control (zero extensions enabled)
   was constructed for the fail-open/fail-closed follow-on question
   (`RA-004`) — and it *also* failed `TraceMatched`, at the same
   structural point, with no PreVote involvement at all. The original
   attribution could not survive this control.
4. **Root cause isolated:** the project's own shipped `example.ndjson`
   (4,888 real events) validated cleanly against the identical spec,
   exonerating the tooling and specification. The fault was isolated to
   this case study's own synchronous test-harness helper, confirmed by
   building a second, correct harness on the real, documented `Node` API
   Ready-loop pattern — which surfaced two genuine bugs in that
   rebuild (skipped `ApplyConfChange`, skipped storage persistence),
   both fixed and disclosed.
5. **Hypothesis retracted and replaced (`RA-005`):** on the corrected
   harness, the *same* PreVote-enabled scenario validated with **zero
   errors** — the opposite of the original finding.
6. **Independent construction, surviving proposition (`RA-006`):** a
   third, structurally different mechanism (leadership transfer) tested
   on the now-trusted harness, producing the same clean-validation
   result — converting a single (and, it turned out, wrong) data point
   into a repeated, cross-category structural finding.

This sequence — hypothesis, adversarial construction, confound
discovery, control, retraction, independent re-construction, surviving
proposition — is preserved in full in `RAFT_RA002_CONSTRUCTION_RESULT.md`
through `RAFT_RA005_CORRECTED_RESULT.md`, not edited away. The final,
surviving finding is stronger for having been tested against its own
best attempt to falsify it, not merely asserted once and left standing.

# RA-003 — Trace Completeness Boundary Inventory

**Status:** complete systematic inventory, grounded in direct reading of
every real trace call site (8 total, confirmed exhaustive by grepping
`trace[A-Z]` across the entire `raft.go`) and every real message-type
case in the `Step()`/`stepLeader`/`stepCandidate`/`stepFollower`
dispatch. No construction beyond what `RA-002` already performed. The
question, per instruction: **not** "manufacture another defect," but
**"which implementation behaviors that materially affect consensus
state are actually represented in the formal trace?"**

## Method

Two independent enumerations, cross-checked against each other:
(1) every message type handled anywhere in `raft.go` (18 distinct types,
confirmed by direct grep — `MsgApp`, `MsgAppResp`, `MsgBeat`,
`MsgCheckQuorum`, `MsgForgetLeader`, `MsgHeartbeat`, `MsgHeartbeatResp`,
`MsgHup`, `MsgProp`, `MsgReadIndex`, `MsgReadIndexResp`, `MsgSnap`,
`MsgSnapStatus`, `MsgStorageAppendResp`, `MsgStorageApplyResp`,
`MsgTimeoutNow`, `MsgTransferLeader`, `MsgUnreachable`, `MsgVote`, plus
`MsgPreVote`/`MsgPreVoteResp` confirmed separately since they appear in
multi-type case lines a simple grep pattern misses); (2) every real
trace call site (8 total: `traceInitState`, `traceSendMessage` ×2,
`traceCommit`, `traceReplicate`, `traceBecomeFollower`,
`traceBecomeCandidate`, `traceBecomeLeader`, `traceReceiveMessage`,
`traceChangeConfEvent`, `traceConfChangeEvent`).

## Message-level inventory

| Message type | Traced? | Mechanism |
|---|---|---|
| `MsgApp` | **Yes** | `traceSendMessage`/`traceReceiveMessage` → `AppendEntriesRequest` |
| `MsgAppResp` | **Yes** | → `AppendEntriesResponse` |
| `MsgHeartbeat` | **Yes** | → `AppendEntriesRequest` (folded together with `MsgApp`, not distinguished) |
| `MsgHeartbeatResp` | **Yes** | → `AppendEntriesResponse` (folded together with `MsgAppResp`) |
| `MsgSnap` | **Yes, but mislabeled** | → `AppendEntriesRequest`/`Response` — confirmed the dedicated `rsmSendSnapshot`/`rsmReceiveSnapshot` enum values exist but are **never actually used anywhere in the file** (dead constants) |
| `MsgVote` | **Yes** | → `RequestVoteRequest` |
| `MsgVoteResp` (via `myVoteRespType`) | **Yes** | → `RequestVoteResponse` |
| `MsgPreVote` | **No** | Falls into `default: return` in both send and receive tracers — already established in `RA-002` |
| `MsgPreVoteResp` | **No** | Same |
| `MsgHup` | **No** | Not a wire message in the traced sense (locally-injected trigger for `campaign()`), but the resulting `BecomeCandidate`/`BecomeLeader` transitions *are* traced — the trigger itself has no direct trace event |
| `MsgBeat` | **No** | Locally-injected heartbeat trigger; no trace event, though its downstream `MsgHeartbeat` sends are traced |
| `MsgCheckQuorum` | **No** | No trace call anywhere in its handling |
| `MsgTransferLeader` | **No** | No trace call — leadership transfer initiation is entirely untraced |
| `MsgTimeoutNow` | **No** | No trace call — the message that actually triggers a transferee's immediate campaign is untraced (though the resulting `BecomeCandidate` is) |
| `MsgReadIndex` | **No** | No trace call |
| `MsgReadIndexResp` | **No** | No trace call |
| `MsgForgetLeader` | **No** | No trace call (a no-op on leader, per source comment) |
| `MsgUnreachable` | **No** | No trace call |
| `MsgSnapStatus` | **No** | No trace call |
| `MsgStorageAppendResp` | **No** | No trace call |
| `MsgStorageApplyResp` | **No** | No trace call |

## State-transition-level inventory

| Transition | Traced? |
|---|---|
| `becomeFollower` | **Yes** — `traceBecomeFollower` |
| `becomeCandidate` | **Yes** — `traceBecomeCandidate` |
| `becomeLeader` | **Yes** — `traceBecomeLeader` |
| `becomePreCandidate` | **No** — confirmed directly, zero trace calls in the function body, unlike every other `become*` function |
| Commit index advancement | **Yes** — `traceCommit`, unconditional `defer` in `maybeCommit` |
| Entry replication | **Partial** — `traceReplicate` only fires for `EntryNormal`-type entries (confirmed from source, `RAFT_RA002_TLA_DECOMPOSITION.md`'s earlier open item); `EntryConfChange`-type entries are not covered by this call |
| Config change proposal | **Yes** — `traceChangeConfEvent`, inside `stepLeader`'s `MsgProp` handling |
| Config change application | **Yes** — `traceConfChangeEvent`, inside `applyConfChange` |
| Node initialization | **Yes** — `traceInitState` |

## What this inventory establishes

**PreVote is not an isolated omission — it is the anchor of a small,
coherent cluster of related exclusions, all centered on the same part of
the protocol:** the PreVote messages themselves (`RA-002`), the
`PreCandidate` state transition itself (found here), and — more broadly
but less centrally — several other locally-significant control messages
(`MsgCheckQuorum`, `MsgTransferLeader`, `MsgTimeoutNow`, `MsgReadIndex`)
that materially affect *when* elections happen or *whether* a read is
safe, without being represented in the trace at all.

**The `EntryConfChange`-vs-`traceReplicate` question, left open in
`RA-002`'s decomposition, is now resolved:** it is a real, partial gap
in `traceReplicate` specifically, but it is *compensated* by the
separate `traceChangeConfEvent`/`traceConfChangeEvent` pair, which cover
config-change proposal and application through a different path. This is
not a second independent exclusion of the same shape as PreVote — it is
a deliberate structural split (ordinary entries traced one way,
config-change entries traced another), not an omission.

**Stated at the precision this inventory earns, directly answering the
question posed:** the exclusions are not uniformly scattered across the
whole protocol. The core data-replication path (`MsgApp`/`MsgAppResp`,
commit, config changes) is comprehensively traced. The exclusions cluster
specifically around **liveness and leadership-stability mechanisms** —
PreVote, CheckQuorum, leadership transfer, and ReadIndex safety — none of
which are covered by any trace event. This is closer to "the validation
architecture has a sharply defined scope boundary" than to "the
validation architecture is generally incomplete" — but the boundary is
**wider than PreVote alone**: it appears to be, more precisely, *the
entire family of mechanisms Raft added beyond the base algorithm's core
replication path* (PreVote, CheckQuorum, transfer, ReadIndex are all
documented as extensions/refinements in the library's own `Config`
comments, not part of the original paper's five safety properties
directly).

## Explicitly not done

No construction against any of the newly-identified gaps
(`MsgCheckQuorum`, `MsgTransferLeader`, `MsgTimeoutNow`, `MsgReadIndex`,
`becomePreCandidate`) — this is an inventory, not an attack, per
instruction. No claim that any of these gaps individually produces a
`TraceMatched` failure the way PreVote was shown to in `RA-002` — that
would require the same real-execution-plus-TLC-run discipline already
applied once, not assumed to generalize. No safety-property implication
drawn from any entry in this inventory.

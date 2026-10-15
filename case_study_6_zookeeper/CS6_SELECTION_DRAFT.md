# Case Study 6: Apache ZooKeeper, watch delivery and Single System Image

Selection draft 1, 2026-10-14. Not a pre-registration. Nothing has been built
or run. Branch `cs6-zk`, created from `origin/main`. Local `main` stays held
for the raft-rs disclosure and is not touched by this branch.

CBV (`PHOENIX_VERIFICATION_PROTOCOL.md`) governs. This is an **in-class**
study.

## Status of every claim in this document

- **Source facts:** read from the `release-3.9.6` tag on 2026-10-14. File
  names are given; line numbers are to be recorded from a pinned local
  checkout before pre-registration.
- **H1:** a hypothesis derived from source. Not executed. Not a bug, not a
  contract violation, not a novel finding.
- **Prior art:** a few web searches plus four JIRA issues read. Not
  exhaustive. A full JIRA search is an open item.

## Selection

| Criterion | ZooKeeper |
| --- | --- |
| Deterministic, replayable state | Totally ordered zxid log, snapshots |
| Integrity artifacts | zxid ordering, transaction log checksums |
| Stated claims | Five numbered consistency guarantees in the Programmer's Guide |
| Real seams | Client/server zxid handoff, failover, the notification path |
| Different philosophy | Zab primary-backup (vs Raft, FDB simulation, Go build transformation, Phoenix replay) |

Pin: ZooKeeper **3.9.6**, the current release on 2026-10-14 (3.8.7 is the
stable line). Java client and server from the same release.

## Claims under test (Programmer's Guide, 3.9.x)

- **SSI (Single System Image).** A client sees the same view of the service
  regardless of server; it never sees an older view, even after failing over
  to a different server with the same session.
- **W (watch ordering).** A client sees the watch event for a znode before it
  sees the new data that corresponds to that event.

Explicitly **not** under test: simultaneously consistent cross-client views,
which the guide itself disclaims (`sync()` is the documented remedy).

## Two readings, fixed before any run

W can be read two ways, and SSI's word "view" can be read two ways. The study
records which reading a result bears on and does not choose after the fact.

- **R-A, event ordering only.** W forbids observing new data before the event.
  SSI covers data responses. A notification is a signal, not part of the
  "view". Under R-A, a stale read after a notification is not a violation.
- **R-B, read freshness.** Once the client has received an event carrying
  zxid Z, its view includes Z, and SSI forbids a later read returning state
  older than Z without an intervening session loss.

## Mechanism, from source at `release-3.9.6`

1. **Client, `ClientCnxn.java`.** In `readResponse`, the `NOTIFICATION_XID`
   branch builds `new WatchedEvent(event, replyHdr.getZxid())`, queues it, and
   returns. `lastZxid` is assigned only in the ordinary-reply path, under
   `if (replyHdr.getZxid() > 0)`. `primeConnection` sends that `lastZxid` in
   the `ConnectRequest`.
2. **Event zxid.** Watch events have carried the triggering zxid since 3.9.0
   (ZOOKEEPER-4655, superseding ZOOKEEPER-3566).
3. **Server connect, `ZooKeeperServer.processConnectRequest`.** The only zxid
   gate refuses when `request.getLastZxidSeen() > zkDb.dataTree.lastProcessedZxid`
   (`CLIENT_ZXID_AHEAD`). No catch-up or sync step follows; the session is
   revalidated directly.
4. **Follower routing, `quorum/FollowerRequestProcessor.java`.** `sync` and
   write opcodes are forwarded to the leader. `getData`, `exists` and
   `getChildren` are not forwarded; they go only to the local next processor.
5. **Commit ordering, `quorum/CommitProcessor.java`.** `needCommit()` returns
   false for `getData` (default branch). A read is held only if
   `pendingRequests.containsKey(request.sessionId)`, i.e. only behind earlier
   requests of the same session; otherwise it goes straight to the next
   processor. No client last-seen zxid is consulted.
6. **Read serving, `FinalRequestProcessor.java`.** `getData` reads
   `zks.getZKDatabase().getData(...)` from the local tree with an ACL check
   and no zxid check. Every reply header carries
   `zks.getZKDatabase().getDataTreeLastProcessedZxid()`.

Consequence if 1-6 hold: a notification at Z leaves `lastZxid` below Z; a
server at or above the old `lastZxid` but below Z accepts the reconnect and,
because the H1 client issues no writes, serves `getData` from its local tree
without waiting.

## H1 (hypothesis, primary)

Scope: Java client, one-shot data watch (`getData` with watch) on a single
znode `/x`, three-server ensemble, session preserved across reconnect.
Persistent and persistent-recursive watches are **excluded** (see
ZOOKEEPER-4698).

1. Client C connects to server S1, reads `/x` with a data watch. Record
   `lastZxid = A`.
2. A separate writer client sets `/x`, committed at zxid Z > A. C receives
   `NodeDataChanged` with `event.getZxid() == Z` from S1.
3. C's connection to S1 is broken before C receives any ordinary reply.
4. C reconnects, same session, to S2, where S2 has applied A but not Z.
5. C calls `getData("/x")` on S2.

Prediction (source-derived): S2 accepts the reconnect, the read returns the
pre-Z value, the reply header zxid is below Z, and C's `lastZxid` after the
read is below the Z it already holds in the event.

H1 is a test of whether a watch notification advances the client's effective
consistency boundary across session-preserving failover. It is not framed as
an established inconsistency.

## Controls

- **T0, ordinary-reply control.** Identical sequence, but in step 2 C learns
  of Z through an ordinary reply (C reads `/x` again on S1 after the write,
  so `lastZxid >= Z`). Prediction: S2 refuses the reconnect with
  `CLIENT_ZXID_AHEAD`, and C cannot obtain a pre-Z read from S2.
- **T1, watch-path treatment.** H1 as written.

**Isolation requirement:** the result is informative only if T0 and T1
differ. If T0 also yields a stale read, the harness has not isolated the
watch path and the run is reported as harness failure, not as support for H1.
If T1 does not yield a stale read, H1 is refuted for this configuration.

## States the harness must observe, not infer

Each run records, with timestamps:

- the event delivered to C: type, path, `getZxid()`;
- C's `lastZxid` at disconnect, at reconnect, and after the read;
- that no ordinary reply reached C between the event and the disconnect;
- S2's `lastProcessedZxid` at C's reconnect and at the read (four-letter
  word or AdminServer), showing S2 serving and behind Z;
- that the session id is unchanged and was never expired;
- the read's returned data, `Stat.mzxid`, and reply header zxid;
- S1/S2/leader roles at each step.

If these cannot be held at the same time, the run is reported as a
feasibility failure. The test is not weakened until it passes.

## Prior art, read so far

| Item | Relation to H1 |
| --- | --- |
| ZOOKEEPER-1412 (fixed 3.3/3.4) | Same variable, different path: `lastZxid` stayed 0 because followers returned 0 or the client's own zxid, so watches fired wrongly on reconnect. Its fix is why reply headers now carry the server's `lastProcessedZxid`. |
| ZOOKEEPER-3566 / ZOOKEEPER-4655 (3.9.0) | Added the triggering zxid to watch events, for ordering downstream. Does not discuss SSI or `lastZxid`. |
| ZOOKEEPER-4698 (open) | Lost persistent and persistent-recursive watch events across reconnect. Different property (event loss, not stale read); excluded by scope. |
| Jepsen ZooKeeper (2013; 2019 note) | Linearizability; sync+read not linearizable. Not SSI under failover with watches. |

Novelty is **not** claimed from "notifications don't update `lastZxid`",
which is visible in source to anyone. Any novelty claim must rest on the
specific sequence and its observed consistency outcome, and only after the
full JIRA search.

## Feasibility

- Three ZooKeeper 3.9.6 servers on the operator's machine, distinct ports.
- A TCP proxy between the leader and S2's quorum port holds S2 behind on
  demand. The harness waits on S2's observed `lastProcessedZxid`, not on a
  timer; `syncLimit x tickTime` bounds how long S2 keeps serving and is
  recorded, not relied on.
- A second proxy on C's client connection to S1 lets the harness cut that
  connection immediately after the event is delivered.
- Runs on the operator's machine (the sandbox cannot reach Maven Central).
  JDK already installed for CS4.

## Expected outcomes, all reportable

1. T1 stale, T0 refused: mechanism isolated. Reported as "reproduced, bears on
   R-B, holds under R-A"; the contract question goes to maintainers.
2. T1 not stale: H1 refuted for this configuration; the mechanism in source
   is protected by something not identified here.
3. T0 also stale: harness does not isolate the watch path.
4. Required states not simultaneously reachable: feasibility failure.

Outcome 1 with maintainers holding R-A is still a usable result: it documents
a concrete boundary between an exposed event-ordering guarantee and the
consistency boundary the client tracks.

## Reporting route (if outcome 1)

Public JIRA, framed as a contract question with both readings, not a
vulnerability report. To be confirmed against ZooKeeper's security page
before sending.

## Open items before pre-registration

1. Record line numbers for every source fact from a pinned local checkout.
2. Full JIRA search: `lastZxid`, `SetWatches relativeZxid`, "single system
   image", watch + reconnect + stale.
3. Confirm the reply-header zxid behaviour on a follower read empirically in
   T0 (it is the trace witness for H1).
4. Decide reporting route.

## Next stage, if approved

Write `CS6_PLAN.md` (pre-registration): pins and hashes, harness design, the
observation list above as pass/fail gates, run counts, scoring rules for each
outcome. Commit and push the plan on `cs6-zk` before any harness code exists.

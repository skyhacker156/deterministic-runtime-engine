# Case Study 6: Apache ZooKeeper — pre-registration (CS6_PLAN.md)

Binding plan, 2026-10-14. Supersedes `CS6_SELECTION_DRAFT.md` (committed
`2d9ad7f` on `cs6-zk`). Committed and pushed on `cs6-zk` (from `origin/main`)
before any harness code exists. Any later change is a dated amendment written
before the run it affects. Local `main` stays held for the raft-rs disclosure
and is not touched.

CBV (`PHOENIX_VERIFICATION_PROTOCOL.md`) governs. In-class study.

## Pins

- ZooKeeper **3.9.6**, tag `release-3.9.6`, commit
  `a355171b081b5b60749db8f19cca1528b0df936f` ("Prepared 3.9.6").
- Server, Java client, and AdminServer all from this tag.
- Client-side observation uses `TestableZooKeeper.testableLastZxid()`
  (-> `ClientCnxn.getLastZxid()`), present at this tag.
- To be recorded in `HASHES_BEFORE_RUN.txt`: sha256 of the release source
  tarball, of the built client/server jars, and of every harness file, before
  the scored run.

## Claims under test (Programmer's Guide, 3.9.x)

- **SSI.** "A client will see the same view of the service regardless of the
  server that it connects to. i.e., a client will never see an older view of
  the system even if the client fails over to a different server with the same
  session." (Clause added by ZOOKEEPER-3373; scoped to post-connection
  failover by its own reporter.)
- **W.** "A client will see a watch event for a znode it is watching before
  seeing the new data that corresponds to that znode."

Out of scope: simultaneously consistent cross-client views (the guide
disclaims these; `sync()` is the documented remedy).

## Two readings, fixed before any run

- **R-A (event ordering only).** W forbids seeing new data before the event.
  SSI governs data responses; a notification is a signal, not part of the
  "view". A stale read after a notification is not a violation.
- **R-B (read freshness).** Once the client holds an event carrying zxid Z,
  its view includes Z; SSI forbids a later read returning state older than Z
  absent an intervening session loss.

The study records which reading a result bears on. It does not pick after the
fact. R-A is the maintainers' likely reading (see ZOOKEEPER-4655 rationale
below); the study does not assume otherwise.

## Mechanism, source at `release-3.9.6` (file : line)

1. `ClientCnxn.java` : `lastZxid` field `L799`; `NOTIFICATION_XID` case
   `L902`; `WatchedEvent we = new WatchedEvent(event, replyHdr.getZxid())`
   `L915`, `eventThread.queueEvent(we)` `L917`, then `return` — the
   notification path does not reach the update; ordinary-reply update
   `if (replyHdr.getZxid() > 0) { lastZxid = replyHdr.getZxid(); }`
   `L956-957`; reconnect carries it,
   `new ConnectRequest(0, lastZxid, ...)` `L1012`.
2. Server stamps the event zxid on the wire:
   `NIOServerCnxn.java:722` and `NettyServerCnxn.java:180`,
   `new ReplyHeader(ClientCnxn.NOTIFICATION_XID, event.getZxid(), 0)`;
   zxid threaded from `DataTree.setData` (`L627`) through
   `triggerWatch(path, EventType.NodeDataChanged, zxid, acl)` (`L658`);
   `WatchedEvent(WatcherEvent, zxid)` `L61`, `getZxid()` `L91`.
3. `ZooKeeperServer.java` : `processConnectRequest` `L1467`; the only zxid
   gate, `if (request.getLastZxidSeen() > zkDb.dataTree.lastProcessedZxid)`
   `L1504`, throws `CLIENT_ZXID_AHEAD` `L1516`; otherwise
   `reopenSession(...)` `L1555`. No catch-up/sync before serving.
4. `quorum/FollowerRequestProcessor.java` : `sync` forwarded `L97-99`; write
   opcodes forwarded `L101-112`; `getData`/`exists`/`getChildren` absent from
   the switch, so only `maybeSendRequestToNextProcessor(request)` `L85` runs —
   reads are served locally, never forwarded.
5. `quorum/CommitProcessor.java` : `needCommit` `L169`, `getData` falls to
   `default` `L191` (not a commit); hold condition
   `if (needCommit(request) || pendingRequests.containsKey(request.sessionId))`
   `L251`, else `sendToNextProcessor(request)` `L259`. A read is held only
   behind the same session's earlier requests; the H1 client issues none.
6. `FinalRequestProcessor.java` :
   `long lastZxid = zks.getZKDatabase().getDataTreeLastProcessedZxid()`
   `L165`; `getData` case `L383` ->
   `zks.getZKDatabase().getData(path, ...)` `L651`, local tree, ACL check
   only, no zxid check; reply header
   `new ReplyHeader(request.cxid, lastZxid, err)` `L588` carries that
   follower's own `lastProcessedZxid`.

Consequence if 1-6 hold: a notification at Z leaves client `lastZxid` below Z;
a follower at or above the old `lastZxid` but below Z accepts the reconnect
(`L1504` false) and serves `getData` locally without waiting; the read reply
carries a zxid below Z.

## H1 (hypothesis, primary) — intended-behavior composition, not a code defect

Scope: Java client, one-shot data watch (`getData` with watch) on a single
znode `/x`, three-server ensemble, session preserved across reconnect.
Persistent and persistent-recursive watches excluded (ZOOKEEPER-4698).

1. C connects to S1, `getData("/x", watch=true)`. Record `lastZxid = A`.
2. Writer sets `/x`, committed at Z > A. C receives `NodeDataChanged` with
   `event.getZxid() == Z` from S1.
3. C's connection to S1 breaks before any ordinary reply reaches C.
4. C reconnects, same session, to follower S2, which has applied A but not Z.
5. C calls `getData("/x")` on S2.

Prediction (source-derived): S2 accepts the reconnect; the read returns the
pre-Z value; the reply header zxid is below Z; C's `testableLastZxid()` after
the read is below the Z it already holds in the event.

## Controls

- **T0 (ordinary-reply control).** In step 2, C learns of Z via an ordinary
  reply (re-reads `/x` on S1 after the write, so `lastZxid >= Z`). Prediction:
  S2 refuses the reconnect with `CLIENT_ZXID_AHEAD`; no pre-Z read obtainable.
- **T1 (watch-path treatment).** H1 as written.

**Isolation gate.** The result is informative only if T0 and T1 differ.
Both stale -> harness failure (watch path not isolated). T1 not stale ->
H1 refuted for this configuration.

## Observations as pass/fail gates (recorded per run, with timestamps)

A run is scored only if all of these are captured; otherwise it is a
feasibility failure and the test is NOT weakened to pass:

- G1 event delivered to C: type, path, `getZxid() == Z`.
- G2 C's `testableLastZxid()` at: post-step-1 (= A), at disconnect, at
  reconnect, after the step-5 read.
- G3 no ordinary reply reached C between the event and the disconnect
  (client-side packet log).
- G4 S2 serving with applied state behind Z at reconnect AND at the read
  (AdminServer `/commands/zabstate` + `lastProcessedZxid`, or 4lw `srvr`).
- G5 session id unchanged, never `Expired` (watcher state log).
- G6 read result: data bytes, `Stat.mzxid`, reply-header zxid.
- G7 roles (leader / S1 / S2) at each step, AND confirmation that C's
  step-4 reconnect landed on the intended behind-follower S2 (not S1, not a
  caught-up server) — recorded from C's remote socket address and matched to
  S2's identity.

## Scoring

| Outcome | Condition | Report |
| --- | --- | --- |
| 1 | T1 stale, T0 refused, G1-G7 all captured | reproduced; bears on R-B; holds under R-A; contract question to maintainers (private, see route) |
| 2 | T1 not stale | H1 refuted for this configuration |
| 3 | T0 also stale | harness does not isolate the watch path |
| 4 | any gate G1-G7 not simultaneously held | feasibility failure |

Runs: T0 and T1 each executed N=20 times; replay-confirm the decisive runs in
fresh processes. Report the full count (e.g. "T1 stale k/20"), not a single
illustrative run.

## Prior art (JIRA + commit history, read 2026-10-14)

- **ZOOKEEPER-1417** (fix 3.4.0/3.5.0, commit `1b66c34e`). Aligned C client
  with Java: update last zxid only on request responses, not pings. Its test
  `testLastZxid` asserts that after a watch event fires, the client's last
  zxid "should remain the same." **The client not advancing `lastZxid` on a
  notification is therefore intended and regression-tested since 2013.** H1 is
  the composition of this intended client behavior with the intended server
  connect gate, not a latent defect.
- **ZOOKEEPER-4655 / -3566** (shipped 3.9.0, commit `880f6064`). Added the
  triggering zxid to watch events, explicitly "to deduplicate ... local
  caches" during bootstrap/catch-up. Not a freshness signal. Supports R-A as
  the maintainers' likely reading.
- **ZOOKEEPER-3373** (2019, commit `f252c769`). Added the SSI failover clause
  H1 tests against; scoped by its reporter to post-connection failover.
- **ZOOKEEPER-1412** (fixed 3.3/3.4). Watches wrongly fired on reconnect
  because `lastZxid` stayed 0; different mechanism.
- **ZOOKEEPER-4698** (open). Persistent/recursive watch event loss on
  reconnect; different property; excluded by scope.
- Jepsen ZooKeeper (2013; 2019 note): linearizability; sync+read not
  linearizable. Not SSI-under-failover-with-watches.

**Novelty position.** No novelty is claimed for the `lastZxid`/notification
behavior — it is intended and tested. Any novelty rests solely on the specific
failover sequence and its observed consistency outcome, and is asserted only
after this plan's run, never from source reading alone.

## Feasibility / harness

- Three 3.9.6 servers, distinct ports, on the operator's machine (sandbox
  cannot reach Maven Central; JDK already present from CS4). A Gradle wrapper
  or the release binary distribution builds/runs it; no Maven/Gradle install.
- Proxy A on S2's quorum link holds S2 behind on demand; the harness waits on
  S2's observed `lastProcessedZxid` (G4), never on a timer. `syncLimit x
  tickTime` bounds how long S2 keeps serving while behind and is recorded, not
  relied on.
- Proxy B on C's client link to S1 cuts the connection immediately after the
  event is delivered (step 3), before any ordinary reply.
- **Reconnect target forced to S2.** `StaticHostProvider` shuffles the connect
  string and picks an arbitrary server, so the harness must leave S2 as the
  only reachable server at reconnect or C may land back on S1 or on a
  caught-up server — a read served fresh there scores as a spurious refutation
  (outcome 2) unrelated to H1. C's connect string contains only S1 and S2
  (never S3); at step 3 Proxy B both cuts and blackholes S1, leaving S2 as the
  sole option. (Alternatively, narrow C's list to S2 via `updateServerList`
  before the cut.) G7 confirms the landing.
- Client built with `TestableZooKeeper` for G2.

## Reporting route

Settled against the ZooKeeper security page: in scope is "behaviors that
contradict documented guarantees in the current ZooKeeper documentation,"
reported to **security@zookeeper.apache.org** "before disclosing it publicly."
- Outcome 1 under R-B: send privately to that address first, framed as a
  contract question presenting both readings and the full trace; let the
  project decide public JIRA vs advisory. Do not open public JIRA first.
- Outcome 1 but maintainers hold R-A: still a usable result — a documented,
  reproducible boundary between the exposed event-ordering guarantee and the
  client's tracked consistency boundary.
- Outcomes 2-4: no report; record in the result note.
Hold any public write-up until the project responds, same discipline as the
raft-rs disclosure.

## Open items before the scored run

1. `HASHES_BEFORE_RUN.txt`: source tarball, built jars, every harness file.
2. `PREFLIGHT_AUDIT.md`: map each plan requirement (G1-G7, isolation gate) to
   the harness code before the scored run.
3. Confirm G4/G6 instrumentation (AdminServer vs 4lw) actually exposes a
   follower's applied zxid at the needed moment.

## Next stage, if approved

Build the harness and controls; write `PREFLIGHT_AUDIT.md` and
`HASHES_BEFORE_RUN.txt`; run T0/T1 at N=20; write `CS6_RESULT.md`. All on
`cs6-zk`.

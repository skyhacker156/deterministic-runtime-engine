# CS6 result: ZooKeeper watch delivery vs Single System Image

2026-10-16. Branch `cs6-zk`. Governs: CBV (`PHOENIX_VERIFICATION_PROTOCOL.md`).
Pre-registration: `CS6_PLAN.md`; amendments `CS6_AMENDMENT_1.md`. Instrumentation
finding: `CS6_G4_INSTRUMENTATION.md`. Harness: `harness/`.

## Headline

CS6 reproduced a concrete **notification-to-session-state gap** but found **no
safety violation**. Under the tested partition-and-failover conditions, the
client's reconnect to the lagging follower was blocked at **two distinct
stages** — the zxid reconnect gate, and global-session establishment — the
latter because a global session cannot be established on a follower that is
partitioned from the leader. Single System Image held in every trial.

This is CBV outcome 2 (H1 refuted for this configuration), upgraded: the
protecting mechanism is identified, not merely observed. The bounded
construction revealed that the same partition needed to make a follower lag is
what blocks the failover onto it.

## Scope (the result is scoped to exactly this)

- Version: ZooKeeper **3.9.6**, tag `release-3.9.6`, commit `a355171b`.
- Topology: 3-node ensemble on one host. Leader = node 3; S1 = node 1 (client
  watches here, reached via Proxy B on 12181->2181); S2 = node 2 (the follower
  held behind, reached directly on 2182).
- Config: **global sessions** (localSessionsEnabled=false, confirmed in logs),
  tickTime 2000, initLimit 10, syncLimit 5, negotiated session timeout 30000 ms.
- Fault injection: Proxy A HOLD (blackhole node 2's learner channel to the
  leader, `server.3`->12883) to make node 2 lag; Proxy B CUT to force the
  client's failover off node 1.
- Schedule: the fixed 5-step H1 sequence and the T0 control, N=10 per arm
  (`CS6_results_20261016-201704.jsonl`) plus the pre-registered N=20 per arm,
  both fully deterministic (10/10 and 10/10; 20/20 and 20/20).

Nothing here is a universal claim about ZooKeeper. It is a result for this
version, configuration, fault model, and schedule.

## Evidence tier 1 — OBSERVED (directly measured)

- **The gap is real and reproducible.** In every T1 trial the watch fired
  (`eventType=NodeDataChanged`, `eventZxid=Z`) while the client's session-level
  `lastZxid` stayed at A: `notifyHeldA=true`, 10/10 (and the probe trial). The
  application was told Z; the session tracker still held A.
- **T0 control (ordinary-reply path).** The client's `lastZxid` advanced to Z
  (`lastBeforeFailover=Z`); the failover to node 2 was refused; no stale read.
  Outcome `T0_REFUSED_as_predicted`, 10/10.
- **T1 treatment (watch path).** The failover session to node 2 never
  established; the failover read never completed (ConnectionLoss on all 20
  retry attempts, ~32 s); no stale read. Outcome `T1_FAILOVER_BLOCKED`, 10/10.
- **Session stable throughout** (`sessionStable=true`, no Expired) in all trials.
- **Live node-2 state during a T1 block** (probe, trial 99):
  - node 2 held at A (`0x300000083`) and did NOT advance to Z (`0x300000084`)
    for the whole ~10 s window — node 2 was genuinely behind Z.
  - node 2 stayed `zab=broadcast` (following) from the partition through
    `20:32:09.999`, then left the quorum (zabstate blank) at `20:32:10.45`
    (~syncLimit = 5 x tickTime = 10 s after losing leader contact), and
    recovered to `broadcast` at `0x300000085` after the heal.
  - Client-side (earlier T1 trace): C connected TCP to node 2, sent the session
    request, node 2 held it ~9.2 s and closed it without completing it; repeated
    every retry.

## Evidence tier 2 — MECHANISM (established behaviorally + from source)

Two distinct rejection stages, confirmed by the two controls plus source:

1. **zxid reconnect gate (T0).** `ZooKeeperServer.processConnectRequest`
   (`L1504`) refuses when `request.getLastZxidSeen() > lastProcessedZxid`
   (`CLIENT_ZXID_AHEAD`, `L1516`). In T0 the client's `lastZxid=Z` exceeded node
   2's `A`, so node 2 rejected before session establishment. This is the
   protection the study originally set out to probe; it works.

2. **Global-session establishment under partition (T1).** In T1 the client's
   `lastZxid=A` is <= node 2's `A`, so it passes the zxid gate. But node 2 must
   then establish the reconnecting **global** session, which for a follower is
   validated through the leader (`processConnectRequest` -> `reopenSession` ->
   `revalidateSession`; a follower forwards session validation to the leader).
   Node 2's learner channel to the leader is held (Proxy A), so establishment
   cannot complete. The probe establishes the decisive point: node 2 was a
   **live, following follower, behind Z, for ~10 s**, and could not accept the
   failover session during that entire window; it tore down the pending
   connection only when it left the quorum at syncLimit.

**Decisive distinction (new, from the probe):** the block is **not server
liveness** and **not** "node 2 immediately dropped out." Node 2 was behind Z
and still following for ~10 s. The block is **session mobility**: a global
session cannot be established on a follower partitioned from the leader, even
while that follower is otherwise serving-capable. The lag condition H1 needed
*was* achieved; the failover still could not land on it.

Honest limit on tier 2: the specific server-side revalidation code path is
taken from source plus behavior, not from a node-2 server log line. No
alternative explanation fits a following, zxid-valid follower refusing the
reconnect, but a node-2 log capture would convert this from "established by
source+behavior" to "established by direct server trace."

## Evidence tier 3 — INFERENCE / UNTESTED BOUNDARY

**The slow-but-connected follower is not tested, and is left open.** A follower
merely lagging by a commit while still in contact with the leader could, in
principle, present the window without the session-mobility block. Mechanism
argument (moderate confidence, explicitly not a result): commit delivery and
session validation ride the same ordered ZAB learner stream in the same
direction, so a delay that holds Z back also holds validation, and a connected
follower's lag window is vanishingly small. Testing this would require a
ZAB-message-aware proxy that holds only the COMMIT(Z) while passing validation
and heartbeats — a substantially larger build. Recorded as an open boundary,
not closed.

## Conclusion

For the tested version, configuration, fault model, and schedule: the
hypothesized stale read did not occur. The notification-to-session-state gap is
real and reproducible, but it is not exploitable via same-session failover,
because the session cannot be established on the lagging follower. **Single
System Image held in every trial.** The result supports the R-A reading (SSI
governs the session's read view; a watch notification is a signal, not a read)
and names **two independent barriers**: the `lastZxid` reconnect gate and the
requirement that a global session be established through the leader.

**No safety violation; no report to the ZooKeeper security list is warranted.**

## Contribution (what CBV surfaced here)

The study set out to probe one barrier (the `lastZxid` gate) and discovered a
second (global-session mobility) that the pre-registration did not anticipate,
by driving the bounded construction until it hit the real limit. The honest
negative — "the gap exists but is doubly protected, and the lag-inducing
partition is exactly what blocks the failover" — is a sharper, more defensible
result than confirming a bug would have been, and it is the kind of calibrated
outcome the method is built to produce. It also keeps one boundary explicitly
open rather than overclaiming closure.

## Artifacts

`harness/tcp_proxy.py`, `harness/CS6Trial.java`, `harness/cs6_run.ps1`,
`harness/cs6_probe.ps1`, the per-trial JSONL result files, and this document.
`zoo2.cfg` `server.3` remains pointed through Proxy A and should be reverted to
the direct address (`127.0.0.1:2883:3883`) now that CS6 is complete.

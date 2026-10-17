# CS6-SF1 — Result (slow-but-connected follower)

**Case:** CS6-SF1 — labeled extension of CS6 (ZooKeeper SSI under same-session failover). CS6's frozen result is unchanged.
**Pinned target:** Apache ZooKeeper 3.9.6, commit `a355171b`. Global sessions, `syncLimit=5`, tickTime 2000 ms. 3-node ensemble, leader = node 3.
**Pre-registration:** `CS6_SF1_PLAN.md`, frozen before harness, SHA-256 prefix `2580427C`.
**Date:** 2026-10-17
**Harness:** `CS6SF1Trial.java` (commit `2ddec75`, instrumented for the zxid-gate vs revalidation discriminator), `tcp_proxy.py` DELAY mode, `cs6_sf1_run.ps1`.

---

## Headline

Under the tested 3.9.6 configuration, the DELAY experiment **reliably reached a connected, lagging-follower state** (node2 following, in quorum, applied zxid behind Z at the failover instant) but **did not demonstrate a stale read**. Every served failover read returned Z. The observed barrier is the **zxid reconnect gate**, driven by the client's session advancing to Z within milliseconds of the watch notification. A secondary session-revalidation latency is observed but is confounded by the ever-present gate and is **not** established as an independent barrier.

This does **not** prove SSI holds. It establishes that this fault model (DELAY on the learner channel, global sessions, session-preserving reconnect) cannot exercise the stale-read path.

---

## Controls and trial counts

- **T0 (no-delay control), N=3:** 3/3 `T0_FRESH_as_predicted`; failover landed on node2 serving current Z. Confirms the rig does not manufacture staleness and the forced-reconnect path works.
- **SF1 (delay), 16 trials total:** pilot N=3 @ 4000 ms, N=3 @ 7000 ms, instrumented N=10 @ 5000 ms.

---

## Evidence (tiered)

### Observed (direct per-trial measurement)
- **Connected-lagging state reached: `reachedBehindZ` 16/16.** At reconnect, node2 was `broadcast` + following + in quorum (`gFollowing`, `gQuorum` all true), with applied zxid = A (< Z).
- **No stale read: `servedBehindZ` 0/16.** `servedByNode2` true; every served read returned Z's value, `valuePreZ=false`, `zxidBelowZ=false`.
- **Client demands Z on reconnect: `clientDemandedZ` 10/10** in the instrumented run (`lastAtReconnect = Z`); `lastBeforeFailover = Z` 16/16. Even the 4/10 trials with `notifyHeldA=true` (session momentarily at A at the notify instant) had advanced to Z by failover — the held-at-A state is not durable.
- **Timing:** reconnect→read ≈ 2× delay (≈10 s @5 s, ≈10 s @4 s, ≈15 s @7 s). node2's data catch-up ≈ 1× delay (~5 s @5 s). In 6/10 instrumented trials `serveAfterCatchupMs ≈ 5000` — node2 held Z for ~5 s while the read remained blocked.
- First failover-read error was `ConnectionLossException` in all instrumented trials (transient failover, not a hard refusal); the read eventually succeeded (not `refused`).

### Mechanism-established (source + behavior)
- **Primary barrier — zxid reconnect gate.** Verified against the pinned revision (ZooKeeper 3.9.6, tag `release-3.9.6` = commit `a355171b`, confirmed `git rev-parse HEAD`). The client's session zxid advances to Z within ~ms of the watch notification, so the session-preserving reconnect carries `lastSeenZxid = Z`. In the session connect-request path, `zookeeper-server/.../server/ZooKeeperServer.java:1504`:
  ```java
  if (request.getLastZxidSeen() > zkDb.dataTree.lastProcessedZxid) {
      String msg = "Refusing session(...) ... it has seen zxid 0x<Z> our last zxid is 0x<...> client must try another server";
      LOG.info(msg);
      throw new CloseRequestException(msg, ServerCnxn.DisconnectReason.CLIENT_ZXID_AHEAD);   // :1516
  }
  ```
  While node2's `lastProcessedZxid < Z`, node2 **refuses** the ahead-zxid session connect (`CLIENT_ZXID_AHEAD`). The client observes this as a closed connection — which is exactly the `firstReadError = ConnectionLossException` recorded in 10/10 instrumented trials — and retries. With the server list constrained to node2, it retries node2 until node2's `lastProcessedZxid` reaches Z, after which the connect is accepted and the read returns Z. The observed ConnectionLoss signature is the client-side manifestation of line 1516. This is the same gate CS6 identified (`ZooKeeperServer.java:1504/1516`), now shown to foreclose the connected-lagging-follower path — not only the hard-partition path.

### Inference / not established
- **Secondary revalidation latency.** The ~5 s of blocking after node2's data catch-up (`serveAfterCatchupMs ≈ 5000`, 6/10) is consistent with global-session revalidation routing through node2's delayed learner channel — the same mobility-cost family as CS6's second barrier. But because `clientDemandedZ=true` in every trial, the zxid gate alone already forces freshness, so this revalidation cost **cannot be isolated as an independent sufficient barrier**. The decomposition of the ~2× window into catch-up vs revalidation is not cleanly separated (the once-per-attempt node2 poll undersamples the catch-up crossing in 4/10 trials).

---

## Relationship to CS6

CS6 blocked the same-session failover stale read with a hard partition (HOLD) at two barriers — the zxid gate and global-session mobility — and explicitly left the **slow-but-connected follower** open as a path that might reach further. CS6-SF1 shows it does **not**, under a DELAY fault: the connected-lagging state is reachable, but the client's near-immediate advance to Z makes the zxid gate fire on reconnect exactly as in CS6, and the revalidation cost (CS6's second barrier) is still present. The slow-follower case is foreclosed by the same barrier family, not a new one.

---

## What this establishes / does not

- **Establishes (in scope):** under 3.9.6 as tested, DELAY on node2's learner channel reaches a connected lagging follower but produces no stale read; the operative barrier is the zxid reconnect gate; a revalidation cost is observed but confounded.
- **Does not establish:** that SSI holds in general; that no stale read is possible under any fault model, configuration, session mode (local sessions untested), delay, or schedule; nor an independent role for the revalidation barrier. No generalization beyond the tested DELAY fault model.
- A reproduced stale read, a cleanly isolated independent barrier, and a different session mode all remain untested paths.

---

## Scorecard (this case)

- **Invariant precision:** high — stale read defined as served pre-Z value with server/client zxid < Z, under R-B.
- **State reachability:** connected-lagging-follower reached 16/16; served-behind-Z reached 0/16 (foreclosed).
- **Discrimination:** distinguished reached-but-fresh from a stale read, and separated the zxid gate (established) from the revalidation cost (confounded) via the `lastAtReconnect` / `serveAfterCatchup` witnesses.
- **Reproducibility:** 16 trials, pinned version/config, harness + JSONL committed.
- **Independent agreement:** not yet obtained (standing corpus-wide gap).
- **Cost to evidence:** ~1 bounded session incl. ensemble bring-up; within the pre-registered time cap.

No security report: negative/characterization result, no vendor-reportable defect.

---

*CS6-SF1 is a bounded reachability + mechanism result. Its value is that it closes CS6's open slow-follower boundary with evidence, and correctly scopes a secondary mechanism it could not isolate — not that it found a defect.*

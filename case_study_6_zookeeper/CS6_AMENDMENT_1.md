# CS6 amendment 1 — partition mechanism and timing pilot (2026-10-15)

Dated amendment to `CS6_PLAN.md`, written before the scored run, recording
implementation decisions fixed by an unscored timing pilot. Does not change H1,
the controls, the gates, or the scoring — it fixes how the partition is produced
and confirms the operating window.

## Decisions fixed

1. **Partition = blackhole (HOLD), not close.** Proxy A holds node 2's learner
   TCP connection to the leader OPEN but stops passing bytes, so node 2 does not
   detect a close and serves locally until its own learner read timeout. A
   closing partition (CUT) would risk collapsing the window by making node 2 go
   LOOKING immediately. Proxy B (client -> S1), still to be built, uses CUT so
   the client fails over fast.
2. **Proxy A placement.** Node 2's config `server.3` points its quorum/learner
   port at Proxy A: `server.3=127.0.0.1:12883:3883` in `zoo2.cfg` only;
   `zoo1.cfg` and `zoo3.cfg` unchanged. Proxy A: listen 12883 -> 127.0.0.1:2883,
   control 13001. Confirmed in the node 2 log: `LeaderConnector-/127.0.0.1:12883
   ... Successfully connected to leader`, then DIFF sync to `broadcast`.
3. **syncLimit kept at 5 (tickTime 2000).** The measured window is sufficient;
   not widened. (Review recommendation, confirmed empirically.)

## Timing pilot result (unscored)

Ensemble: leader = node 3, followers = node 1 (S1) and node 2 (S2). All at
`0x100000003` at baseline.

- `hold` on Proxy A at t0. Leader write `set /x held1` committed with majority
  (leader + node 1), leader advanced to `0x100000005`.
- Node 2 stayed at `0x100000003` and in `broadcast` for **~9.5 s**, then left
  `broadcast` (admin zabstate stopped returning the fields). Matches
  `syncLimit * tickTime = 10 s`.
- `pass` on Proxy A -> node 2 reconverged to `0x100000005`.

Readings: lag confirmed (node 2 flat while leader advanced); window
**W ≈ 9.5 s**; recovery confirmed (temporary, intervention-caused).

## Implications for the scored harness

- The scored sequence (write Z while node 2 is held -> S1 fires the watch to C
  -> cut C's link to S1 -> C reconnects to node 2 -> C reads) must complete
  well inside W. Target completion < ~7 s after `hold`, leaving margin.
- Window-end signal for instrumentation is node 2 leaving `broadcast`. This is a
  serving-capability bound, not proof of a served read; the scored run proves
  actual read-serving via the read's own reply-header zxid (G6), per the plan.
- Order is fixed: `hold` node 2 BEFORE writing Z, so node 2 never receives Z.

## Artifact

`harness/tcp_proxy.py` (PASS/HOLD/CUT, control port, timestamped logging).
Self-tested on localhost (all three states) and validated against the live
3.9.6 ensemble in this pilot. Revert `zoo2.cfg` `server.3` to the direct
address when CS6 concludes.

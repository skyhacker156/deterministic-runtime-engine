# CS6-SF1 — Pre-Registration (slow-but-connected follower)

**Case:** CS6-SF1 — a **labeled extension** of CS6 (ZooKeeper SSI under same-session failover). The frozen CS6 result is **not** reopened or amended; CS6-SF1 stands or falls on its own.
**Status:** PRE-REGISTRATION — **frozen before any harness code**. Hypothesis, state target, controls, and outcome classes below are committed in advance. Post-hoc reinterpretation of an outcome into a different class is a protocol violation.
**Pinned target:** Apache ZooKeeper 3.9.6, commit `a355171b` (identical to CS6). Global sessions. `syncLimit=5`, `tickTime` as in CS6.
**Date:** 2026-10-17
**Companion:** `CS6_RESULT.md`, `CS6_PLAN.md`, `CS6_AMENDMENT_1.md`, `CS6_G4_INSTRUMENTATION.md`.
**Hard time cap:** one bounded research block (set the wall-clock limit before starting — see §9). If the target state is not established within the cap, record the reachability limitation and stop. Reachability failure is a result, not a reason to keep debugging.

---

## 1. Why this experiment exists

CS6 established (30/30) the intermediate state `notifyHeldA = true`: a watch notification delivered Z to the application while the client session's recorded `lastZxid` stayed at A. The hypothesized stale read did **not** occur; the path was blocked at **two** barriers — the zxid reconnect gate and **global-session mobility** (a global session must revalidate through the leader, which the **partition** (HOLD/blackhole) prevented). CS6 explicitly left **out of scope** the *slow-but-connected* follower.

**The distinction that makes SF1 non-redundant:** CS6's HOLD barrier (blackhole) is also what *prevented session revalidation*. A follower that is **delayed but still connected** to the quorum preserves the revalidation path — so the **global-session-mobility barrier that stopped CS6 is lifted by construction.** SF1 asks what happens once it is lifted: does a *different* barrier stop the path, is it safe for another reason, or does a stale read become reachable?

This directly tests the discrimination question — can CBV reach a consequential state a simpler experiment could not, and classify the outcome correctly — rather than accumulate another pass/fail run.

---

## 2. Hypothesis (H-SF1)

> With the partition removed (follower S2 connected and revalidation-capable) but S2's applied state lagging in the interval `[A, Z)` at the moment of a session-preserving reconnect, a client whose application has already observed Z (via a delivered watch) but whose session `lastZxid` is still A may, on reconnecting to S2 and reading the watched path, observe pre-Z state.

**Falsification / direction:** H-SF1 is supported only by the **STALE-READ-OBSERVED** class (§7). Any blocked or safe-by-other-mechanism outcome refutes it for the tested construction.

**Precise target state (all four must hold at reconnect):**
1. Application has received the watch event carrying Z (app-level view includes Z).
2. Client session `lastZxid == A` (`< Z`) — the CS6 `notifyHeldA` condition, re-verified here.
3. Target follower **S2 is connected to the quorum and revalidation-capable** (NOT partitioned).
4. S2's `last_zxid` (per `/commands/zabstate`, = `getDataTreeLastProcessedZxid`) is in `[A, Z)` — behind Z but at/above A.

---

## 3. New harness capability required (spec, to build after freeze)

The CS6 proxy supports PASS / HOLD (blackhole) / CUT. HOLD cannot be used here: a blackhole *is* a partition and would re-impose the mobility barrier. SF1 requires a new state:

- **DELAY(d):** forward leader→follower traffic with a bounded added latency `d`, **connectivity preserved** (TCP stays up, heartbeats still flow within `syncLimit`). Purpose: hold S2's applied zxid behind Z long enough to catch a session-preserving reconnect inside the window, **without** tripping the follower out of quorum.
- The DELAY must be gentle enough that S2 stays a following, revalidation-capable member (verified via `zabstate`), and strong enough to keep S2 in `[A, Z)` across the reconnect. The usable `d` band is itself an empirical quantity to pin in the pilot.

If no `d` keeps S2 simultaneously (a) in quorum and (b) behind Z across a reconnect, that is a **reachability** finding (§9), not a negative result.

---

## 4. Forced reconnect to S2 (reuse CS6 technique)

As in CS6: client C connects for setup via the connect string, sets the watch on the target path with `getData(path, watcher, stat)` (record A via `ClientCnxn.getLastZxid()`), the writer commits Z on the leader, the watch fires (record `lastZxidAtNotify`, must `== A`), then `updateServerList(S2-only)` **after** the watch has fired and immediately before forcing the current connection closed, so C reconnects onto S2. Then the read.

The read is a plain `getData(path, false, stat)` on S2 (no `sync()` first — a `sync()` would force catch-up and is a separate control, §6).

---

## 5. Instrumentation (per trial, JSON)

`A`, `Z`, `lastZxidAtNotify` (must == A for a valid trial), S2 `last_zxid` sampled at reconnect and at read (via `zabstate`), S2 quorum/follower state at reconnect (via `zabstate`), the connected remote (reflection `remoteserver:` parse, must == S2), the read's returned `stat.pzxid`/value, and the reconnect outcome (accepted / rejected / retried). Live `zabstate` polling as in `cs6_probe.ps1` to confirm S2 was connected-and-behind-Z, not partitioned, during the window.

---

## 6. Controls (pre-committed)

- **T0 (no-delay baseline):** DELAY(0) — equivalent to CS6's converged no-fault path. Expectation: no lag window; reconnect reads Z. Confirms the rig does not manufacture staleness on its own.
- **T-SF1 (delay condition):** DELAY(d) tuned to hold S2 in `[A, Z)` across the reconnect.
- **T-SYNC (safety control):** T-SF1 construction but issue `sync()` before the read. Expectation: catch-up → reads Z. Confirms that any stale read seen in T-SF1 is attributable to the missing forced-sync path, not to a broken rig.

---

## 7. Outcome classification (committed in advance — exactly one per valid trial)

- **BARRIER-BLOCKED** — the session-preserving reconnect to S2 is refused or forced forward before the read (e.g., zxid gate rejects, session reassigned/expired, or S2 refuses until caught up). Observable: reconnect rejected/redirected, or read returns Z (caught up). *Refutes H-SF1; identifies the remaining barrier.*
- **SAFE-BY-OTHER-MECHANISM** — reconnect accepted onto S2-behind-Z, read returns **Z anyway** (S2 applied Z before the read, or ZK routed/caught up). Observable: read value/`pzxid` == Z despite S2 having been behind Z at reconnect. *Refutes H-SF1; records the mechanism.*
- **STALE-READ-OBSERVED** — reconnect accepted onto S2-behind-Z, read returns **pre-Z** state after the application already observed Z. Observable: read value/`pzxid` `< Z` while `lastZxidAtNotify == A` and S2 `last_zxid < Z` at read. *Supports H-SF1.*
- **UNINFORMATIVE** — the target state (§2) was not established this trial (e.g., S2 caught up to Z before reconnect, or watch never carried Z, or S2 left quorum). Not counted toward either direction; tallied separately.

**Adjudication if STALE-READ-OBSERVED is reached:** this does not by itself declare a defect. It adjudicates the two SSI readings already defined in CS6:
- **R-A (event-ordering only):** not a violation — monotonicity holds because pre-Z `>= A` and the session never recorded Z.
- **R-B (read-freshness after notification):** a violation — the application observed Z, then a same-session read returned pre-Z.
Report which interpretation the observation falls under; do **not** collapse R-A/R-B into an unqualified "violation."

---

## 8. Gates (a trial counts only if all pass)

- **G-SF1.1** `lastZxidAtNotify == A` (the CS6 held-state precondition).
- **G-SF1.2** S2 confirmed **connected + following + revalidation-capable** at reconnect (via `zabstate`), i.e. NOT partitioned.
- **G-SF1.3** S2 `last_zxid` confirmed in `[A, Z)` at reconnect (behind Z, at/above A).
- **G-SF1.4** the client actually reconnected onto S2 (remote parse == S2).
A trial failing any gate is **UNINFORMATIVE**, not negative.

---

## 9. Trial count, stopping, and the time cap

- **Pilot first:** find a DELAY band `d` that satisfies G-SF1.2 + G-SF1.3 across a reconnect. If none is found within the time cap → **STOP**, record "target state unreachable within budget" as the result.
- **If reachable:** N = 20 valid trials per condition (T0, T-SF1, T-SYNC), honoring the CS6 pre-registered count. Report the actual tally including UNINFORMATIVE trials; do not discard or retry to pad valid trials beyond disclosure.
- **Hard wall-clock cap:** set before starting. On reaching the cap, stop and record whatever tier of result was reached. Debugging past the cap is out of scope for this block.

---

## 10. Evidence tiers (report each finding at its tier)

- **Observed:** direct per-trial measurements (zxids, read values, connection events, `zabstate`).
- **Mechanism-established:** the barrier or safety mechanism, where supported by ZooKeeper source **and** behavior (cite source lines as in CS6).
- **Inference-untested:** anything the construction did not directly exercise (e.g., behavior at other `syncLimit`/`d` values, other follower counts). Left explicitly open.

---

## 11. Scorecard footer (lightweight, per-case)

To be filled at completion: Invariant precision · State reachability · Discrimination · Reproducibility · Independent agreement (pending) · Cost-to-evidence (wall-clock of this block).

---

## 12. Scope and what CS6-SF1 does NOT establish

- Scope: ZooKeeper 3.9.6 `a355171b`, global sessions, `syncLimit=5`, the single DELAY band found in pilot, N=20.
- Does **not** establish: SSI correctness across other versions, session modes, `syncLimit`/`d` values, follower counts, or schedules; nor anything about replay tools (that line is closed — see the Coyote+go-fuzz characterization note).
- A BARRIER-BLOCKED or SAFE-BY-OTHER-MECHANISM outcome is a **bounded negative**, not a universal guarantee. A STALE-READ-OBSERVED outcome is adjudicated R-A/R-B, not promoted to an unqualified defect. An unreachable state is a **reachability** result, scored differently from a meaningful negative.

---

## 13. Freeze and next steps

1. **Freeze** this pre-registration (commit on `cs6-zk` or a `cs6-sf1` branch; record its SHA-256, CS6_PLAN style).
2. Build the proxy **DELAY(d)** mode (§3).
3. Bring the CS6 ensemble back up (note the standing `zoo2.cfg server.3` port state from CS6 teardown).
4. Pilot for a usable `d` (§9). Then run T0 / T-SF1 / T-SYNC.
5. **No harness until this document is frozen.**

*CS6-SF1 is a search with a committed falsification condition and a hard stop. Its value does not depend on finding a defect — a bounded negative, a correctly-classified safe path, or a clean reachability limitation each advance the method.*

# Cross-Case Synthesis — CS3, CS6/SF1, CS7: the enforcement-boundary arc

**Scope.** This relates the three most recent CBV case studies against real, widely-used distributed systems:
CS3 (etcd `raft` ReadIndex, #392), CS6 + CS6-SF1 (ZooKeeper Single System Image), and CS7 (Apache Curator
`InterProcessMutex` → external resource). It is interpretation over already-committed Level-A findings — **no new
construction.** It is distinct from, and complementary to, `FOUR_SYSTEM_SYNTHESIS.md`, which asks what a system's
*verification oracle* establishes independently; this arc asks a different question (§3) and connects back to that
framework only at §6, explicitly as analogy.

**Governing method:** CBV (`PHOENIX_VERIFICATION_PROTOCOL.md`). Pins and evidence per case in §8.

---

## 1. The three cases, one line each

| Case | Target (pinned) | Headline outcome | Contribution | Not a… |
|---|---|---|---|---|
| **CS3** | etcd `raft` v3.6.0/v3.7.0, ReadIndex under `ReadOnlySafe` | No new defect; reproduced known, fixed #392 on v3.6.0 (positive control), 0/3000 on v3.7.0 | Located the **contract boundary** — the retry that triggers #392 is permitted by the *published* contract of both released versions; the restriction lives only on an unreleased branch (a documentation-scope fact stated nowhere in one place). Stopped a clean run from being over-read. | …defect discovery; …evidence the fix is complete |
| **CS6** | ZooKeeper 3.9.6 (`a355171b`), global sessions | No safety violation; the notification-to-session-state gap is **real** but doubly protected | Set out to probe one barrier (the `lastZxid` reconnect gate), **discovered a second** (global-session mobility: a global session must revalidate through the leader, which the lag-inducing partition itself prevents). Named the protecting mechanism; left one boundary explicitly open. | …stale-read demonstration |
| **CS6-SF1** | same, DELAY-proxy extension | Reached the connected-lagging follower state CS6 couldn't (16/16), still **no stale read** (0/16) | Closed CS6's open boundary by *constructing* the state a simpler experiment could not reach; found the **zxid gate is primary** (client advances to Z within ms of the watch notification), revalidation cost confounded | …a reopening of CS6 (labeled, stands alone) |
| **CS7** | Apache Curator 5.9.0 (`37c7a713`) on ZK 3.9.6 | **Stale write lands** on an unfenced resource after lock loss (Arm U 20/20); resource-side fencing rejects it (Arm F 19/19) | First *in this three-case arc* to **exhibit the invariant being violated and pair it with a control that blocks it.** In the tested process-pause schedule, connection-state detection alone did not prevent the stale write; resource-side enforcement rejected it once the newer token was registered. The lock's own sequence number is not a durable fencing token (source-confirmed) | …Curator defect; …proof every listener fails or every fence is correct |

---

## 2. What each case was actually about

- **CS3** is a *methodology* result above all: a pre-registered positive control (P1a/P1b) converts "3,000 clean trials"
  from apparent evidence-of-a-fix into "the workload never reached the failure mode," by the rule of three. The finding
  that survived is where the published contract draws the line, not a bug.
- **CS6** is a *mechanism-location* result: the invariant (SSI) holds, and the study's value is naming the **two**
  independent barriers that hold it — one anticipated, one not — and showing they are not the barrier the pre-registration
  assumed alone.
- **CS6-SF1** is a *reachability* result: it demonstrates CBV can drive a bounded construction into a consequential state
  a cruder fault model cannot reach, and still classify the outcome honestly as safe-for-another-reason rather than forcing
  a violation.
- **CS7** is an *integration-boundary* result: the invariant (at most one lock epoch's writes accepted by the resource) is
  violated, and the study shows exactly **where** enforcement has to live — at the resource, not the lock.

---

## 3. The through-line: the enforcement-boundary question

All three cases answer one three-part question in different systems:

> **Where does enforcement of the tested safety property actually occur; what behavior does the published contract
> permit; and how clearly does the documentation identify that boundary?**

These three are related but not identical — a system can enforce a property correctly while documenting it poorly, or
document a limitation clearly while leaving enforcement to the application. Keeping them separate is what lets the arc
avoid presuming that every documentation gap creates a misleading mental model.

- CS3: enforcement is correct on both released versions; the behavior that triggers #392 is **contract-permitted** on
  both, and the restriction sits on an unreleased branch — a boundary the release docs don't state in one place.
- CS6: enforcement sits at **two** barriers; the second (global-session mobility) is not framed as a safety barrier in
  the docs, and the pre-registration didn't anticipate it.
- CS7: enforcement of external-resource write authority sits **at the resource**, not the lock; Curator documents the
  stale-holder *risk* (Tech Note 10) and client-side remedies, but does not connect them to resource-side write authority
  or prescribe fencing — and the one monotonic token it exposes, it resets itself.

In every case the headline is a **boundary-location** result, not a defect. The systems behave as designed; what the
studies add is naming where enforcement actually sits and how clearly the published material marks that boundary — which
ranges from "stated nowhere in one place" (CS3) through "a real barrier the docs don't frame as one" (CS6) to "documents
the risk but not the resource-side boundary" (CS7).

---

## 4. What CS7 adds that CS3 and CS6 did not

1. **An exhibited violation with a paired control.** CS3 and CS6 were negative safety results (invariant held). CS7 is the
   first to *show the invariant breaking* (stale write lands, 20/20) **and** run a control that blocks it (fencing rejects,
   19/19). CS6 could only exhibit the *protecting* mechanism; CS7 exercises both the failure path and its remedy. Shape:
   CS6 = "doubly protected"; CS7 = "unprotected at the boundary the docs don't name — and here is exactly the protection
   the resource must add."
2. **A new locus for the method.** CS3/CS6 findings live *inside* one system's behavior. CS7 relocates the finding to the
   **integration boundary between two components** (a coordination service and an external resource). The violated invariant
   belongs to the end-to-end system, not to any single component — each component (lock expires the session correctly, client
   eventually receives LOST, app checks local state, resource accepts a write) behaves reasonably in isolation while the
   end-to-end property fails. This is the pattern the method is built to surface, now demonstrated at a seam rather than within a box.
3. **A secondary, source-grounded caveat distinct from the headline.** The `InterProcessMutex` ephemeral sequence number is
   not a durable fencing token — Curator's own `clean()` and container-node reaping reset it (`StandardLockInternalsDriver`,
   `LockInternals`). This is an independent observation with its own evidence trail, carefully *not* promoted to a safety
   breach: a correct high-water fence survives the reset (it over-rejects → availability, not safety).

---

## 5. The shared discipline that makes these credible

The same four habits recur, and they are the reason the negatives are defensible and the one positive is not over-read:

- **A positive control that separates "safe" from "never reached."** CS3 P1a; CS6 T0; CS7 Arm F (and the no-stall baseline
  logic). Without it a clean run is uninterpretable.
- **No promotion of an expected or known result to a defect claim.** CS3 (#392 is known/fixed); CS6 (the TN10 scenario is
  documented); CS7 (an unfenced resource accepting a stale write is the documented strawman — the study is only meaningful
  because Arm U uses the *documented* mitigation).
- **Keep an open boundary rather than overclaim closure.** CS6 left the slow-but-connected follower open; CS6-SF1 later
  closed it with a labeled extension. CS7 leaves the blackhole fault model and the seq-reset safety case as named, scoped
  follow-ups.
- **Source-ground the mechanism at a pinned revision.** CS6 zxid gate (`ZooKeeperServer.java:1504/1516`); CS7 `clean()` /
  `creatingParentContainersIfNeeded()`. Behavior plus source, with the honest limit stated where only one is in hand.

---

## 6. Relation to the four-system oracle synthesis (analogy, flagged)

`FOUR_SYSTEM_SYNTHESIS.md` classifies *verification oracles* into four shapes; its sharpest pair is **Category 1**
(a real behavior the mechanism never inspects) versus **Category 4** (genuine independent re-derivation that can reject a
disagreement). CS7 exhibits a structurally identical split, in the adjacent domain of **authorization** rather than
verification:

- The **unfenced** resource inspects nothing about write authority → structurally Category 1 (the authority question is
  *absent from consideration*, exactly the stale write that lands).
- The **fenced** resource independently checks a monotonic token and can reject → structurally Category 4 (independent
  rejection).

The documented Curator integration leaves write authority in the Category-1 shape; adding a resource-side fence moves it to
Category 4. This is the same "where does independent checking actually happen, versus where is a property merely assumed"
boundary the four-system synthesis found *between* systems' formal cores and their layered extensions — now shown live at a
single integration seam.

**The analogy is about independent checking, not equivalence of guarantees.** Verification (is this computation correct?)
and authorization (is this writer still allowed?) are different questions, and CS7 is not another oracle case. A resource
fence is not a Category-4 verification oracle: it checks a writer's authority/freshness, not whether the write's content is
correct — a monotonic token can reject a stale writer while still accepting an **incorrect** write from the current,
legitimate holder. The echo is worth recording only because the same independent-checking boundary was arrived at
independently, from a different starting question.

---

## 7. What this arc does NOT establish

- No generalization beyond each pinned version / configuration / fault model. CS7 is Curator 5.9.0 + ZK 3.9.6 + the
  process-pause stall; CS7's **blackhole control and no-stall baseline were not run** (named follow-up: wiring the CS6
  DELAY/HOLD proxy into the C1 harness, ~one build block).
- None of the three is a defect claim against its target. CS3 reproduced a known bug; CS6 found no violation; CS7 is an
  integration-boundary + documentation-adequacy result.
- The documentation-adequacy judgments are **argued assessments**, recorded separately from execution outcomes, never
  inferred from a single result.
- CS7's seq-reset caveat is an observation about token durability, not a demonstrated safety failure; Arm F proves the
  specific tested fence, not all fences.
- **Capability demonstrated, not comparative effectiveness.** These are three *selected* case studies, not an independent
  benchmark of CBV against competing methods. The arc shows the method can be applied productively to three different
  problems; it does **not** establish how often CBV finds consequential issues, how much it outperforms ordinary testing
  (CS3 explicitly did *not* outperform etcd's own robustness suite), or whether an independent researcher would reproduce
  these interpretations. Demonstrating a method's capability and validating its comparative effectiveness are different
  claims; only the former is made here.
- This document is Level-C interpretation over Level-A findings; it is not itself a new measurement. Whether a further case
  reveals an enforcement-boundary shape not seen here is open.

---

## 8. Evidence index

| Case | Pins | Key commits / files | Source anchors |
|---|---|---|---|
| CS3 | etcd `raft` v3.6.0 / v3.7.0, Go 1.27.0, Porcupine v1.3.1 | `a733851`→`ab528c1`; `case_study_3_raft/CS3_RESULT.md`, `results.jsonl`, `histories/` | published ReadIndex contract vs unreleased `release-3.6` branch |
| CS6 | ZooKeeper 3.9.6 `a355171b`, global sessions | branch `cs6-zk`; `case_study_6_zookeeper/CS6_RESULT.md`, `CS6_results_*.jsonl` | `ZooKeeperServer.java:1504` / `:1516` (`CLIENT_ZXID_AHEAD`) |
| CS6-SF1 | same, DELAY proxy | plan frozen `2580427C` (`e1d5ba7`); `CS6_SF1_PLAN.md`, `CS6_SF1_RESULT.md`, SF1 JSONL | same zxid gate; client advances to Z within ms of watch notify |
| CS7 | Curator 5.9.0 `37c7a713`, ZK 3.9.6 `a355171b` | branch `cs7-c1`; pre-reg freeze `00a9c62`, harness `f44568e`, result+records `0a05079`; `case_study_7_curator/CS7_C1_RESULT.md`, three `CS7C1_results_*.jsonl` | `InterProcessMutex.java:34–35`; `StandardLockInternalsDriver.java:51,60,66`; `LockInternals.java:73,77` |

---

## 9. Forward criterion for the next case

The sharpened search target the arc points to, more focused than "find a bug in a distributed system":

> **Find the next case where the apparent safety guarantee and the actual enforcement mechanism sit at different
> boundaries** — and where the experiment can distinguish, *in advance*, between (a) a real gap, (b) correct-but-poorly-
> documented enforcement, and (c) an apparent gap that turns out not to exist.

All three outcomes are useful findings under CBV if the pre-registration can tell them apart before the run. This keeps
the method aimed at boundary-location, not defect-hunting, and leaves room for the honest negative (clear docs, independent
enforcement, or no real gap) to be a result rather than a disappointment.

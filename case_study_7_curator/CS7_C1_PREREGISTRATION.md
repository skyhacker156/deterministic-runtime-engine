# CS7 (C1) — Pre-Registration: Curator lock → resource-fencing seam

**STATUS: UNFROZEN.** Draft for review. Do not build the harness until frozen. Freeze is gated on the user's review of the §0 documentation findings and the final doc surface (javadoc vs recipe-page discrepancy, TN10/TN14) being accepted.
**Case:** CS7, candidate C1 (selected provisionally).
**Research question (verbatim intent):** whether a *realistic application using the documented library* can violate an *explicit resource invariant*, and whether Curator's documentation adequately explains that risk and its mitigation.
**Pins:** Apache Curator 5.9.0, commit `37c7a713` (tag `apache-curator-5.9.0`, verified). ZooKeeper 3.9.6, commit `a355171b` (tag `release-3.9.6`) — reuse the CS6 3-node ensemble + proxy tooling. Date: 2026-10-17.

---

## 0. Documentation findings (claim vs. enforced — done, under review)

Separating Curator's actual contractual claims from our interpretation:

- **Recipe page (official), `curator.apache.org/docs/recipes-shared-reentrant-lock`** claims exactly: *"Fully distributed locks that are globally synchronous, meaning at any snapshot in time no two clients think they hold the same lock."* This is a claim about **clients' belief/coordination**, not about an external resource being protected from two writers.
- **Javadoc (source, `InterProcessMutex.java`)** claims more strongly: *"achieve an inter-process critical section."* → a **discrepancy**: the javadoc overclaims relative to the careful official page. Our earlier "critical section" framing came from the javadoc, not the recipe page.
- **Warnings (official):** *"If a SUSPENDED state is reported you cannot be certain that you still hold the lock unless you subsequently receive a RECONNECTED state."*; *"If a LOST state is reported it is certain that you no longer hold the lock."*; *"strongly recommended that you add a `ConnectionStateListener`."* Error Handling page: SUSPENDED → *"Leaders, locks, etc. should suspend"*; LOST → *"consider any locks, etc. as dirty/unstable."*
- **Absent:** no fencing-token accessor in the public API (`InterProcessLock` = acquire/acquire(t)/release/isAcquiredInThisProcess; mutex adds getParticipantNodes/makeRevocable/isOwnedByCurrentThread); `grep` for `fenc*`/stale-writer across the lock recipes = 0; the Error Handling page gives **no instruction to stop acting on the protected resource**.

**Honest reading:** Curator documents that the lock can be *lost* and recommends *detection* (a `ConnectionStateListener`). It does **not** claim resource-level mutual exclusion, and it provides **no fencing token**. The open gap is whether the *recommended detection mitigation* is sufficient to protect a resource against a **stalled** holder (it is asynchronous and cooperative), and whether the docs convey that insufficiency.

*(Remaining doc surface to confirm before freeze: Tech Note 10 "recipes that depend on being connected" and Tech Note 14; whether any official example threads a fence. Listed for completeness; findings above are the load-bearing ones.)*

---

## 1. Hypothesis

**H-C1:** A realistic application that follows Curator's documented lock guidance — acquires an `InterProcessMutex`, registers a `ConnectionStateListener`, treats SUSPENDED/LOST as lock-loss — can **still** write to an external resource **after** its lock was lost (session expiry during a holder stall) and **before** it processes the LOST event, violating the resource's mutual-exclusion invariant, because Curator's recommended mitigation is asynchronous and no fencing token is provided.

**This is NOT a claim that Curator is defective.** Curator does not promise resource protection. H-C1 tests the *integration boundary* and the *documentation adequacy*, per §9.

---

## 2. Target, resource invariant, and the stalled-writer sequence

- **System under test:** a Curator `InterProcessMutex` on the ZK 3.9.6 ensemble, two client applications (A, B), and a **protected resource** (a local monotonic register/file).
- **Resource invariant (explicit):** at most one writer mutates the resource per lock epoch; a write from a holder whose lock has been lost must not take effect. Operationalized as: the resource's value/version is never written by a client that no longer holds the lock.
- **Stalled-writer sequence (instrumented):**
  1. A acquires the lock (ephemeral sequential znode).
  2. A stalls: its ZK client channel is blackholed (proxy `HOLD`) long enough for the **server-side session to expire**, deleting A's ephemeral node. (Models the "holder paused past session timeout" case.)
  3. B acquires the lock (now free).
  4. A's channel is restored (`PASS`); A resumes and attempts a resource write.
  5. Record whether A's write reaches the resource, and whether A's `ConnectionStateListener` had already set its lock-lost flag at the instant of A's write.

---

## 3. Arms and controls (pre-committed)

- **Arm U — unfenced resource + documented mitigation.** The app follows Curator's docs: `ConnectionStateListener` sets a volatile `lockLost` flag on SUSPENDED/LOST; A checks `!lockLost` before writing. The resource does **not** check any token. *Purpose:* test whether a doc-following app can still land a post-loss write (the race window). **Explicitly demonstrates the integration boundary, not a Curator defect.**
- **Arm F — fencing-aware resource (control).** The app threads a monotonic token (derived from the lock znode sequence / `czxid`, which the app must extract itself since Curator does not expose it) into each resource write; the resource rejects any write whose token is below the highest it has accepted. *Expectation:* blocked — shows the gap is closable only by a fence Curator does not provide.
- **Control N — no-stall baseline.** Same construction, no session expiry. *Expectation:* no violation; confirms the rig does not manufacture one.

---

## 4. Outcome classification (pre-committed; exactly one per valid trial)

- **VIOLATION** — in Arm U, A's post-loss write takes effect on the resource (A wrote with `lockLost==false` at write time, B already held the lock). The doc-following mitigation did not prevent it.
- **BLOCKED** — A's write is prevented: either the documented listener set `lockLost` before A's write (mitigation sufficed), or Arm F's fence rejected it. Identify which.
- **INCONCLUSIVE** — preconditions not met: session did not actually expire, B did not acquire, A's write did not occur, or the stall window could not be engineered. (Reachability result, not "safe.")

A trial counts only if observed: A held then lost the lock (session expiry confirmed via ZK), B acquired, and A attempted the write.

---

## 5. Instrumentation / required logs

Per trial (JSON): timestamps for A-acquire, stall-start, server-side session-expiry (ZK), B-acquire, A-resume, A-write-attempt, listener-LOST-fired; A's `lockLost` flag value at the instant of A's write (the race witness); the resource's accepted/rejected decision and any fence token; A's and B's znode identities; connection-state events A received. ZK and Curator version pins recorded in each record.

---

## 6. Reachability risk (flagged, like CS6-SF1)

The VIOLATION window (A writes post-loss before processing LOST) requires engineering a race that mimics a full-process stall. A channel blackhole alone may let A's listener fire in time (→ BLOCKED). The honest modal outcome may be BLOCKED (documented mitigation sufficed against our injectable stall) or INCONCLUSIVE (window unreachable). **All three outcomes are informative** about whether the documented mitigation is adequate — that is the point, not a bug hunt.

---

## 7. Time budget, stop, N

One bounded research block, hard wall-clock cap set before starting. Pilot to establish that the stall reliably expires A's session and B acquires; then N=20 per arm if the window is reachable. If the window cannot be engineered within the cap, record the reachability limitation and stop.

---

## 8. What would falsify H-C1 / what would merely confirm a known limitation

- **Falsifies H-C1:** the doc-following mitigation (listener) reliably prevents A's post-loss write across the tested stalls — i.e., `lockLost` is always set before A can write. That would be evidence Curator's recommended mitigation is adequate against these stalls.
- **Merely confirms a known limitation (must NOT be promoted):** showing that an **unfenced resource with no listener** accepts a stale write. That is Kleppmann's known principle and a strawman. The study is only meaningful if Arm U uses the **documented** mitigation and still violates — and if the finding is tied to whether the docs convey that insufficiency.
- **Genuine contribution (if reached):** a doc-following Curator integration violates the resource invariant, and the docs do not adequately explain that lock-loss *detection* is insufficient without fencing.

---

## 9. Scope / framing guards

- Does not assert a Curator defect: Curator does not promise resource exclusion. The finding, if any, is an integration-boundary + documentation-adequacy result.
- Does not generalize beyond Curator 5.9.0 / ZK 3.9.6 / the tested stall model.
- Source-pinned and auditable (Curator `37c7a713`, ZK `a355171b`).

---

## 10. Freeze procedure

Freeze only after: (a) user review of §0 findings; (b) confirmation of TN10/TN14 and any official fenced example. On freeze: commit, record SHA-256, then build the harness (reusing the ZK ensemble + proxy; Arm U/F apps + the resource). No harness before freeze.

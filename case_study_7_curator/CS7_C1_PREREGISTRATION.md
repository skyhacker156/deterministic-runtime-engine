# CS7 (C1) — Pre-Registration: Curator lock → external-resource write-authority boundary

**STATUS: UNFROZEN — amended per review, ready to freeze pending final OK.** No harness before freeze.
**Case:** CS7, candidate C1 (locked).
**Pins:** Apache Curator 5.9.0, commit `37c7a713` (tag `apache-curator-5.9.0`, verified). ZooKeeper 3.9.6, commit `a355171b` (tag `release-3.9.6`, verified) — reuse the CS6 3-node ensemble + proxy tooling. Date: 2026-10-17.

---

## 1. Hypothesis (H-C1)

Under Curator 5.9.0 and ZooKeeper 3.9.6, an application following Curator's documented connection-state guidance **may attempt a write to an external resource after its lock has been lost.** The experiment tests whether that guidance *alone* prevents the stale write under a specified holder-stall fault model, and whether the official documentation adequately distinguishes **lock-loss detection** from **resource-enforced write authority.**

**Framing guards (binding):**
- The stale-holder scenario itself is **already documented** (Curator Tech Note 10) and is **not claimed as novel.**
- A stale write accepted by an **unfenced** resource is evidence about the **integration boundary**, not by itself evidence of a Curator defect or of inadequate documentation.
- The fencing control tests whether stale writes can be **rejected** when the resource atomically enforces monotonically increasing fencing tokens **and has already observed the newer holder's token.**

---

## 0. Documentation findings (verified; recorded as an OPEN ASSESSMENT, not a presumed deficiency)

Quoted from official 5.9.0-era docs:
- **Recipe page:** *"Fully distributed locks that are globally synchronous, meaning at any snapshot in time no two clients think they hold the same lock"* — a claim about clients' belief, not resource protection. (Javadoc says "inter-process critical section" — a stronger wording; recorded as a doc/source discrepancy.)
- **Tech Note 10:** explicitly documents the long-GC-pause sequence — 3 s session timeout, A holds the mutex, 10 s STW pause, A's session lapses, ZK deletes the node, B acquires, and *"BOTH CLIENT A AND CLIENT B WILL BELIEVE THEY ARE THE LOCK HOLDER."* Remedy offered: *"tune your JVM so that GC pauses… do not exceed your session timeout."*
- **Tech Note 14:** *"no way to completely emulate in the client the session timing,"* recommends *"treat SUSPENDED as a complete connection loss,"* *"Exit all locks, leaders, etc."*
- **Error Handling page:** SUSPENDED → suspend; LOST → treat locks as dirty/unstable. No instruction about external-resource writes; no fencing token anywhere in API or docs.

**Open assessment (to be judged, not presumed):** Curator *documents* the stale-holder/overlapping-belief risk and recommends client-side remedies (GC/timeout tuning; connection-state handling; "exit all locks"). The surfaced documentation does **not** connect those remedies to an external resource's enforcement of write authority, nor prescribe fencing as the resource-side safeguard. Whether that omission makes the guidance inadequate is an **evaluative question**, recorded separately from the execution outcome (§10).

---

## 2. Target and resource invariant

- **System:** a Curator `InterProcessMutex` on the ZK 3.9.6 ensemble; two client applications A, B; one **external protected resource** (a local monotonic register/file with an atomic compare-and-set).
- **Resource invariant (explicit):** a write from a client that no longer holds the lock must not take effect; at most one client's writes are accepted per lock epoch.

---

## 3. Fault models

- **PRIMARY — genuine process pause (faithful to TN10).** A acquires the lock with a short negotiated session timeout (e.g., 5 s; within ZK min/max = 2×–20× tickTime). A's **entire JVM process is suspended** (Sysinternals `PsSuspend`, or `NtSuspendProcess` via a small helper) for longer than the session timeout, freezing all threads including the ZK client — so A's `ConnectionStateListener` **cannot** fire during the stall. The ensemble expires A's session (verify server-side: A's ephemeral node gone, B able to acquire). A is resumed (`PsSuspend -r`); A's main thread resumes at the point before its resource write. Record whether A's write occurs before its listener processes LOST.
- **CONTROL — channel blackhole.** Proxy `HOLD` on A's client→ZK channel (our CS6 tooling). Here A's listener **can** fire (connection loss detected while A runs), so this tests the network-partition variant, not a true stall. Reported separately; conclusions limited accordingly.
- **BASELINE — no stall.** Confirms the rig does not manufacture a stale write.

*Dependency / feasibility:* `PsSuspend` is a one-tool download (accessibility cost, logged). If the process-pause arm cannot be made reliable within the time budget, preserve the blackhole + baseline and **limit all conclusions to the blackhole fault model** (stated explicitly in the result).

---

## 4. Arms

- **Arm U — unfenced resource + documented mitigation (primary).** The app follows Curator's docs: registers a `ConnectionStateListener` that sets a volatile `lockLost` flag on SUSPENDED/LOST; A checks `!lockLost` before writing. The resource performs no token check. Tests whether the documented mitigation alone prevents the post-loss write.
- **Arm F — resource-side fencing (control).** Fencing token = A's own lock znode **sequence number** (ZK guarantees it increases across successive acquisitions); the app identifies its own node via the lock path / `getParticipantNodes()`. The resource keeps the highest token accepted and **atomically** rejects any write whose token is not strictly greater. **Ordering requirement (binding):** B must present its newer (higher) token to the resource **before** A's stale write is attempted — i.e., sequence the trial B-acquires → B-writes(token_B) → A-resumes → A-writes(token_A<token_B). Otherwise the resource has not yet seen B's token and would accept A's stale token, falsely validating the fence. The fence is the **application's** responsibility built around Curator's recipe, **not** something Curator must provide for the experiment to be valid. If token extraction proves too costly, Arm F is a separately bounded sub-task and Arm U remains the primary test.

---

## 5. Outcome classification (pre-committed; keep these SEPARATE in recorded data)

- **STALE_WRITE_ACCEPTED** — A's post-loss write took effect on the resource (A held then lost the lock; B had acquired). The configured mitigation did not prevent it.
- **LISTENER_BLOCKED** — the documented listener set `lockLost` before A's write, so A did not write. The application-side mitigation prevented it *in this execution*.
- **FENCE_REJECTED** — the resource rejected A's write because A's token was below the highest it had accepted (B's token already registered). The resource independently enforced write authority.
- **INVALID_TRIAL** — a required precondition was not established (session did not expire, B did not acquire, A did not reach the write, suspend/resume failed). A reachability result, not "safe."

Do **not** treat N trials without STALE_WRITE_ACCEPTED as proof of safety — they are evidence about the tested execution and fault model only.

---

## 6. Instrumentation / required logs

Per trial (JSON): session timeout; timestamps for A-acquire, suspend-start, server-side session-expiry (ZK: A's node gone), B-acquire, resume, listener-LOST-fired, A-write-attempt; A's `lockLost` value at the instant of its write (race witness); for Arm F, token_A, token_B, the resource's highest-accepted token at A's write, and accept/reject; A's and B's lock znode identities/sequences; connection-state events A received; fault model (pause / blackhole / baseline); Curator + ZK version pins.

---

## 7. Reachability / feasibility risk

The STALE_WRITE_ACCEPTED window requires A's main thread to resume and write before its event thread processes LOST. The process-pause model makes this faithful (listener frozen during the stall); the main risk is `PsSuspend` reliability and session-timeout/suspend-duration tuning. Honest modal outcomes: STALE_WRITE_ACCEPTED (unfenced, pause) or FENCE_REJECTED (fenced) if the window is reached; LISTENER_BLOCKED (esp. blackhole control) or INVALID_TRIAL if not. All are informative about the detection-vs-enforcement question.

---

## 8. Time budget, stop, N

One bounded block, hard wall-clock cap set before starting. Pilot: establish that a process suspension reliably expires A's session and B acquires; then N=20 per arm/fault-model if the window is reachable. If unreachable within the cap, record the reachability limitation and stop.

---

## 9. Falsification / known-limitation boundary

- **Falsifies H-C1:** the documented listener mitigation reliably prevents A's post-loss write across the tested process-pause stalls (`lockLost` always set before A can write).
- **Merely confirms a known limitation (must NOT be promoted):** an unfenced resource with **no** listener accepting a stale write — that is the documented TN10 scenario and a strawman. The study is only meaningful because Arm U uses the **documented** mitigation and the question is resource write-authority + doc adequacy.
- **Contribution (if reached):** a doc-following Curator integration still violates the resource invariant under a faithful stall, establishing that lock-loss *detection* ≠ resource *write authority*, and that the official guidance does not bridge that gap — recorded as the §10 assessment.

---

## 10. Documentation assessment (recorded SEPARATELY from execution outcome)

Independent of the trial outcomes, record: (a) what the official material states (quoted, §0); (b) the mitigation it recommends; (c) whether it explicitly addresses resource-side write authority / prescribes fencing. The adequacy judgment is reported as an argued assessment, not asserted as fact, and never inferred merely from a STALE_WRITE_ACCEPTED outcome.

---

## 11. Scope / framing guards

- Not a Curator defect claim: Curator does not promise resource exclusion and documents the stale-holder risk (TN10). Finding, if any, is an integration-boundary + documentation-adequacy result.
- No generalization beyond Curator 5.9.0 / ZK 3.9.6 / the tested stall models.
- Source-pinned and auditable (Curator `37c7a713`, ZK `a355171b`).

---

## 12. Freeze procedure

Freeze on your OK: commit this pre-registration, record its SHA-256 (CS6_PLAN style), then build the harness (reuse the ZK ensemble + proxy; Arm U/F apps + the resource + the PsSuspend driver). No harness before freeze.

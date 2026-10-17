# CS7 (C1) — Result: Curator lock → external-resource write-authority boundary

**Pre-registration:** `CS7_C1_PREREGISTRATION.md` (branch `cs7-c1`), frozen at commit `00a9c62`.
**Harness:** committed at `f44568e` (`resource.py`, `C1Client.java`, `cs7_c1_run.ps1`, `pom.xml`).
**Pins:** Apache Curator 5.9.0, commit `37c7a713` (tag `apache-curator-5.9.0`, re-verified this run). ZooKeeper 3.9.6, commit `a355171b` (tag `release-3.9.6`). Date: 2026-10-17.
**Discipline:** outcome classes scored mechanically from predeclared logic (`cs7_c1_run.ps1` §classification); interpretation held until both scored arms complete; documentation assessment (§D) recorded separately from execution outcome; no expected result promoted to a defect claim.

---

## 1. What was run

Two scored arms, both under the **PRIMARY** fault model of the pre-registration — a genuine whole-process pause of client A via Sysinternals `PsSuspend` (−9 s, session timeout 5000 ms), faithful to Curator Tech Note 10's long-STW-pause scenario. In both arms client A follows Curator's **documented** connection-state guidance: it registers a `ConnectionStateListener` that sets a volatile `lockLost` flag on `SUSPENDED`/`LOST` and checks `!lockLost` immediately before writing to the external resource.

- **Arm U (primary):** unfenced resource — accepts every write. Tests whether the documented listener mitigation *alone* prevents a post-loss write. N = 20.
- **Arm F (control):** fenced resource — accepts a write only if its fencing token is strictly greater than the highest accepted, compare-and-set atomic under one lock; B presents its newer token **before** A's stale write (the §4 binding ordering requirement). N = 20.

The blackhole control (network-partition variant, where A's listener *can* fire mid-run) and the no-stall baseline were not run in this block; conclusions are therefore limited to the process-pause fault model, as the pre-registration requires when an arm is omitted.

---

## 2. Scored outcomes (pre-registered classes only)

| Arm | Resource | N | STALE_WRITE_ACCEPTED | FENCE_REJECTED | LISTENER_BLOCKED | INVALID_TRIAL |
|---|---|---|---|---|---|---|
| **U** | unfenced | 20 | **20** | — | 0 | 0 |
| **F** | fenced | 20 | 0 | **19** | 0 | 1 |

- **Arm U: 20/20 STALE_WRITE_ACCEPTED.** Every trial recorded `lockLost = false` at A's pre-write sample, A's write accepted by the resource, A's token strictly below B's already-registered token (`tokA < tokB`), and A the final writer. The documented `ConnectionStateListener`/`lockLost` mitigation did not prevent the post-loss write in a single trial.
- **Arm F: 19/19 valid → FENCE_REJECTED.** In every valid trial A's stale (lower) write was rejected by the resource because B's higher token was already the highest accepted; B remained the final writer. The one non-scored trial (F/13) is a precondition failure, not a fence breach — see §3.

Per the pre-registration §5, the Arm F result is **not** read as proof of safety; it is evidence that an atomic, monotonic, resource-side fence that has already observed the newer holder's token rejects the stale write under this fault model.

---

## 3. The excluded trial (F/13) and the sequence-counter reset

Trial F/13 scored `INVALID_TRIAL_other`: `tokA = 24`, `tokB = 0`, A accepted, final writer A. B presented a token (0) **lower** than A's (24), violating the §4 binding ordering requirement ("B must present its newer/higher token before A's stale write"). The fenced resource behaved exactly as specified — it accepts strictly increasing tokens and simply never saw a higher B token to reject A against — so the trial cannot test fencing and the classifier correctly dropped it rather than scoring it. No Arm F trial shows A's stale write landing over a *higher* registered B token.

**Mechanism (source-confirmed, Curator `37c7a713`):** the ZooKeeper child-sequence counter lives on the lock parent znode `/cs7/lock` and resets only if that parent is deleted and recreated. Curator does exactly that:

- `StandardLockInternalsDriver.createsTheLock()` creates the lock node with `.creatingParentContainersIfNeeded()` (`StandardLockInternalsDriver.java:60`, `:66`), so `/cs7/lock` is a ZooKeeper **container node**, which the server's `ContainerManager` reaps automatically once it is childless (both ephemerals gone between trials).
- `LockInternals.clean()` is documented in its own Javadoc as: *"Attempt to delete the lock node so that sequence numbers get reset"* (`LockInternals.java:73`, method at `:77`).

So the reset is **intended library behaviour**, observed here twice (F/13 and, cosmetically, U/20). It is not a rig artifact.

This yields a sharp, source-grounded **integration caveat**, recorded as an observation and not a defect:

> The `InterProcessMutex` ephemeral **sequence number is not a durable, globally monotonic fencing token** across the lock parent's lifecycle. It is monotonic only within a single lock-parent (container-node) lifetime; Curator's own `clean()` and the container-node reaper delete the parent once it is idle, and the next acquisition's numbering restarts at 0 — a token that was `24` can later be `0`. An application that extracts this number (as Arm F must, by reflection on `InterProcessMutex.threadData → LockData.lockPath`) and treats it as a fencing token inherits that reset.

**A reset does not, by itself, admit a stale write through a correctly built fence.** The two consequences are distinct and must not be conflated:
- **Availability failure (correct high-water fence).** A fence that retains the highest token accepted would, after a reset, **reject** a legitimate new holder presenting the reset token (`0 ≤ 24`). Stale-writer *safety* still holds; the cost is denial of real work.
- **Safety failure (only if the high-water mark is itself mis-handled).** If the resource's high-water mark is reset, cleared when the lock goes idle, or scoped per-session, the sequence reset could let an older token pass. This requires an incorrect resource, not merely the reset.

So the supported conclusion is narrow: the lock znode sequence number must **not** be assumed globally monotonic. A robust resource-side fence needs a token whose monotonicity is independent of the lock znode's lifetime (a monotonic counter owned by the resource, or an external epoch), not the lock's own sequence number.

---

## 4. Result against the hypothesis

**H-C1 is not falsified.** Under a faithful process-pause stall, a Curator 5.9.0 application following the documented connection-state guidance attempted and completed a write to the external resource after its lock had been lost, in 20/20 trials. The documented client-side mitigation detects loss *eventually* but does not prevent the race: on resume, A's local resource write beats its own ZK client's processing of session expiry, so `lockLost` is still `false` at the instant A writes.

The core finding stands at the **integration boundary**: **lock-loss detection ≠ resource write authority.** Arm F confirms that write authority is enforced where the write lands — a resource-side fence rejects the stale write — not by the lock library, which never promises resource exclusion.

The §9 strawman is avoided: Arm U uses the *documented* mitigation, not a no-listener naïf, so the accepted stale write is not merely the already-known TN10 scenario restated.

---

## D. Documentation assessment (recorded separately from execution outcome)

Per pre-registration §0/§10, this is an argued evaluative judgment, **not** inferred from the STALE_WRITE_ACCEPTED outcome.

(a) **What the official material states (quoted):**
- Recipe page: *"Fully distributed locks that are globally synchronous, meaning at any snapshot in time no two clients think they hold the same lock"* — a claim about clients' *belief*, not resource protection.
- `InterProcessMutex` Javadoc (`InterProcessMutex.java:34–35`): *"All processes in all JVMs that use the same lock path will achieve an inter-process critical section"* — stronger wording than the recipe page; recorded as a doc/source discrepancy.
- Tech Note 10: documents the long-GC-pause sequence and states *"BOTH CLIENT A AND CLIENT B WILL BELIEVE THEY ARE THE LOCK HOLDER."* Remedy offered: tune the JVM so GC pauses do not exceed the session timeout.
- Tech Note 14: *"treat SUSPENDED as a complete connection loss," "Exit all locks, leaders, etc."*
- Error-handling page: SUSPENDED → suspend work; LOST → treat locks as dirty. No instruction about external-resource writes; no fencing token anywhere in API or docs.

(b) **Mitigation the docs recommend:** JVM/GC and session-timeout tuning; connection-state listening; exit locks on SUSPENDED/LOST.

(c) **Whether the docs address resource-side write authority / prescribe fencing:** No. The official material documents the stale-holder risk and prescribes client-side remedies, but does not connect those remedies to an external resource's enforcement of write authority, nor prescribe fencing as the resource-side safeguard. The one monotonic value it exposes (the lock znode sequence number) it also resets itself (§3).

**Assessment:** the guidance is sound for what it claims (clients' *belief* of exclusivity, and detection) but leaves the detection-vs-enforcement gap to the reader. For an application writing to an external, non-ZK resource, the documented remedies are necessary-but-not-sufficient, and nothing in the surfaced material says so or points to fencing. This is a documentation-adequacy observation at the integration boundary — argued, not asserted — and is explicitly **not** a Curator defect claim.

---

## 5. Scope and framing guards (binding)

- **Not a Curator defect.** Curator does not promise resource exclusion and documents the stale-holder risk (TN10). The result is an integration-boundary + documentation-adequacy finding.
- **Arm F proves the specific tested fence, not all fences.** It establishes that this resource implementation rejects the stale write under the specified ordering; it does not establish that every fencing implementation is correct or that every external resource can supply the required atomic compare-and-set.
- No generalization beyond Curator 5.9.0 (`37c7a713`) / ZK 3.9.6 (`a355171b`) / the process-pause stall. Blackhole and baseline arms not run in this block.
- The sequence-reset caveat (§3) is an observation about using the lock znode sequence as a fencing token, source-confirmed, not a claim that Curator misbehaves.
- Source-pinned and auditable; all code-level claims cite file:line at the pinned revision.

---

## 6. Evidence index

- Run records committed alongside this result: `CS7C1_results_20261017-172341.jsonl`, `CS7C1_results_20261017-172534.jsonl`, `CS7C1_results_20261017-173249.jsonl`.
- Arm F (fenced) = `CS7C1_results_20261017-173249.jsonl`: 19 FENCE_REJECTED, 1 INVALID_TRIAL_other (F/13).
- Arm U (unfenced) = the 20-line, all-`STALE_WRITE_ACCEPTED` record among the above; the remaining record is the N=1 pilot.
- Per-trial witnesses (JSON): session timeout, suspend/resume timestamps, A's `lockLost` at pre-write, token_A / token_B, resource highest-accepted at A's write, accept/reject, final writer.
- Source citations (Curator `37c7a713`): `InterProcessMutex.java:34–35`; `StandardLockInternalsDriver.java:51,60,66`; `LockInternals.java:73,77`.

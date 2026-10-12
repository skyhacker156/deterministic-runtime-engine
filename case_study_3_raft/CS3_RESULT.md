# Case Study 3 (etcd raft, ReadIndex under `ReadOnlySafe`): result

Runs 2026-10-11 23:52 to 2026-10-12 00:03 EDT, on the operator's
Windows machine, Go 1.27.0, `go.etcd.io/raft/v3` v3.6.0 and v3.7.0
fetched through the Go module proxy and checksum database, Porcupine
v1.3.1 (`harness/BUILD_INFO.txt`). Plan: `CS3_EXECUTION_PLAN.md`
(draft 3). Selection: `CS3_SELECTION.md`.

## Timeline

| Commit | Pushed | Content |
| --- | --- | --- |
| `a733851` | 2026-10-11 23:50:45 | Plan, selection, dev log, harness, module checksums, 3,000 schedules, `HASHES_BEFORE_RUN.txt`. No scored run before this. |
| `e640291` | 23:52:57 | P1a |
| `09beef0` | 2026-10-12 00:00:35 | P1b, P2 |
| `ab528c1` | 00:03:30 | P3, divergence |

After `a733851` was pushed, all 28 entries in `HASHES_BEFORE_RUN.txt`
were checked against the committed files (0 mismatches), and all 3,000
schedules were regenerated independently on Linux with a different Go
version; both schedule hash lists were byte-identical. The push times
are GitHub's record. The hashes themselves are not otherwise externally
timestamped.

## Results

**P1a, directed #392 scenario on v3.6.0: gate passed.** 19 of 21 runs
(jitter 0-20) met the success condition: a non-linearizable history, the
#392 shape (a read submitted once, returned with an index below the
client-history bound, and confirmed while a twice-delivered rctx of a
different read was pending at the same stale leader), clean
conformance, and a byte-identical replay. Both builds' self-tests then
passed with the recorded P1a history as case (d): the v3.7.0 build's
oracle also judges it non-linearizable.

Jitter 6 and 9 aborted at scenario setup ("expected two held heartbeat
responses, got 0"), so they produced no verdict and count neither way.
The likely cause, not confirmed, is that jitter delayed node 1's first
messages to node 2, so node 2 did not yet know the leader when read A
was issued and dropped it. The warmup checks only that node 1 is leader
with an entry committed, not that node 2 has heard from it. This was not
seen in the 20 development jitter values (1001-1020), so the disclosed
expectation of 21 of 21 did not hold. The harness was not changed during
the study.

P1a's outcome was expected: the scenario had already been run on
development builds and disclosed (`DEV_LOG.md`). It confirms the
harness can detect #392 on the pinned, unmodified v3.6.0 release. It is
not a discovery: #392 is a known, fixed upstream bug.

**P1b, P2, P3, randomized workload.**

| Arm | Build | Trials | Verdicts | #392 shape | Client flag | Library flag | Conformance failures | Replays (matched) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1b | v3.6.0 | 2,000 | 2,000 Ok | 0 | 0 | 0 | 0 | 40 (40) |
| P2 | v3.7.0 | 2,000 | 2,000 Ok | 0 | 0 | 0 | 0 | 40 (40) |
| P3 | v3.7.0, leader-targeted | 1,000 | 1,000 Ok | 0 | 0 | 0 | 0 | 20 (20) |

Workload actually exercised:

| Arm | Reads (completed) | Reads with more than one submission | Writes completed | Isolation / pause windows | Leader-targeted windows skipped (no leader) | Ticks, median (max) |
| --- | --- | --- | --- | --- | --- | --- |
| P1b | 420,715 (417,871) | 90,382 (21.5%) | 172,309 of 179,285 | 11,231 / 7,177 | n/a | 1,286 (1,727) |
| P2 | 420,715 (417,940) | 90,482 (21.5%) | 172,387 of 179,285 | 11,271 / 7,211 | n/a | 1,290 (1,708) |
| P3 | 210,144 (206,521) | 43,581 (20.7%) | 84,887 of 89,856 | 5,249 / 3,156 | 273 | 1,196 (1,645) |

No trial reached the 6,000-tick limit, and no Porcupine check returned
Unknown.

**Divergence between builds.** Every one of the 2,000 P1b/P2 seed pairs
diverged in its message sequence, at a median of tick 72 (10th
percentile 39, range 26-514). This is expected: v3.7.0 changed what
heartbeats carry for reads. The schedules guarantee identical client
operations and fault windows for both builds; per-message fates are
identical only up to the divergence point. The P1b/P2 comparison is
matched on exogenous inputs, not on message-level schedules.

## Predictions against outcomes

| Prediction | Outcome |
| --- | --- |
| P1 (positive control): the harness detects #392 on v3.6.0 | Held, via P1a. 19 of 21 directed runs; 2 setup aborts |
| P2: no violation on v3.7.0, randomized workload | Held, 2,000 of 2,000 Ok. **Uninformative about #392**, see below |
| P3: no violation on v3.7.0, leader-targeted | Held, 1,000 of 1,000 Ok. Same limitation |
| Falsification rule | Not triggered: no non-linearizable history in P2 or P3 |

## Interpretation, under the pre-registered ladder

P1b reached the #392 shape in 0 of 2,000 trials. The plan states the
consequence in advance: a clean P2 then shows only that the randomized
workload did not reach that failure mode on either version. By the rule
of three, the per-trial probability that this workload reaches the #392
shape on v3.6.0 is below about 0.15 per cent at 95 per cent confidence.
P2 and P3 therefore cannot distinguish v3.7.0 from v3.6.0 with respect
to #392.

The strongest statement the study supports is bounded: a harness shown,
by P1a, to detect #392 when a schedule reaches it found no
non-linearizable history in 3,000 pre-registered randomized trials of
v3.7.0 under `ReadOnlySafe`. It is not evidence of linearizability for
all legal executions, and not evidence that the #392 fix is complete.

The likely reason for the coverage gap is that #392 needs a specific
conjunction: a retry delayed long enough to survive an election, held
acknowledgments of an earlier heartbeat round, and a client on the old
leader issuing a read after a write completed elsewhere. Independent
random faults at these rates rarely line that up. This is an inference
from the P1a trace, not a measured result.

## What the method contributed, and what it did not

- **It did not find a new defect.** P1a reproduced a known, fixed bug.
- **It located the contract boundary precisely.** The retry that
  triggers #392 is permitted by the published contract of both
  released versions; the restriction appears only on the unreleased
  `release-3.6` branch. That is a documentation-scope fact the upstream
  record does not state in one place.
- **It stopped a clean run from being over-read.** Without P1b, 3,000
  clean v3.7.0 trials would read as support for the fix. The
  pre-registered positive-control measurement shows they say nothing
  about it. This is the study's clearest methodological result.
- **Against the conventional baseline** (criterion 5): etcd's own
  robustness suite already checks client histories with Porcupine and
  first surfaced the bug behind #392 at system level, via Antithesis.
  This study adds a library-level, contract-compliant reproduction with
  index attribution; it does not show the method outperforms
  conventional testing.

## Deviations from the plan

1. P1a: 19 of 21, not the disclosed expectation of 21; two setup aborts.
2. Toolchain Go 1.27.0, not 1.26; the plan required 1.26 or newer.
3. P1a and development runs before hashing, disclosed in `DEV_LOG.md`
   and plan draft 3. Reserved seeds were not used before `a733851`.
4. `build.ps1` failed on its first attempt (argument quoting) and was
   fixed before anything was built; logged.
5. Console captures (`P1b_console.txt`, `P2_console.txt`,
   `P3_console.txt`, `divergence.txt`) are UTF-16, as written by
   PowerShell redirection. The scored data is `results.jsonl` and
   `histories/` in each arm.

## Follow-up, not run, would need its own pre-registration

1. A targeted workload aimed at the #392 conjunction (retries clustered
   around leader changes, long delays on heartbeat responses), with a
   reachability measurement on v3.6.0 fixed **before** any v3.7.0 run.
   Only a workload that reaches #392 on v3.6.0 can say anything about
   the fix.
2. The P1a precondition fix (wait until every follower knows the leader
   before issuing read A), as a written amendment, rerun on new jitter
   values.

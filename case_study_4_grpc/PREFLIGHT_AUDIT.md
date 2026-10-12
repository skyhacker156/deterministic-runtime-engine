# Case Study 4: preflight audit before the scored session

Written 2026-10-12, after amendment 2 (`fb14d33`) and the second Java
development run (`55ccde4`), before any scored run. Requested by the
operator's review of the same date, which set five conditions. This file
adds no criteria: every rule below is quoted or derived from `CS4_PLAN.md`
(`ca4ccaa`), `CS4_AMENDMENT_1.md` (`ae942d8`) and `CS4_AMENDMENT_2.md`
(`fb14d33`). Where a case is not covered by those documents, it is marked
**not covered** and stated as such.

## 1. Inputs frozen

- `HASHES_BEFORE_RUN.txt` is computed on the operator's machine from the
  files and binaries actually on disk, committed and pushed in the same
  commit as this file. It lists: the plan, the selection draft, both
  amendments, this audit, the scored-session script, every git-tracked
  file under `harness/go` and `harness/java`, the eight Go binaries, the
  two planted `stream.go` files, and every JAR in the Java client's
  runtime classpath.
- That commit is then checked from a clone (sandbox): every listed
  source file's hash must equal the file at the commit. Binaries and JARs
  exist only on the operator's machine; their hashes are checked by the
  scored script itself.
- `harness/run_scored.ps1` refuses to start unless every entry in
  `HASHES_BEFORE_RUN.txt` matches the disk, `HEAD` equals the pushed
  `origin/cs4-grpc`, `case_study_4_grpc` has no uncommitted or untracked
  change, no harness server or proxy is running, and
  `GRPC_EXPERIMENTAL_XDS_RLS_LB` is unset.

## 2. Scored-session script against the plan

| Plan requirement | `run_scored.ps1` |
| --- | --- |
| Pins: `go184` v1.84.0, `go168` v1.68.2, `java` 1.84.2 (am. 1) | Fixed binaries and JARs, hash-checked; each client also refuses a label that does not match its build |
| One session, operator machine, both languages against the same server binary | One `server.exe` (hash-checked) for every call |
| 20 calls per decision scenario per configuration; 50 for T | `$DecisionN = 20`, `$TimingN = 50` |
| Sanity S on every decision-track configuration | Step 1: S for `go184`, `java`, `goMX1`, `goMX5` |
| Planted controls run on X1 and X5 before any subject run in those scenarios | Step 2: `goMX1` X1, `goMX5` X5, before step 3 |
| Subject decision track: X5, X1, X2 (three rows), X4 (two rows) for `go184`, `java` | Step 3, 14 runs |
| Timing track T for `go168`, `go184`, `java`, `javaNoJitter`; variable set before JVM start for `javaNoJitter` only | Step 4; variable set for that one process and removed after |
| Replay rule: a full rerun of the decision track reproduces every tuple | Pass r2 repeats steps 1-3 (20 runs) on a fresh server process; `replay_r1.json` and `replay_r2.json` compared byte for byte, result in `REPLAY_COMPARE.txt` |
| Development runs must not include subject runs of X5, X1, X2, T | None were made (DEV_LOG.md); this script is the first |
| Fail-stop, no silent rerun | Any client or server failure stops the session; `ABORTED.txt` names the step; everything written is kept, hashed and committed; the results folder and every log must not pre-exist, so nothing is overwritten. An interrupted session leaves its folder on disk and a new one gets a new timestamped folder |

The fresh-server choice for r2 is the script's; the plan says "a full
rerun" and does not specify the server process.

**Dry run (sandbox, 2026-10-12).** A copy of the script, changed only in
the repository path and path separators, was run under PowerShell 7.4.6
with the real `server` and `checker` (Linux builds of the same source)
and stand-in clients that write well-formed logs without calling the
server, in a scratch repository with a bare remote:

- Normal run: 44 client steps in the order above; both checker passes;
  replay files compared; 59 result files hashed; committed and pushed.
- Abort run (stand-in made to fail at `r2/java/X2HI`): stopped there,
  server stopped, 45 files kept with `ABORTED.txt`, committed and pushed,
  non-zero exit. `javaNoJitter` saw the variable `false`; every client
  after it saw it unset.
- Refusals, each creating no results folder: a binary changed after the
  freeze; an untracked file under `case_study_4_grpc`; the variable set in
  the shell.

One defect was found and fixed before the dry run: client console output
would have mixed with the function's return value (the same class as the
`Start-Bg` error in DEV_LOG.md); client output now goes to `Out-Host`.
Not exercised by the dry run: Windows PowerShell 5.1 itself, Windows
paths, and real clients. The real clients and server were exercised on
the operator's machine in the development runs.

## 3. Checker rules against the plan

`harness/go/internal/oracle/oracle.go`, line numbers at `fb14d33`.

| Plan rule | Checker |
| --- | --- |
| Outcome tuple: (attempts seen at the server, final status at the client) | `Tuple` (94-103): attempts = server log lines for the call ID; final code from the client log |
| X2: *immediate* below 0.5 s, *waited* at least 1.8 s, else *other*; status of a waited call recorded, not scored | `ElapsedClass` (83-91), `ImmediateBelowNs` (24), `WaitedAtLeastNs` (25); waited final replaced by `*` (99-101) |
| All 20 calls of a scenario give one tuple, or the scenario is uninformative (nondeterminism) | `analyzeDecision` (188-214): INCOMPLETE if calls != 20 (201), NONDETERMINISTIC if more than one tuple (203), RECORDED if no prediction (205), else MATCH or MISMATCH |
| Predictions per configuration and scenario | `DecisionPredictions` (57-70); identical to the plan's tables (S, X5, X1, X2HI, X2MAX, X2NEG for `go184` and `java`; X4 recorded; `goMX1` S and X1, `goMX5` S and X5) |
| T: *r* = delay / 200 ms; A6: no *r* below 0.80 and at least 95% at most 1.40 (am. 2); old: at least 70% below 0.80; else neither | `RLow` (31), `RHigh` (32), `A6MinAtMostHi` (33), `OldMinBelowLo` (34), `ClassifyTiming` (234-258) |
| T sample: 50 calls, 4 delays each | `analyzeTiming` (260-292): INCOMPLETE unless 50 calls, 200 delays, no malformed call |
| T predictions: `go168` old, `go184` A6, `java` A6, `javaNoJitter` old | `TimingPredictions` (73-78) |
| Replay rule compares tuples, not timing | `ReplayView` (298-305): decision results without finals or timing |

The checker evaluates each (configuration, scenario) row against its own
predicted tuple. It does not combine rows into claim verdicts; that is
section 5, applied by hand in the result write-up. The self-test
(`oracle_test.go`) covers every verdict class, the X2 and T boundaries,
the replay view and the C1 rule; planted defects in the checker were
caught (DEV_LOG.md). On the operator's machine: `goMX1` X1 and `goMX5`
X5 detected; S MATCH for `go184` and `java`.

## 4. Tracks kept apart

- **Decision track** (S, X5, X1, X2, X4): whether and how many attempts
  reach the server, per client and scenario. Each claim is established
  for each client separately from its own rows.
- **Timing track** (T): characterises backoff delays only. It cannot
  establish or refute any retry-decision claim, and no decision-track
  conclusion is drawn from T.
- Finding 2 of amendment 2 (Java retry gaps of 12.7 to 40.2 ms for a 10 ms
  pushback) is a timing observation. It is not a decision-track defect and
  is not scored.

## 5. What each result means (fixed before the run)

Quoted or derived from the plan; nothing here is a new criterion.

**Preconditions for reading any decision-track row.** The configuration's
S row is MATCH (harness sees a retry), and, for X1 and X5, the matching
planted control is MATCH. Otherwise the subject row is reported as
uninformative (plan, "Controls"). The replay rule must hold; a row whose
r1 and r2 tuples differ is reported as nondeterministic and uninformative.

**X5 (primary).**
- `java` X5 MATCH, (2, OK) in 20 of 20 calls: X5 holds for grpc-java.
  This is a reproduced behaviour, not yet a defect claim. The plan's "If
  X5 holds" steps follow before any claim: rerun (the r2 pass serves as
  the first), minimal reproduction, a unit-level reproduction against
  `RetriableStream`, a renewed issue search, and the reporting route.
  The contract basis is A6 case 1 (OK: "return success") and line 117
  (only a non-OK status is checked against the retry policy); whether
  grpc-java's behaviour violates A6 or exploits its residual ambiguity is
  argued in the result, not assumed.
- `java` X5 (1, OK) in 20 of 20 calls, with the preconditions met: X5 is
  false for grpc-java (plan, falsification rule).
- `go184` X5 with 2 attempts: an unpredicted finding against `G0` for
  grpc-go, reported separately (plan).
- Any other `java` X5 tuple (for example 3 attempts, or a non-OK final
  status): **not covered**. Reported as observed; X5 neither confirmed
  nor falsified.

**X1 (characterisation).** Known behaviour asserted by grpc-java's own
test. MATCH on both clients records a divergence between the two
implementations and a specification question (A6 summary cases 2 and 5).
Not a defect claim in either direction (plan).

**X2 (secondary).** Holds only if `go184` treats X2HI like X2MAX (both
waited, 1 attempt) and `java` treats X2HI like X2NEG (both immediate,
`UNAVAILABLE`, 1 attempt). If either calibration row (X2MAX, X2NEG)
misses its prediction for a client, X2 is uninformative for that client
(plan). Only the parse difference is claimed; the deadline ending is not.

**X4.** Recorded, not scored (plan).

**T.** If `go168` is not OLD_RANGE, the timing oracle is invalid and the
whole timing track is uninformative (plan). Otherwise each configuration's
class is compared with its prediction. `javaNoJitter` OLD_RANGE (X3) is
recorded as a coupling between two features sharing one variable, not a
defect (plan). A `java` or `go184` NEITHER is reported with its fractions;
it is not reinterpreted after the fact.

**Null and inconclusive results** are reported as such. No threshold,
prediction, sample size or checker rule is changed after the run except
by a dated amendment that leaves the original run and its verdicts in
place.

## Limits of this audit

It checks consistency between documents, code and a dry run. It does not
certify the results, and it was written by the same party that built the
harness (plan, "What this study cannot establish").

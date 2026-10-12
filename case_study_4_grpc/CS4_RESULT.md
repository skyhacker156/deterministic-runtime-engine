# Case Study 4 result: gRPC client retries

Written 2026-10-12 from committed data only. Governing documents:
`CS4_PLAN.md` (`ca4ccaa`), `CS4_AMENDMENT_1.md` (`ae942d8`),
`CS4_AMENDMENT_2.md` (`fb14d33`); readings fixed in advance in
`PREFLIGHT_AUDIT.md` section 5 (frozen at `47ff80a`). Section 2 records
observations only; interpretation starts in section 3.

**Status of the primary claim: X5 is a reproduced behaviour under
contract review. It is not a confirmed defect, and no security or
production impact is claimed.**

## 1. What was run

| Item | Value |
| --- | --- |
| Subjects | grpc-go v1.84.0 (`go184`); grpc-java 1.84.2 from Maven Central (`java`; amendment 1) |
| Timing control | grpc-go v1.68.2 (`go168`) |
| Planted copies | grpc-go v1.84.0 with the plan's edits at `stream.go` 857 (`goMX1`) and 857, 964 (`goMX5`) |
| Server | grpc-go v1.84.0, native transport, plaintext, 127.0.0.1; one server-streaming method that sends no messages |
| Operator machine | Windows, Go 1.27.0, Temurin 21.0.12.1+1 |
| Freeze | `47ff80a`: `HASHES_BEFORE_RUN.txt`, 76 entries, all verified by the session before the first call |
| Session | `results/scored_20261012_190314/`, commit `764722a`, 2026-10-12 19:03:14 to 19:10:15 UTC, no failure |
| Passes | r1 (server process A): sanity S, planted controls, subject decision track, timing track. r2 (fresh server process B): decision track again |

Gates before the session: C1 PASS (`d26d293`), C2 PASS (`93c704f`), C3
sources (`ae942d8`) and binaries (`8f0d6b2`), C4 (`ed57edf`). No subject
run of X5, X1, X2 or T was made before the session (`DEV_LOG.md`).

## 2. Observations

Each decision row is 20 calls; each T row 50 calls (200 delays). "Attempts"
is the number of times the server handler ran for one call; "final" is the
status the client application received. Identical in r1 and r2 for every
decision row (`REPLAY_COMPARE.txt`: both replay files
`3A9CC1719F1C5DD6118052F76773EC0E3FFA0834BD112A3D3D5DD92ED2E75001`).

| Scenario | Server, attempt 1 / later | `go184` | `java` | Controls |
| --- | --- | --- | --- | --- |
| S | `UNAVAILABLE` + pushback 10 / OK | 2, OK x20 | 2, OK x20 | `goMX1` 2, OK; `goMX5` 2, OK |
| X5 | OK + pushback 10 / OK | 1, OK x20 | **2, OK x20** | `goMX5` 2, OK x20 |
| X1 | `INVALID_ARGUMENT` + pushback 10 / OK | 1, `INVALID_ARGUMENT` x20 | 2, OK x20 | `goMX1` 2, OK x20 |
| X2HI | `UNAVAILABLE` + pushback 2147483648 | 1, `DEADLINE_EXCEEDED` at 2.000-2.002 s | 1, `UNAVAILABLE` at 3-6 ms | |
| X2MAX | `UNAVAILABLE` + pushback 2147483647 | 1, `DEADLINE_EXCEEDED` at 2.000-2.001 s | 1, `DEADLINE_EXCEEDED` at 2.002-2.017 s | |
| X2NEG | `UNAVAILABLE` + pushback -1 | 1, `UNAVAILABLE` at 0-22 ms | 1, `UNAVAILABLE` at 3-7 ms | |
| X4P | `UNAVAILABLE` + pushback `+5` / OK | 2, OK x20 | 2, OK x20 | |
| X4Z | `UNAVAILABLE` + pushback `007` / OK | 2, OK x20 | 2, OK x20 | |

X5 detail (server log, both passes): for every `java` X5 call the server
logged attempt 1 sending OK with `grpc-retry-pushback-ms: 10`, then attempt
2 sending OK with no pushback, 13.0 to 29.1 ms later; the client received
OK once. For every `go184` X5 call the server logged one attempt.

Timing track (r1, *r* = delay / 200 ms):

| Configuration | Share of *r* below 0.80 | Min *r* | Max *r* | Class |
| --- | --- | --- | --- | --- |
| `go168` | 0.760 | 0.012 | 1.000 | OLD_RANGE |
| `go184` | 0.000 | 0.807 | 1.267 | A6_RANGE |
| `java` | 0.000 | 0.836 | 1.263 | A6_RANGE |
| `javaNoJitter` | 0.795 | 0.065 | 1.081 | OLD_RANGE |

Checker: every predicted row MATCH in r1 and r2; X4 rows RECORDED; orphan
and mislabeled attempts 0 (`checker_r1.txt`, `checker_r2.txt`).
**Independent recomputation:** every row above was recomputed from the raw
server and client logs by a separate script that does not use the checker
(sandbox, from a clone of `764722a`), with the same results, and confirmed
that each scenario's server responses were exactly the plan's table. All
59 result files re-hash to `SHA256SUMS.txt`.

## 3. Readings against the plan

Preconditions (`PREFLIGHT_AUDIT.md` section 5): S MATCH for both subjects;
planted controls detected for X1 and X5; replay rule holds; gates passed.
Every subject row is therefore informative.

- **X5 (primary): holds for grpc-java.** Predicted 2 attempts for `java`
  and 1 for `go184`; observed in all 40 `java` and 40 `go184` calls across
  both passes. The falsification condition (`java` at 1, OK in 20 of 20)
  did not occur. No unpredicted `go184` retry occurred.
- **X1 (characterisation): divergence as described.** grpc-java retries a
  non-retryable code when a valid pushback is present, as its own test
  asserts; grpc-go does not. Recorded as a divergence and a specification
  question (A6 summary cases 2 and 5), not a defect in either client.
- **X2 (secondary): holds for both clients.** `go184` treats 2147483648
  as it treats 2147483647 (waits until the deadline); `java` treats it as
  it treats -1 (no retry, server status returned at once). Both
  calibration rows matched. Only the parse difference is claimed.
- **X4 (recorded):** both clients accept `+5` and `007` as valid pushback.
- **T:** the `go168` control is OLD_RANGE, so the timing oracle is valid.
  `go184` and `java` apply A6's 0.8-1.2 jitter; `javaNoJitter` reverts to
  the pre-2024 range, so **X3 is confirmed**: one environment variable
  that also gates RLS route lookup controls retry jitter. Recorded as a
  coupling, not a defect.
- **Amendment 2:** no delay exceeded 1.30 in any configuration (maximum
  1.267), so raising the A6 upper bound to 1.40 changed no verdict; every
  timing verdict is the same under the pre-registered bound. The Java
  warm-up did matter for X2: each warm-up took 550 to 617 ms, after which
  `java` X2 calls classed as immediate at 3 to 7 ms.

All pre-registered predictions were borne out. The corrections made before
the run stay visible where they were made: plan, "Corrections to draft 3";
`DEV_LOG.md` for every process error.

## 4. X5: what is established and what is not

Established, for this configuration: grpc-java 1.84.2, with a retry policy
and no hedging, sends a second attempt after a trailers-only response with
status OK and a valid `grpc-retry-pushback-ms`, so a server handler runs
twice for one successful call. grpc-go 1.84.0 does not. The source path
read in gate C2 (`RetriableStream.closed()` reaching `makeRetryDecision`
with no status check, 1006 and 1065-1097 at 1.84.2) is consistent with the
observation.

Not yet established:

1. **That the second attempt is created by that path at runtime.** C2 is a
   source reading; no runtime trace links attempt 2 to
   `RetriableStream`'s retry scheduling. (Next step 3.)
2. **That it violates A6.** For a violation: A6 case 1 ("OK: Successful
   response, return success to client application") and line 117 (only a
   non-OK status is checked against `retryableStatusCodes`). Against, or
   at least leaving room: A6 lists "pushback: retry in *n* ms" as its own
   response type without saying which governs a response that is both OK
   and pushback; the state diagram's edge "failure or pushback: retry"
   leads to the retry-configuration check and does not exclude an OK
   response carrying a pushback; and line 209 retries after a pushback
   "when it is appropriate to retry the RPC" without defining appropriate.
   Both readings are recorded; the question is not settled here.
3. **Impact.** It needs a server that sends a pushback with OK. How often
   servers do that is unknown; no production or security impact is claimed.
4. **Generality.** Shown only for a server-streaming method with a
   trailers-only response, the unshaded Netty transport, loopback, one
   Windows machine. Other transports, unary calls, OK responses with
   headers, hedging and other grpc-java versions were not tested.

## 5. Next steps (plan, "If X5 holds")

1. Rerun: done (pass r2).
2. Minimal reproduction: the smallest server and grpc-java client showing
   one successful call producing two handler executions.
3. Runtime trace: a client stream tracer recording where attempt 2 is
   created, with no change to grpc-java.
4. Fresh prior-art search: grpc-java issues and pull requests, gRFC
   discussions; the scope of the search is recorded, not novelty claimed.
5. Reporting route, decided before any write-up beyond this repository.
   Checked 2026-10-12: grpc-java's `SECURITY.md` points to the gRPC CVE
   process (`grpc/proposal` `P4-grpc-cve-process.md`, last changed
   2023-06-09), which asks that suspected vulnerabilities be reported
   privately to grpc-security@googlegroups.com, including when the reporter
   is "unsure how a vulnerability affects gRPC", and not used for issues
   that are not security related. The classification is a deliberate
   decision still to be made.

The plan, the X5 prediction (since `ca4ccaa`) and these results are on the
public branch `cs4-grpc`, which the plan allows ("this repository").

## 6. Limits

- Out-of-class probe: not evidence that CBV transfers within its stated
  class (plan, "Label and governance").
- Two implementations, one machine, one operator, who also built the
  harness and wrote the plan.
- The checker and the independent recomputation were written by the same
  party; their agreement shows the arithmetic, not the absence of a shared
  misreading of the plan.

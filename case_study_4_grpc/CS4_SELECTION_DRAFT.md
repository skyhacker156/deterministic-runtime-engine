# Case Study 4: selection screen, gRPC client retries (draft 3, not committed)

Draft 1 written 2026-10-12 before any harness existed. Draft 2, same day,
after a source and test-suite audit of draft 1. Draft 3, same day, adds an issue-tracker search run by
Gemini at the operator's request and two paper checks ("Feasibility and preconditions"). Nothing has been built or
run. Everything below comes from the specification, source code, test
suites and commit history at the pins given. Predictions are
source-derived and untested.

## What changed from draft 1

- **X1 is no longer a prediction.** grpc-java's own test suite asserts the
  behaviour (`RetriableStreamTest`,
  `throttledStream_FailWithNonRetriableStatusCode_WithRetriablePushback`):
  a non-retryable status with a valid pushback is retried, and the
  throttle is not charged. It is a deliberate, tested design choice, so
  under Case Study 3's rule ("the answer is not already known") it cannot
  be a discovery. It is kept as a characterisation of a cross-implementation
  divergence.
- **New primary claim X5**, found while checking a draft-1 open item: a
  successful (OK) response can be retried in grpc-java.
- **The specification is less ambiguous on X1** than draft 1 said (see
  "Specification").
- **X2 narrowed**: the deadline half of it does not discriminate.
- **Controls relabelled**: no historical bug exists to serve as a positive
  control for the retry-decision oracle; planted-defect controls are
  specified instead.
- **Pins fixed** for all implementations.
- Draft 1's baseline survey read grpc-go's tests only; grpc-java's are now
  included.

## Governance and framing (operator decision, accepted 2026-10-12)

CBV (`PHOENIX_VERIFICATION_PROTOCOL.md`) governs. The four-category
taxonomy line (`FIFTH_CASE_CANDIDATES.md`, uncommitted), in which gRPC was
candidate 3, is separate and selected nothing.

gRPC is **outside the class the protocol was written for**: it fails
deterministic execution, persistent replayable state and integrity
artifacts among the six selection criteria; it meets stated claims (a
normative specification, gRFC A6), real seams, and a different
philosophy. This study is recorded as an **out-of-class probe**. It does
not count as evidence that CBV transfers within its stated class; Case
Studies 2 (FoundationDB) and 3 (etcd raft) remain that evidence. Kafka
stays the candidate for a later in-class study.

What survives of the class: X5, X1 and X2 concern whether a second
attempt happens at all. That is a deterministic function of the status,
the trailers and the retry policy, so a byte-identical replay rule
applies to them. Backoff timing (`G1`, X3) is random by design and forms
a separate statistical track with its own acceptance criteria.

**Scope bound.** The study stops after the source and oracle audit (the
paper stage) if X5 is refuted by source reading or by a quick
construction check; it does not grow into an open-ended investigation.

## Pins

| Implementation | Pin | Role |
| --- | --- | --- |
| grpc-java | `v1.84.3`, `0ea6d0a6efd2b08cf40fc9b30a89c10f83ad7059` (tagged 2026-10-12) | Subject. Its `RetriableStream.java` differs from master `cf7c13c` only in a cancel-registration race fix; the lines cited below are unchanged |
| grpc-go | `v1.84.0`, `e84aa5ab` (2026-09-18) | Subject |
| grpc-go | `v1.68.2`, `c982e40790533e2e360bcea963a152b6cfa37b45` (2024-12-18) | Timing control only |
| gRFC A6 | `grpc/proposal` `dc9fd4f` (2024-08-29), the last change to the file | Specification |

Line numbers below refer to these pins.

## Specification

gRFC A6, "Client Retries". The text that bears on the claims:

- Line 207 (`G2`): pushback is "an ASCII encoded signed 32-bit integer
  with no unnecessary leading zeros"; "negative or unparseble" means do not
  retry.
- Line 209 (`G3`, `G4`): "When a client receives an explicit pushback
  response from a server, **and it is appropriate to retry the RPC**, it
  will retry after exactly that delay." The delay then resets to
  `initialBackoff`.
- Summary of Retry and Hedging Logic: five response types. Case 1, "OK":
  "Successful response, return success to client application". Case 2,
  "Fatal Status Code": "Don't retry". Case 5, "Pushback: Retry in n ms".
- State diagram (`A6_graphics/StateDiagram.svg`): "failure or pushback:
  retry" leads to "Check Retry Config to Determine if Retry Should be
  Performed", and only then to "retry should occur".
- Line 193: only retryable or non-fatal failures, or a "do not retry"
  pushback, count against the throttle, to avoid "conflating server
  failure with responses to malformed requests (such as the
  `INVALID_ARGUMENT` status code)".

On X1, line 209 and the state diagram point to the retry configuration
deciding, which is grpc-go's behaviour. The five-case summary, which lists
"fatal status code" and "pushback: retry" as separate types without saying
which governs a response that is both, is the residual ambiguity. On X5
there is none: OK is case 1.

## Candidate claims

| ID | Claim | A6 source |
| --- | --- | --- |
| `G0` | An OK response is returned as success and is not retried | Summary, case 1 |
| `G1` | Without pushback, the delay before retry *n* is `min(initialBackoff*multiplier^(n-1), maxBackoff) * random(0.8, 1.2)` | Exponential Backoff (as amended 2024-08-29) |
| `G2` | Pushback outside signed 32-bit range, negative or unparseable means do not retry | Line 207 |
| `G3` | After a pushback, the next non-pushback delay resets to `initialBackoff` | Line 209 |
| `G4` | A fatal status is not retried; pushback applies only where a retry is appropriate | Line 209, state diagram; summary cases 2 and 5 (residual ambiguity) |
| `G5` | Once response headers are received, the call is committed and never retried | Commitment section |

## Enforcement, read in source

| | grpc-go v1.84.0 (`stream.go`, `shouldRetry`, 800-894) | grpc-java v1.84.3 (`RetriableStream.java`) |
| --- | --- | --- |
| Commitment | Retry considered only for trailers-only responses (827-829) | `headersRead` commits (899-904). A trailers-only response never calls it: Netty routes end-of-stream headers to `transportTrailersReceived` (`NettyClientStream.java`), which goes to `inboundTrailersReceived`, not `inboundHeadersReceived` |
| OK status | End of stream with status OK returns success before `retryLocked` is reached (`withRetry`, 964) | No OK check before `makeRetryDecision`; the only `isOk()` in the file is in the hedging decision |
| Fatal code plus valid pushback | Code checked first (856-859): no retry | Valid pushback sets `shouldRetry` without checking the code (1089): retry. Throttle not charged |
| Pushback parse | `strconv.Atoi`, 64-bit `int`: 2^31 accepted (834-841) | `Integer.valueOf`: 2^31 throws, mapped to -1, no retry (1121) |
| Delay past deadline | Waits; ends with the context error, `DEADLINE_EXCEEDED`. Acknowledged in a TODO (883-884) | Not examined |
| `G1` jitter | `0.8 + 0.4*rand.Float64()` (878) | `0.4*random+0.8` if `isExperimentalRetryJitterEnabled`, else `random.nextDouble()` (pre-2024 range) (855) |
| Jitter switch | none | `getFlag("GRPC_EXPERIMENTAL_XDS_RLS_LB", true)`, an environment variable that also gates xDS route lookup (`XdsRouteConfigureResource.java` line 74) |

grpc-go v1.68.2 has the same pushback and code checks (669, 690) and draws
the backoff as `rand.Int63n(cur)`, uniform on `[0, cur)` (713).

## Claims for the study

**Primary.**

- **X5, `G0`.** A server-streaming method with a retry policy. The server
  completes the call with status OK, sends no messages and no headers
  (a trailers-only response), and sets `grpc-retry-pushback-ms: 10`.
  Predicted: grpc-java makes a second attempt about 10 ms later, so the
  handler runs twice for a call that succeeded; grpc-go does not.
  Unverified preconditions, to be checked at the construction stage: that
  a grpc-go server sends trailers-only for a handler that returns without
  sending, and that nothing above `RetriableStream` in grpc-java
  intercepts the OK close first.

**Characterisation (known behaviour, not a prediction).**

- **X1, `G4`.** Non-retryable status (`INVALID_ARGUMENT`) plus
  `grpc-retry-pushback-ms: 10`. grpc-java retries and does not charge the
  throttle, as its own test asserts; grpc-go does not retry. Measured:
  number of attempts at the server, and the throttle effect (observable as
  whether later retryable failures are suppressed sooner in grpc-go than
  in grpc-java under the same sequence). Recorded as a divergence and a
  specification question, not as a found defect.

**Secondary.**

- **X2, `G2`.** Retryable status plus `grpc-retry-pushback-ms: 2147483648`.
  grpc-java: no retry, the server's status returned at once. grpc-go:
  retry scheduled about 24.9 days out. Only this difference is claimed.
  The `DEADLINE_EXCEEDED` ending in grpc-go is not, because it happens for
  any pushback longer than the remaining deadline, including the valid
  2147483647, and is acknowledged in grpc-go's source.

**Timing track (statistical).**

- **`G1` control.** grpc-go v1.68.2: about 80 per cent of non-pushback
  delays below `0.8 * cur`; v1.84.0 and grpc-java default: none. The
  acceptance criteria (sample size, tolerance) are set before any run.
- **X3, `G1`.** grpc-java with `GRPC_EXPERIMENTAL_XDS_RLS_LB=false`:
  delays revert to the old range. The flag was added in `44e92e2c2`
  (PR #11858, 2025-02-06), described there as "a flag for experimental
  jitter"; it reuses the variable that gates RLS route lookup. Whether the
  sharing was intended cannot be read from the code; recorded as a
  coupling, not as a defect.

**Recorded, not scored.**

- **X4, `G2`.** `+5` and `007` parse as valid in both. Whether they are
  "unparseable" under "no unnecessary leading zeros" is not settled by the
  text.

`G5` is not tested: no positive control for it has been found.

## Controls

- **Timing oracle.** grpc-go v1.68.2 is a genuine positive control: a
  documented behaviour, correct before the 2024-08-29 revision and
  non-conformant after it, reached by every retry. It validates the timing
  oracle only.
- **Retry-decision oracle.** No fixed pushback or retry-decision bug was
  found in either implementation's history (`--grep=pushback`: none in
  grpc-go; three unrelated flow-control commits in grpc-java). Two controls
  replace it, both to be specified in the plan before any run:
  - *Sanity check:* a retryable status with a valid pushback must produce
    exactly one retry in every implementation. It shows the harness can
    see a retry; it is not a defect-detection control.
  - *Planted-defect controls (M-series):* for each primary or secondary
    claim, a copy of grpc-go with one change that produces the claimed
    behaviour (for X5, entering the retry path on OK). The harness must
    flag each one. If it does not, the corresponding clean result is
    uninformative.

## Five-point screen

1. **Narrow, falsifiable claims.** Met: whether, and after what delay, a
   second attempt reaches the server.
2. **Enforcement boundary.** Met: one function per implementation, cited.
3. **Reachable adversarial states.** Met without fault injection: every
   input is something a legitimate server can send.
4. **Independent oracle.** Met: the server logs every attempt's arrival;
   expected behaviour comes from A6, not from any client. Two clients
   against one server give a cross-implementation comparison.
5. **Conventional baseline.** Met, and thin where it matters.
   - grpc-go `test/retry_test.go`: pushback `-1`, `xxx`, two values, `100`
     then `10`, `1000`, all with `UNAVAILABLE`. No fatal code with
     pushback, no out-of-range value, no OK with pushback.
   - grpc-java `RetriableStreamTest`: pushback tests with retryable codes,
     the X1 case (asserting Java's behaviour), empty and negative pushback,
     hedging. No out-of-range value; no test closes a retriable stream
     with OK at all.
   - Cross-language interop test descriptions and Buf's conformance suite:
     no retry cases.

## Prior art (2026-10-12)

- A6 and its history. No change since `dc9fd4f`.
- grpc-go history: retry fixes are mostly panics and races; semantic ones
  are `03da31ac` (maxAttempts option, v1.65.0), `4c07bca2` (A6 jitter,
  v1.69.0), `f53724da` (service-config validation, v1.70.0). No commit
  mentions pushback.
- grpc-java: PR #11858 (`44e92e2c2`), jitter and flag; no commit message
  mentions retry pushback.
- Web search for X1, X5 and the flag variable: nothing specific found.
- Issue-tracker search for X5 run by Gemini at the operator's request
  (2026-10-12), grpc-java and grpc-go, issues and PRs: queries on `grpc-retry-pushback-ms`,
  trailers-only with retry, `RetriableStream` with OK, and successful
  calls being retried. No report of a successful call being retried, no
  fix restricting it. Nearest items: grpc-java #11244 (retry with
  grpc-servlet on Tomcat), #9641 (fixed by `0f4b76766`, PR #9686, which
  adds `grpc-previous-rpc-attempts` to the initial response metadata;
  commit verified in history), grpc-go #2206 (`ServeHTTP` never sends
  trailers-only responses). The log's result counts are approximate. Of its
  specific citations, only `0f4b76766` was checked against history; the
  issue numbers not referenced by commits are unverified and, coming from
  a model, could be wrong. A manual spot check of #11244 and #2206 is
  needed before the plan cites them.
- **Not done:** gRPC C-core source as a third implementation (optional,
  not required by the question).

## Feasibility and preconditions checked on paper (2026-10-12)

- **X5 precondition 1, trailers-only OK from the test server.** grpc-go's
  native server sends one in this case: `writeStatus`
  (`internal/transport/http2_server.go`, from line 1089, v1.84.0) checks
  whether headers were sent and, if not, puts `:status`, `content-type`
  and the gRPC status in a single end-of-stream HEADERS frame. The
  `ServeHTTP` mode does not (grpc-go #2206), so the test server must use
  the native transport. To be confirmed on the wire at construction.
- **X5 precondition 2** (nothing above `RetriableStream` intercepts the OK
  close) remains for the construction stage.
- **Where runs can happen.** Maven Central is blocked from the sandbox
  (HTTP 403), and building grpc-java from source also needs it. All
  grpc-java runs are operator runs on the operator's machine, as in Case
  Study 3. That machine has Go 1.27.0 and, as of 2026-10-12, no JDK,
  Maven or Gradle; a JDK must be installed first; grpc-go builds can be checked in the sandbox (GitHub clones,
  module hashes verified against the checksum database values recorded
  in `go.sum`).

## Next stage, if approved

A pre-registration plan, committed and pushed before any harness code: the
pins above; X5 as the primary prediction with its falsification rule; the
X1 characterisation and X2 measurements; the statistical criteria for the
timing track; the M-series definitions; the construction-stage checks for
X5's two preconditions; and the stop rule.

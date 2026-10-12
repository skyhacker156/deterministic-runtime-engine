# Case Study 4: gRPC client retries, pre-registration

Pre-registration. Written 2026-10-12, before any harness code exists and
before any gRPC client or server has been run for this study. To be
committed and pushed (branch `cs4-grpc`, created from `origin/main`)
before that code is written. Any later change is a dated amendment,
written before the run it affects.

Source: `CS4_SELECTION_DRAFT.md`, draft 3, committed unchanged beside this
file, SHA-256
`F73830A4AF589E29BB984A9BB444F73DBDAD336575B9EADC4A2C19CAA109D37A`. Where
this plan differs from the draft, the difference is stated in place under
"Corrections to draft 3".

## Label and governance

- CBV (`PHOENIX_VERIFICATION_PROTOCOL.md`) governs. The four-category
  taxonomy line (`FIFTH_CASE_CANDIDATES.md`) does not.
- **Out-of-class probe.** gRPC fails three of the six selection criteria
  (deterministic execution, persistent replayable state, integrity
  artifacts). The result does not count as evidence that CBV transfers
  within its stated class; Case Studies 2 and 3 remain that evidence.
- Two tracks with different rules:
  - **Decision track** (X5, X1, X2): whether a second attempt happens is
    a deterministic function of status, trailers and retry policy. A
    replay rule applies (below).
  - **Timing track** (`G1` control, X3): backoff is random by design.
    Statistical acceptance criteria are fixed below.

## Corrections to draft 3 (source checked 2026-10-12, before this plan)

All draft citations were re-read at the pins below. Two corrections; the
rest matched line for line.

1. **X1 throttle measurement dropped.** The draft proposed measuring the
   throttle effect of X1 as a difference between clients. There is none
   to measure: grpc-go also leaves the throttle uncharged for a fatal
   status (`stream.go` v1.84.0: the code check at 856-859 returns before
   the throttle call at 863), and grpc-java charges it only for a
   retryable code or a negative pushback (`RetriableStream.java` 1075).
   X1 is measured by attempts and final status only. No retry throttling
   is configured in any scenario.
2. **Line citations, grpc-java jitter.** The flag is read at 854-855; the
   jitter formula is at 858-859 (draft: 855 for both).
3. **Date, grpc-go v1.84.0.** The tagged commit is dated 2026-09-17 13:03
   -0700. The draft's 2026-09-18 is not the commit date; what it refers
   to was not checked.

## Targets, pinned (resolved by clone on 2026-10-12)

| Item | Value |
| --- | --- |
| grpc-java (subject) | tag `v1.84.3`, `0ea6d0a6efd2b08cf40fc9b30a89c10f83ad7059` (2026-10-12) |
| grpc-go (subject) | tag `v1.84.0`, `e84aa5ab15d1d2b29d54f838312ad490cb7551a8` |
| grpc-go (timing control) | tag `v1.68.2`, `c982e40790533e2e360bcea963a152b6cfa37b45` (2024-12-18) |
| Specification | gRFC A6, `grpc/proposal` `dc9fd4f` (2024-08-29), last change to `A6-client-retries.md` |
| Test server | grpc-go `v1.84.0`, native transport (`Server.Serve`), plaintext h2c, 127.0.0.1 |
| Toolchain | Go 1.27.0 (operator); JDK vendor and version recorded at install; Gradle wrapper version committed with the harness |

grpc-java is consumed as published artifacts if `1.84.3` exists on Maven
Central (gate C3). grpc-go modules are fetched normally on the operator
machine; any module substituted from a GitHub clone has its `h1:` hash
recomputed and matched against `go.sum` before use.

## Specification passages relied on (A6 at `dc9fd4f`)

- Line 117: a **non-OK** status is checked against `retryableStatusCodes`.
- Line 193: only retryable or non-fatal codes, or a do-not-retry pushback,
  count against the throttle.
- Line 207: pushback is an ASCII signed 32-bit integer; negative or
  unparseable means do not retry.
- Line 209: retry after exactly the pushback delay "and it is appropriate
  to retry the RPC".
- Lines 218-238, five-case summary. Case 1, OK: return success. Case 2,
  fatal status: do not retry. Case 5, pushback: retry in *n* ms.
- State diagram: "failure or pushback: retry" leads to "Check Retry
  Config to Determine if Retry Should be Performed".
- Lines 111-113: backoff is `min(initialBackoff*backoffMultiplier^(n-1),
  maxBackoff) * random(0.8, 1.2)`.
- Lines 256-259: an RPC is committed when Response-Headers are received.

## Enforcement sites (read at the pins)

| | grpc-go v1.84.0 `stream.go` | grpc-java v1.84.3 `RetriableStream.java` |
| --- | --- | --- |
| OK close | `withRetry` 964 returns success before `retryLocked` | `closed()` 908-1058: an uncommitted, processed close reaches `makeRetryDecision` (1006) with no status check; the only `isOk()` is in hedging (1108) |
| Trailers-only | retry considered only if `TrailersOnly()` (827-829) | `NettyClientStream` 343-348 routes end-of-stream headers to `transportTrailersReceived`; `Http2ClientStreamTransportState` 172-186 to `inboundTrailersReceived`, so `headersRead` (commit, 893-904) is not called |
| Code vs pushback | code check 856-859 before anything else | valid pushback sets `shouldRetry` regardless of code (1089-1092) |
| Pushback parse | `strconv.Atoi`, 64-bit (836) | `Integer.valueOf`, failure maps to -1 (1121-1123) |
| Jitter | `0.8 + 0.4*rand.Float64()` (878) | `0.4*random+0.8` if flag, else `random.nextDouble()` (858-859); flag `GRPC_EXPERIMENTAL_XDS_RLS_LB`, default true (854-855) |

grpc-go v1.68.2: same pushback parse and code check (669, 690); backoff
`rand.Int63n(cur)`, uniform on `[0, cur)` (713).

Test server, grpc-go v1.84.0 `internal/transport/http2_server.go`
`writeStatus` (1089-1111): if no headers were sent and `s.header` is
empty, `:status`, `content-type` and the gRPC status go out in one
end-of-stream HEADERS frame. **The handler must therefore set the
pushback with `SetTrailer`, never `SetHeader` or `SendHeader`.**

## Harness (to be built after this plan is pushed)

- One server-streaming method, `cs4.Probe/Run`. A bytes codec may be used
  in place of protobuf. Each request carries a `call_id` and a
  `scenario` name. Attempts are counted by `call_id` at the server, not by
  `grpc-previous-rpc-attempts` (grpc-go reserves that key and is not
  relied on to send it).
- The server logs, per attempt, as JSON lines: `call_id`, scenario,
  attempt number, arrival time from a monotonic clock, and the status and
  trailers it sent. The handler sends no messages in any scenario.
- Each client logs, per call: `call_id`, final status code, elapsed time
  from call start to return.
- Retry policy, set through each client's default service config, no
  `retryThrottling`:
  `{"maxAttempts": 3, "initialBackoff": "0.2s", "maxBackoff": "0.2s",
  "backoffMultiplier": 1, "retryableStatusCodes": ["UNAVAILABLE"]}`,
  except scenario T (`maxAttempts` 5). grpc-java calls `enableRetry()`
  explicitly.
- Deadline 10 s per call, except X2 (2 s).
- Client configurations: `go184` (grpc-go v1.84.0), `go168` (v1.68.2,
  timing only), `java` (grpc-java 1.84.3, default environment),
  `javaNoJitter` (same, `GRPC_EXPERIMENTAL_XDS_RLS_LB=false` set before
  JVM start, timing only), `goMX1` and `goMX5` (planted copies, below).
- All scored runs happen on the operator's machine, one session, both
  languages against the same server binary.

## Scenarios and predictions

The server's response depends on the attempt number *k* for the call.
Outcome tuple per call: (attempts seen at the server, final status at the
client). 20 calls per scenario per configuration.

| ID | Server, attempt 1 | Server, attempt k >= 2 | `go184` predicted | `java` predicted |
| --- | --- | --- | --- | --- |
| S (sanity) | `UNAVAILABLE`, pushback `10` | OK | (2, OK) | (2, OK) |
| **X5** | **OK**, pushback `10` | OK | (1, OK) | **(2, OK)** |
| X1 | `INVALID_ARGUMENT`, pushback `10` | OK | (1, `INVALID_ARGUMENT`) | (2, OK) |

**X5 (primary).** grpc-java makes a second attempt after a successful,
trailers-only response carrying a pushback, so the handler runs twice for
a call that succeeded; grpc-go does not.

**X5 falsification.** If gates C1-C3 pass, S gives (2, OK) on `java`, and
`goMX5` is detected, then 20 of 20 `java` X5 calls at (1, OK) make X5
false. A `go184` X5 call with 2 attempts is reported as a separate,
unpredicted finding against `G0`.

**X1 (characterisation).** Known behaviour, asserted by grpc-java's own
test `throttledStream_FailWithNonRetriableStatusCode_WithRetriablePushback`.
Recorded as a divergence and a specification question, not a defect.

**X2 (secondary).** Server: `UNAVAILABLE` with the pushback below, on
every attempt; deadline 2 s. Elapsed classes: *immediate* below 0.5 s,
*waited* at least 1.8 s, anything else *other*.

| Row | Pushback | `go184` predicted | `java` predicted |
| --- | --- | --- | --- |
| X2-hi | `2147483648` | (1, waited) | (1, immediate, `UNAVAILABLE`) |
| X2-max (calibration) | `2147483647` | (1, waited) | (1, waited) |
| X2-neg (calibration) | `-1` | (1, immediate, `UNAVAILABLE`) | (1, immediate, `UNAVAILABLE`) |

X2 holds if `go184` treats `-hi` like `-max` and `java` treats `-hi` like
`-neg`. Only that difference is claimed. The status at the end of a
waited call is recorded and not scored: grpc-java's behaviour past the
deadline was not examined in source. If either calibration row misses
its prediction for a client, X2 is reported as uninformative for that
client.

**X4 (recorded, not scored).** S with pushback `+5`, then `007`. Attempts
and delay recorded.

## Replay rule (decision track)

All 20 calls in a scenario must give the same outcome tuple, and a full
rerun of the decision track must reproduce every tuple. A difference is
reported as nondeterminism and that scenario counts as uninformative for
that configuration. Timestamps are excluded from the comparison.

## Timing track

Scenario T: `UNAVAILABLE`, no pushback, every attempt; `maxAttempts` 5,
so 4 delays per call; 50 calls, so 200 delays per configuration.
Delay *d* is the server-side difference between consecutive attempt
arrivals for one call; *r* = *d* / 200 ms. Measured *d* is never below
the client's scheduled backoff (the client starts its timer only after
the server's response).

Classification, per configuration:

- **A6 range:** no *r* below 0.80, and at least 95 per cent of *r* at
  most 1.30.
- **Old range:** at least 70 per cent of *r* below 0.80 (uniform on
  `[0, 1)` gives about 80 per cent).
- **Neither:** anything else, reported as such.

| Configuration | Predicted |
| --- | --- |
| `go168` (positive control) | Old range |
| `go184` | A6 range |
| `java` | A6 range |
| `javaNoJitter` (X3) | Old range |

If `go168` is not classed "old range", the timing oracle is invalid and
the whole timing track is reported as uninformative. X3 is recorded as a
coupling between two features sharing one variable, not as a defect.

## Controls

- **Oracle self-test.** The checker classifies a set of synthetic logs,
  one per verdict class in both tracks, before any scored run. Committed
  with the harness.
- **Sanity S** on every configuration in the decision track: the harness
  can see a retry. Not a defect-detection control.
- **Planted-defect controls**, copies of grpc-go v1.84.0 `stream.go`
  with the changes below and nothing else. Run on scenarios X1 and X5
  before any subject run in those scenarios.
  - `goMX1`, line 857:
    `if rp == nil || !rp.RetryableStatusCodes[code] {` becomes
    `if rp == nil || (!rp.RetryableStatusCodes[code] && !hasPushback) {`.
    Must give X1 = (2, OK).
  - `goMX5`: the `goMX1` change, plus line 964:
    `if err == nil || (err == io.EOF && a.transportStream.Status().Code() == codes.OK) {`
    becomes the same condition with
    `&& len(a.transportStream.Trailer()["grpc-retry-pushback-ms"]) == 0`
    added inside the parentheses. Must give X5 = (2, OK).
  - A control that does not give its expected tuple makes the matching
    subject result uninformative until a dated amendment resolves it.
- **X2** has no planted copy; its calibration rows serve that purpose.

## Gates (construction stage, in this order, before any scored run)

- **C1, X5 precondition 1 (wire).** With a logging HTTP/2 frame proxy
  between a grpc-go client and the server, the X5 attempt-1 response must
  be exactly one HEADERS frame with END_STREAM, carrying `:status 200`,
  `grpc-status 0` and `grpc-retry-pushback-ms 10`, and no DATA frame. The
  client for this check runs with retries disabled
  (`grpc.WithDisableRetry()`), so no retry outcome is observed. Failure is
  a precondition failure, not a falsification; it requires an amendment.
- **C2, X5 precondition 2 (source).** Before the first grpc-java run, a
  written trace in `DEV_LOG.md` of every class between the Netty handler
  and `RetriableStream.closed()` for the harness's client configuration
  (no interceptors), stating whether any of them handles an OK close
  first. If one does, X5 is refuted by source reading and the stop rule
  applies.
- **C3, grpc-java artifact identity.** `io.grpc:*:1.84.3` exists on Maven
  Central; the SHA-256 of every grpc jar is recorded; `RetriableStream.java`
  from `grpc-core-1.84.3-sources.jar` is byte-identical to the file at the
  pinned tag. If 1.84.3 is not published, an amendment chooses the
  subject (a published 1.84.x checked the same way, or a source build of
  the tag) before any Java run.
- **C4, module identity.** `go.sum` committed; any substituted module
  checked as stated under "Targets".
- **Hashes before run.** SHA-256 of every harness file written to
  `HASHES_BEFORE_RUN.txt` and committed before the first scored run.

## Development runs

Allowed before the scored runs: the oracle self-test; scenario S on any
configuration; `goMX1` and `goMX5` on any scenario; gate C1. Not allowed:
X5, X1, X2 or T on any subject configuration (`go184`, `go168`, `java`,
`javaNoJitter`). Any accidental subject run is disclosed in
`DEV_LOG.md` with its output, and its scenario is reported as
contaminated.

## Stop rule

- The study stops at the paper stage if X5 is refuted by source reading
  (C2) or by C1, and records why.
- After the scored runs, the result is written up in `CS4_RESULT.md`
  against these predictions. New claims found on the way are recorded,
  not tested, unless a new pre-registration is written for them.

## If X5 holds

Before any claim of a defect, in order:

1. Rerun the decision track; every tuple must reproduce.
2. Reduce to a minimal reproduction and confirm each part is needed.
3. Confirm with grpc-java's in-repo tests or a unit-level reproduction
   against `RetriableStream` that the second attempt originates there.
4. Search the grpc-java issue tracker again for an existing report.
5. Read grpc's security policy and decide the reporting route before any
   write-up beyond this repository. No statement about impact on real
   services is made: the second attempt needs a server that sends a
   pushback with OK, and how often servers do that is not known.

## What this study cannot establish

- Transfer of CBV within its stated class (out-of-class probe).
- Behaviour of gRPC C-core or any other implementation.
- Behaviour under xDS, hedging, retry throttling or `ServeHTTP`.
- Independence of operator: same party as Case Studies 2 and 3.

## Development disclosure

Before this plan, on 2026-10-12: grpc-go (v1.84.0, v1.68.2), grpc-java
(v1.84.3) and `grpc/proposal` were cloned and read at the pins; every
line cited above was read at those pins. grpc-go #2206 ("ServeHTTP never
sends trailers-only responses") and grpc-java #11244 ("Retry does not
work with grpc-servlet in Tomcat", closed) were fetched and match the
draft's descriptions; neither reports a successful call being retried.
Maven Central's index could not be fetched from the sandbox, so whether
1.84.3 is published is unknown (gate C3). The operator machine was
checked for toolchains (Go 1.27.0; no JDK, Maven or Gradle). No harness
code exists; no gRPC client or server was run.

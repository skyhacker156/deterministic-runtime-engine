# Case Study 4: development log

Append-only. Each entry is dated; earlier entries are never edited. Wrong
turns and corrections stay where they happened.

## 2026-10-12

### Pre-registration and amendment 1

- `CS4_PLAN.md` committed as `ca4ccaa` on branch `cs4-grpc` (parent
  `eb2d337`, `origin/main`), pushed. SHA-256
  `A1A0905C3C09675AF61BAB75E4D0F30291D60A7EA02DD87148B5B731B06BFDEB`.
  `CS4_SELECTION_DRAFT.md` (draft 3) committed unchanged beside it, SHA-256
  `F73830A4AF589E29BB984A9BB444F73DBDAD336575B9EADC4A2C19CAA109D37A`.
- Gate C3, first condition, failed on the operator's machine: Maven
  Central lists 1.84.2 as latest (`lastUpdated` 20261008194525); 1.84.3 not
  published.
- `CS4_AMENDMENT_1.md` (Java subject 1.84.2), SHA-256
  `C4408ED165011D135D1CF318D318F0EEFD96FA855C007BDC94F3C44A4EBE3C17`,
  committed as `ae942d8abdbed5acfb4b99b9ffbbf9ae05be7786`, pushed. Operator
  output:
  - `ae942d8abdbed5acfb4b99b9ffbbf9ae05be7786 refs/heads/cs4-grpc`
  - `eb2d33758d27c5a2749a06fd5b30ea0d9568137b refs/heads/main`
- Gate C3 as amended, source check, run on the operator's machine before
  the amendment commit, passed:

| File | SHA-256 | Result |
| --- | --- | --- |
| `grpc-core-1.84.2-sources.jar` | `8D6B44A0FB838DC5C4529A60905D7099158DEE854386624A2E5DF13286C23EEA` | downloaded |
| `grpc-netty-1.84.2-sources.jar` | `06527D5901286641E6686FC355D3589E9892DC5EB70A262A79A096C16598601E` | downloaded |
| `io/grpc/internal/RetriableStream.java` | `1AF4DD76AC33929AA811B854D422C5FF5E4E302DBB31C519F124B815C28CC5EA` | MATCH |
| `io/grpc/internal/Http2ClientStreamTransportState.java` | `EA0C93FBBC06643D20772EB2331E965BAE6400B8282F7354F99FCF56FEC31371` | MATCH |
| `io/grpc/internal/ClientCallImpl.java` | `688A323EE305A296768080E52C75DC45EFF2E7EE292ECDA7747A5729ACB0FE01` | MATCH |
| `io/grpc/netty/NettyClientStream.java` | `5D991EA7B8753F4911F1DCE40F5B22FB1E71BDF46AF2EB6580221DBCFB55425A` | MATCH |

  Binary JAR hashes are still to be recorded at the Java harness build.

### Operator toolchain

- JDK: Eclipse Temurin `21.0.12.1+1` (OpenJDK 21.0.12.1, 2026-08-18 LTS),
  installed with winget, `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot`.
- Go: `go1.27.0 windows/amd64`.

### Go harness development (sandbox)

Environment: Linux sandbox. Go 1.27.0 built from source (`golang/go` tag
`go1.27.0`, `8af21751f066eced273ca3ce49506b366847c623`), because the
sandbox had Go 1.24.7 and grpc v1.84.0 requires Go 1.25. The Go module
proxy and checksum database are blocked here, so dependencies came from
GitHub clones through sandbox-only module files with `replace` lines
(not committed). The committed `go.mod` files carry no such lines; the
operator's `go mod tidy` fetches and verifies every module normally.
Nothing built in the sandbox is used for any scored run.

| Module | Version | Clone |
| --- | --- | --- |
| google.golang.org/grpc | v1.84.0 / v1.68.2 | `e84aa5ab` / `c982e407` |
| golang.org/x/net | v0.57.0 / v0.29.0 | `b8f09f6f062c` / `35b4abaed97f` |
| golang.org/x/sys | v0.47.0 / v0.25.0 | `9e7e939dcafa` / `a43b625d3c32` |
| golang.org/x/text | v0.40.0 / v0.18.0 | `724af9c35838` / `1e3e9fdab19c` |
| google.golang.org/protobuf | v1.36.11 / v1.34.2 | `96a179180f0a` / `c33baa8f3a0d` |
| google.golang.org/genproto/googleapis/rpc | `f0a921348800` / `8af14fe29dc1` | commit times match the pseudo-versions |

Results:

1. **Oracle self-test** (`go test ./internal/oracle`): 8 test groups
   pass. As a check that it can fail, four defects were planted one at a
   time in a scratch copy of the oracle (Java X5 prediction flipped; A6
   rule allowing two delays below 0.80; C1 ignoring END_STREAM;
   nondeterminism check weakened). The self-test failed on each. The
   committed oracle files were not touched.
2. **Builds.** All five commands compile against grpc v1.84.0; the client
   and every other package compile against v1.68.2; `go vet` and `gofmt`
   clean.
3. **Planted copies.** `mkmutant` was run on a stand-in for the module
   cache (`git archive v1.84.0`). First attempt failed: the stand-in held
   symlinks under `security/advancedtls`, a nested module that is not part
   of grpc's module zip. The stand-in was wrong, not the tool; it was
   trimmed of nested modules as a module zip is. `mkmutant` was also
   changed to delete its partial output when a copy fails. Second attempt:
   1082 files copied per variant; `stream.go` before
   `68AA9293B8023D550C730D391482DC08B2572526B8629904F1DDE457BF042C4D`,
   after `39275DA00C9ADA4830464829EF09DBF3FBB94E37A0DB89186CBD46C5DFEC4095`
   (mx1) and `1E1E44818BF1C739BD063BCCF40B2547D64BDD155183918AB669FE6A16F74D44`
   (mx5). `diff -r` against the stand-in: only line 857 (mx1), only lines
   857 and 964 (mx5).
4. **Development runs** (all allowed by the plan; none on a subject
   configuration in X5, X1, X2 or T):
   - Client label check refused three mismatched builds (exit 2 each).
   - `goMX1` S: 2,OK x20, MATCH. `goMX1` X1: 2,OK x20, MATCH.
   - `goMX5` S: 2,OK x20, MATCH. `goMX5` X5: 2,OK x20, MATCH.
   - Orphan and mislabeled server attempts: 0.
5. **C1 dry run** (not gate C1; that runs on the operator's machine with
   the unmodified `go184` client). Through `frameproxy`, `goMX5` with
   retries disabled:
   - X5 attempt 1: one HEADERS frame on stream 1, END_STREAM and
     END_HEADERS, fields `:status 200`, `content-type
     application/grpc+cs4raw`, `grpc-status 0`, `grpc-message ""`,
     `grpc-retry-pushback-ms 10`; no DATA. C1 rule: PASS.
   - S attempt 1 (negative control): same shape with `grpc-status 14`.
     C1 rule: FAIL, for that reason only.
6. **Observation, informational.** grpc-go v1.84.0 sent
   `grpc-previous-rpc-attempts: 1` on its retry in S. The plan does not
   use this header.

Open before any Java run: Java client, gate C2 trace, binary JAR hashes.

### Go harness install on the operator's machine, first attempt (failed, nothing committed)

- Zip `E279DACD...759B` and all 17 files matched the manifest; files copied
  onto `cs4-grpc` at `ae942d8`.
- `go mod tidy` fetched grpc v1.84.0 and its dependencies through the Go
  module proxy (checksums verified by the go command); tools and the
  `go184` client built.
- **Planted copies on the real module cache**
  (`C:\Users\gosur\go\pkg\mod\google.golang.org\grpc@v1.84.0`): 1082 files
  each, `stream.go` hashes identical to the sandbox values (mx1
  `39275DA0...4095`, mx5 `1E1E4481...4D44`, source `68AA9293...2C4D`). This
  confirms the trimmed sandbox stand-in matched the real module.
- `go mod tidy` with each alternate module file passed.
- **Failure:** `go build -modfile=go168.mod ...` stopped with
  `go: -modfile=go168: file does not have .mod extension`. Windows
  PowerShell 5.1 splits an unquoted argument that starts with `-` at the
  `.`; the tidy step passed only because its argument was quoted. Fix:
  every `-modfile=` argument quoted, in the install script and in
  `harness/go/README.md`. The script stopped before any commit.

### Go harness install, second attempt (resume script, stopped before any change)

- The resume script's state check required the four module files to match
  their delivered hashes. `go mod tidy` adds `// indirect` lines to them by
  design, so that check could never pass: an error in the check, not in
  the files. The script stopped before replacing or building anything.
  The check was changed to require every delivered line (module, `go`,
  direct requirements, `replace`) to be present after tidy, and to print
  all four files.

### Go harness install, third attempt: committed `ed57edf`

- All delivered lines present after tidy. Each module file gained only one
  `// indirect` block: x/sys, x/text, genproto rpc and protobuf at the
  versions grpc v1.84.0 (or v1.68.2) requires.
- Oracle self-test passed on the operator's machine (Go 1.27.0, Windows).
- Commit `ed57edf2992d0c421e76318a9e60015f43b4ea12` on `cs4-grpc`, pushed.
  Checked from a clone: the 13 delivered non-module files match their
  hashes; every dependency checksum in `go.sum`, `go168.sum`, `gomx1.sum`
  and `gomx5.sum` equals the one grpc-go's own `go.sum` records for the
  same version (0 disagreements). Only grpc's own lines are not in grpc-go's
  `go.sum`; the go command verified those against the checksum database.
- Binaries built on the operator's machine (SHA-256):

| Binary | SHA-256 |
| --- | --- |
| `checker.exe` | `5460661EAFB082EA786D37C4378D134F18FABE8D5BE5370D43E2C35428CF43C7` |
| `client168.exe` | `7192D51F01DC6DB68CF33CFE463BB43BD3D44A8DEBD6F86EAB0038C1CC73EBE0` |
| `client184.exe` | `5F21D5F5410A001E1957466872ED60B003C5A33A9CAD5D71F2EDE23A0B71C116` |
| `clientmx1.exe` | `9500B3BC40137F673F8E470D8B9553BAE18EA7D5B6B0B814FFA4CF775DA581F8` |
| `clientmx5.exe` | `7DE1E93B029E18B9594B1EB6F30983E2B749C448D1FC8FEA3CA88E9F846CC0A7` |
| `frameproxy.exe` | `9928CAD837D8D1BDF4722D20D0FE8445FA0BC84D8CDEE8A4D979EEDFCB217BA7` |
| `mkmutant.exe` | `BD82C25EFED8BFF6A2F3DCC373291C0892370C515CC7BE5D7761316571DFE31E` |
| `server.exe` | `43230BC88B64F3260A75ED3239607191EFB07AA5F797C65BB1241CF79A78781C` |

### Operator development runs and gate C1: committed `d26d293`

- First script run: the five client runs completed (100 calls), then the
  script stopped. Cause: its `Start-Bg` helper both printed a status line
  and returned the process, so PowerShell returned both and `Stop-Bg`
  called `WaitForExit` on the text. The server had already been given its
  stop. Nothing was committed.
- A continue script reused the completed run data after checking branch,
  HEAD, binary hashes, that no harness server or proxy was still running,
  and that the results folder held exactly the eight files the client runs
  create. A draft of that script also required exactly 200 attempt lines,
  which assumes the outcome (two attempts per call); it was removed before
  delivery and the count printed instead (it was 200).
- Development runs, checker verdicts (server `server_dev.jsonl`):

| Configuration | Scenario | Calls | Predicted | Observed | Verdict |
| --- | --- | --- | --- | --- | --- |
| go184 | S | 20 | 2,OK | 2,OK x20 | MATCH |
| goMX1 | S | 20 | 2,OK | 2,OK x20 | MATCH |
| goMX1 | X1 | 20 | 2,OK | 2,OK x20 | MATCH |
| goMX5 | S | 20 | 2,OK | 2,OK x20 | MATCH |
| goMX5 | X5 | 20 | 2,OK | 2,OK x20 | MATCH |

  Orphan and mislabeled attempts: 0. Gap from attempt 1 to attempt 2
  (pushback 10 ms), server clock: 10.11 to 11.33 ms across all five runs.
  grpc-go sent `grpc-previous-rpc-attempts: 1` on every retry.
  The planted-defect controls for X1 and X5 are therefore detected on the
  operator's machine; the sanity check passes for `go184`.
- **Gate C1: PASS.** `go184` (unmodified grpc v1.84.0), retries disabled,
  through `frameproxy`, separate server log `server_c1.jsonl` (one attempt
  per call, not analysed as a run). X5 attempt 1 reached the client as one
  HEADERS frame on stream 1 with END_STREAM and END_HEADERS: `:status 200`,
  `content-type application/grpc+cs4raw`, `grpc-status 0`,
  `grpc-message ""`, `grpc-retry-pushback-ms 10`; no DATA. X5 precondition 1
  holds on the wire.
- C1 negative control: S attempt 1 through the same path failed the rule
  for one reason only, `grpc-status = "14", want "0"`.
- Results: `case_study_4_grpc/results/dev_20261012_op/`, 24 files listed
  in `SHA256SUMS.txt`; all 24 re-checked from a clone after the push.
- Commit `d26d293c583c4e268a9b7e25802927e8c7f80882` on `cs4-grpc`, pushed.

Still open before any Java run: Java client, gate C2 trace, binary JAR
hashes. No scored run has been made.

### Gate C2: source trace, grpc-java 1.84.2 (written before any Java run)

Question (plan, gate C2): does any class between the Netty handler and
`RetriableStream`'s `Sublistener.closed()` handle an OK close first, for
the harness's client configuration? Configuration: `grpc-netty` 1.84.2
(unshaded), plaintext, retry enabled, default service config with a retry
policy for `cs4.Probe` and no `retryThrottling` or hedging policy, no
client interceptors, no call credentials.

Source: tag `v1.84.2`, `1d2977b0cff51be8da111c8449cb03c0e0b10995`,
`git archive` of `api`, `core`, `netty`, `util`, `stub`. The extracted
`RetriableStream.java` hashes to
`1AF4DD76AC33929AA811B854D422C5FF5E4E302DBB31C519F124B815C28CC5EA`, the
value gate C3 matched in the published sources JAR. Line numbers are at
that tag.

Inbound path of a trailers-only response (one HEADERS frame, END_STREAM):

1. `NettyClientHandler` `FrameListener.onHeadersRead` (1079-1088) calls
   `onHeadersRead(streamId, headers, endStream)` (419-452). Only a header
   size over the soft limit reports a status here (429-445,
   RESOURCE_EXHAUSTED); otherwise `stream.transportHeadersReceived` (446).
2. `NettyClientStream.TransportState.transportHeadersReceived` (343-352):
   with `endOfStream`, queues a `CancelClientStreamCommand` with a null
   reason if the outbound side is still open (345-346), then calls
   `transportTrailersReceived` (348). The headers path (350) is not
   taken, so `headersRead` is never called and the attempt is not
   committed. `cancelStream` with a null reason only writes RST_STREAM and
   reports no status (`NettyClientHandler` 815-831, 821-824).
3. `Http2ClientStreamTransportState.transportTrailersReceived` (172-188):
   with no headers received, `validateInitialMetadata` (219-233) checks
   only that `:status` is present and the content type is gRPC; no check of
   the gRPC status. Then `statusFromTrailers` (193) and
   `inboundTrailersReceived` (186).
4. `AbstractClientStream.TransportState.inboundTrailersReceived`
   (377-387) calls `transportReportStatus(status, false, trailers)`, which
   uses `RpcProgress.PROCESSED` (401-404). In 421-449, `status.isOk()` is
   stored (433) and used only by `deframerClosed` for a partial message
   (274), which cannot occur with no DATA. `closeListener` (456-466) uses
   `isOk()` only for stats and the transport tracer (460-462), then calls
   `listener().closed(status, PROCESSED, trailers)` (464).
5. Listener wrappers between the transport stream and `RetriableStream`
   (all `ClientStreamListener` implementations in api, core, netty, util,
   stub were listed; util and stub have none):
   - `InternalSubchannel` call-tracing transport (775-798): its
     `closed` (790-795) records `status.isOk()` in `callTracer`, then
     forwards the same arguments.
   - `DelayedStream.DelayedStreamListener.closed` (513-523): queues or
     runs `realListener.closed` with the same arguments.
   - `ForwardingClientStreamListener.closed` (33-35): forwards.
   `ClientCallImpl` and any client interceptors sit above `RetriableStream`
   (its master listener) and see the close only after the retry decision.
6. `ManagedChannelImpl.ChannelStreamProvider.newStream` (474-539): with
   retry enabled (builder default `true`, `ManagedChannelImplBuilder` 198;
   the harness also calls `enableRetry()`), every call is a `RetryStream`
   whose attempts come from `delayedTransport.newStream` (530); the
   retry policy comes from the call's `MethodInfo` (492-494).
7. `RetriableStream.Sublistener.closed` (908-1058): not cancelled (916),
   no buffer overflow (933), not MISCARRIED (940), uncommitted (951), not
   transparent-retry progress (952-983), no hedging (987), so
   `makeRetryDecision(status, trailers)` (1006) runs with no status check
   (1065-1097). Commit points in the class, all checked: `headersRead`
   (893, not called, step 2); `closed` (934, 942, 1054); `cancel` (529;
   the harness cancels nothing, deadline 10 s); `outboundWireSize` buffer
   limits (1412-1450; default 1 MiB per RPC and 16 MiB per channel,
   `ManagedChannelImplBuilder` 120-121, request about 100 bytes);
   `messagesAvailable` requires a prior commit (1130-1145), and no message
   arrives.

**C2 result: PASS.** No class on the path handles an OK close before the
retry decision. X5 is not refuted by source reading; the stop rule does
not apply.

What C2 does not establish: that the default service config's retry
policy reaches the call's `MethodInfo` (the Java sanity run S shows this:
2,OK means the policy is applied), and anything about runtime behaviour.

### Java client: committed `8f0d6b2`

- Gradle 8.14.3 wrapper generated in the sandbox (`--no-validate-url`,
  since the sandbox cannot reach gradle.org; `validateDistributionUrl` set
  back to `true` before delivery). On the operator's machine the delivered
  `gradle-wrapper.jar` matched Gradle's published hash
  (`7D3A4AC4DE1C32B59BC6A4EB8ECB8E612CCD0CF1AE1E99F66902DA64DF296172`) and
  `distributionSha256Sum=bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531`
  was pinned from Gradle's published value.
- Sandbox compile check: `Client.java` compiled with no errors or
  `-Xlint:all` warnings against grpc-api 1.84.2 built from source
  (`api/src/main` and `api/src/context`). It could not run in the sandbox
  (no Netty).
- Operator build: `dependencies --write-locks`, then
  `--write-verification-metadata sha256 installDist`, then a verifying
  `installDist`, which reported its tasks up to date; whether that build
  re-checked the artifacts was not shown in its output.
  `gradle.lockfile`: grpc 1.84.2, Netty 4.2.16.Final. 29 runtime JARs.
- **Gate C3, binary half (amendment 1, "record the SHA-256 of every grpc
  binary JAR"):** the five grpc JARs in `verification-metadata.xml` equal
  the hashes the build printed (checked from a clone):

| JAR | SHA-256 |
| --- | --- |
| `grpc-api-1.84.2.jar` | `457897231C31FDAE557D853F58739F35D3C752373115B523913026631882A82B` |
| `grpc-context-1.84.2.jar` | `964BAF971597969A5B8E134B3FE9ECF22FD5BCB0520DF8BBACD704AD34026B59` |
| `grpc-core-1.84.2.jar` | `1308DF2B6CB572549002C9DD31BE0FEC8E4E9FAAF6F6F2D8C3EE0D790C4D47E3` |
| `grpc-netty-1.84.2.jar` | `C98709AACF61D762C945B2E2B2FC2A849D3F7467E269EA133EF90F2250BCB3DF` |
| `grpc-util-1.84.2.jar` | `D7521C1973ACC173DD569A3D8B466DACC3C56E0D671DAC28C84CCDE594C22059` |

- Runtime checks, no calls (`-check`): `java`: grpc 1.84.2,
  `io.grpc.netty.NettyChannelBuilder`, variable unset, jitter flag `true`,
  `RetriableStream` loaded from `grpc-core-1.84.2.jar` (`1308DF2B...`).
  `javaNoJitter` with the variable `false`: jitter flag `false`, same JAR.
  `javaNoJitter` without the variable: refused, exit 2.

### Java development run, scenario S: committed `c7aab89`

- `java` S, 20 calls: 2,OK x20, MATCH. Orphan and mislabeled attempts 0.
  The default service config's retry policy reaches the Java call (the
  point gate C2 left open). `javaNoJitter` was not run on S: the plan uses
  it for the timing track only and the checker has no S prediction for it.
- grpc-java also sent `grpc-previous-rpc-attempts: 1` on each retry.
- **Finding 1, first-call latency.** Client elapsed, `java` S calls 0-19
  (ms): 608.4, 59.0, then 19.8 to 32.3. `go184` S: 10.5 to 14.4, call 0
  14.4. The plan's *immediate* class for X2 is below 500 ms, so Java's call
  0 would probably class as *other* in X2HI and X2NEG.
- **Finding 2, late Java retries.** Server gap attempt 1 to attempt 2,
  pushback 10 ms: `java` 16.3 to 40.2 ms (median 27.4); Go 10.1 to 11.3 ms.
  Cause not established (consistent with about 15.6 ms timer granularity on
  Windows). On the timing track's 200 ms base, up to 30 ms adds up to 0.15
  to *r*, against a 0.10 margin between A6's 1.20 and the pre-registered
  1.30 bound.
- **Decision (operator, 2026-10-12):** both changes, as
  `CS4_AMENDMENT_2.md`: a Java warm-up call to the unregistered method
  `cs4.Probe/Warmup`, and the A6 upper bound raised from 1.30 to 1.40 for
  every configuration. Made from S data only, before any X2 or T data
  exists for any subject configuration.

### Amendment 2 applied (this commit)

- `internal/oracle/oracle.go`: `RHigh` 1.40; report field
  `frac_r_at_most_1_40`; checker column `atmost1.40`. Self-test passes; it
  now includes r = 1.35 (A6 under 1.40, not under 1.30) and pins `RHigh`.
  With `RHigh` reverted to 1.30 in a scratch copy the self-test fails.
- `harness/java/src/main/java/cs4/Client.java`: warm-up call before the
  measured calls (same `call` code, method `cs4.Probe/Warmup`, must end
  `UNIMPLEMENTED`, not logged). Compiles with no `-Xlint:all` warnings
  against grpc-api 1.84.2 source. grpc-go v1.84.0 answers an unknown method
  of a known service with `UNIMPLEMENTED` without invoking a handler
  (`server.go` 1592-1614), and the CS4 server sets no unknown-service
  handler.
- Rebuilt: `checker.exe` and the Java client. Server, Go clients and
  `frameproxy.exe` are not rebuilt (`frameproxy.exe` keeps its C1 hash;
  its source now compiles against the amended oracle package, whose `Frame`
  type and C1 rule are unchanged).

### Amendment 2 committed `fb14d33`; second Java development run `55ccde4`

- Commit 1 of the apply script: `fb14d33` (amendment, checker 1.40 bound,
  Java warm-up, this log's previous entry), pushed before the warm-up was
  used. Checked from a clone: all 7 delivered files match.
- `checker.exe` rebuilt on the operator's machine:
  `0DD2C6A93E9EE36C2E1A81ED88F80F9017D2C398488882D8BA17355FC6960D25`. The
  other seven Go binaries were confirmed unchanged. Oracle self-test passed.
- Java client rebuilt under dependency verification (tasks executed this
  time); `-check` for `java` as before.
- Second `java` S run (run tag `d4`), with the warm-up: warm-up
  `UNIMPLEMENTED` in 574.9 ms, not logged. Measured calls 0-19, client
  elapsed (ms): 20.7, 46, 34.9, 29.4, 30.1, 47, 27.2, 30.5, 15.6, 15.8,
  32.2, 31.9, 30, 30.4, 29.9, 30.5, 31.5, 32.2, 28.8, 31.4. Call 0 is no
  longer above 500 ms (amendment 2, "Check": satisfied). 2,OK x20, MATCH;
  orphan and mislabeled attempts 0; server log 40 lines, all scenario S,
  no warm-up call ID. Retry gap 12.7 to 30.9 ms (median 26.9): finding 2
  persists, as expected.

### Preflight audit before the scored session

- Requested by the operator's review (2026-10-12): freeze inputs, verify
  the scored script and the checker against the plan, keep the tracks
  apart, fix the meaning of each result before the run.
  `PREFLIGHT_AUDIT.md` covers the five points.
- `harness/run_scored.ps1` written as a repository file so that it is
  frozen and hashed with everything else. One defect found by reading
  before any run: client console output would have mixed with
  `Run-Client`'s return value (the `Start-Bg` class of error); fixed with
  `Out-Host`.
- PowerShell 7.4.6 installed in the sandbox from the PowerShell GitHub
  release. A first dry-run attempt failed because my translation of the
  script for Linux replaced every backslash, including the `\s` in a
  regular expression; the translation was redone to change only the six
  path lines and the repository path. Dry-run results (normal, abort,
  three refusals) are in `PREFLIGHT_AUDIT.md`, section 2.
- `HASHES_BEFORE_RUN.txt` is generated on the operator's machine in the
  same commit as this entry.

### Freeze `47ff80a` and scored session `764722a`

- Freeze checked from a clone before the run: 37 of 76
  `HASHES_BEFORE_RUN.txt` entries are files in the commit, all matching;
  of the 39 operator-only entries, 8 binaries and 2 `stream.go` files
  match their independently recorded hashes, 28 of 29 JARs match the Gradle
  verification metadata, and `cs4client.jar` (the client's own build) has
  no outside record.
- Scored session `scored_20261012_190314` (19:03:14 to 19:10:15 UTC):
  preflight verified 76 hashes at `47ff80a`; 44 client steps, no failure;
  replay IDENTICAL; committed `764722a`. Every predicted row MATCH in r1
  and r2.
- Verified from a clone of `764722a`: 59 files re-hash; every row
  recomputed from the raw logs by a separate script that does not use the
  checker, with the same results.
- Reporting policy checked (for `CS4_RESULT.md` section 5): grpc-java
  `SECURITY.md` refers to `grpc/proposal` `P4-grpc-cve-process.md`
  (`2d6aff2`, 2023-06-09): private reports to grpc-security@googlegroups.com
  for suspected vulnerabilities, including when unsure; not for issues that
  are not security related.
- `CS4_RESULT.md` written. One correction before delivery: a draft listed
  A6's state diagram as support for a violation; its edge "failure or
  pushback: retry" does not exclude an OK response with pushback, so it was
  moved to the other side of the contract question.

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

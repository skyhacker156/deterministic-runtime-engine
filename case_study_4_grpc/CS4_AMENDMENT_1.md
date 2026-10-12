# Case Study 4, amendment 1: grpc-java subject version

Dated amendment, written 2026-10-12, after the pre-registration
(`CS4_PLAN.md`, commit `ca4ccaa`, SHA-256
`A1A0905C3C09675AF61BAB75E4D0F30291D60A7EA02DD87148B5B731B06BFDEB`) and
before any harness code exists and before any Java run. The plan is not
edited; it stays as committed. Where this amendment and the plan differ,
this amendment governs from its commit onward.

## Trigger

Gate C3, first condition, failed on the operator's machine on
2026-10-12: Maven Central's `io/grpc/grpc-core/maven-metadata.xml` lists
`1.84.2` as latest and release (`lastUpdated` 20261008194525); `1.84.3` is
not published. The plan requires an amendment choosing the Java subject
before any Java run.

## Change

| | Plan | This amendment |
| --- | --- | --- |
| Java subject | tag `v1.84.3`, `0ea6d0a6efd2b08cf40fc9b30a89c10f83ad7059` | `io.grpc:*:1.84.2` from Maven Central; tag `v1.84.2`, `1d2977b0cff51be8da111c8449cb03c0e0b10995` (2026-10-08) |
| Java transport artifact | not specified | `io.grpc:grpc-netty:1.84.2` (unshaded), so its sources JAR can be checked; with `grpc-api`, `grpc-core`, `grpc-stub` at 1.84.2 |

Nothing else changes: the questions, predictions (X5, X1, X2, X4), the
timing track and its criteria, the controls, the gates, the development
run rules and the stop rule are as in the plan. Every grpc-java line
number cited in the plan applies unchanged, because the cited files are
byte-identical at both tags (below).

## Basis: comparison of the two tags (sandbox, 2026-10-12)

`v1.84.3` is one commit, "Bump version to 1.84.3", on a line that differs
from `v1.84.2`. Outside `examples/`, `README.md` and build files, three
source files under `core/`, `netty/` and `api/` differ:

1. `core/.../internal/GrpcUtil.java`: `IMPLEMENTATION_VERSION` string only.
2. `core/.../internal/MessageDeframer.java`: 1.84.2 returns a
   `LazyDecompressingInputStream` from `getCompressedBody()` (433-441 at
   1.84.2); 1.84.3 removes it. `getCompressedBody()` runs only for a
   compressed message frame. No scenario sends a message (the server
   handler sends none) and no compression is configured, so this code is
   not reached.
3. `core/.../internal/ServerCallImpl.java`: server-side request handling.
   The test server is grpc-go, so this code is not executed.

Files on the measured client path, identical at both tags (full SHA-256
of the file at tag `v1.84.2`, as checked out with LF line endings):

| File | SHA-256 |
| --- | --- |
| `core/src/main/java/io/grpc/internal/RetriableStream.java` | `1AF4DD76AC33929AA811B854D422C5FF5E4E302DBB31C519F124B815C28CC5EA` |
| `core/src/main/java/io/grpc/internal/Http2ClientStreamTransportState.java` | `EA0C93FBBC06643D20772EB2331E965BAE6400B8282F7354F99FCF56FEC31371` |
| `core/src/main/java/io/grpc/internal/ClientCallImpl.java` | `688A323EE305A296768080E52C75DC45EFF2E7EE292ECDA7747A5729ACB0FE01` |
| `netty/src/main/java/io/grpc/netty/NettyClientStream.java` | `5D991EA7B8753F4911F1DCE40F5B22FB1E71BDF46AF2EB6580221DBCFB55425A` |

`ManagedChannelServiceConfig.java`, `RetryPolicy.java` and
`NettyClientHandler.java` were also compared and are identical.

## Gate C3, as amended

Before this amendment is committed, and again before any Java run if the
dependency cache changes:

- Download `grpc-core-1.84.2-sources.jar` and
  `grpc-netty-1.84.2-sources.jar` from Maven Central. Extract the four
  files above. Each must match its SHA-256 in the table. These are
  expected values, verified on the operator's machine, not assumed.
- At harness build, record the SHA-256 of every grpc binary JAR resolved
  (Gradle dependency verification metadata, committed with the harness).

**Decision rule.** If any extracted file does not match, or the
difference review above is found wrong, the study pauses and the subject
is reconsidered in a further amendment. It does not move to another
version quietly.

## Limits of this substitution

- Identical source on the retry path does not establish that the whole
  runtime behaves identically; the three differing files are argued
  unreachable above, not tested.
- A matching sources JAR does not prove the published binary was built
  from it. The binary JAR hashes are recorded so the exact artifact is
  reproducible, but that link is not verified here.
- Results are reported as grpc-java 1.84.2. Statements about 1.84.3 rest
  on the comparison above.

## Record

The commit hash of this amendment and the push confirmation (`git log`
and `git ls-remote` output) are recorded in `DEV_LOG.md` when that file
is created with the harness, before any scored run.

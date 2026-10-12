# CS4 Java client

grpc-java 1.84.2 client for Case Study 4 (`../../CS4_PLAN.md`,
`../../CS4_AMENDMENT_1.md`). Same request body, retry policy and log format
as the Go client in `../go`. Gradle 8.14.3 through the wrapper; JDK 21.

- `gradle.lockfile` pins every dependency version.
- `gradle/verification-metadata.xml` pins the SHA-256 of every artifact;
  a build fails if a downloaded JAR differs.
- `gradle/wrapper/gradle-wrapper.properties` pins the Gradle distribution
  by `distributionSha256Sum`.

Build:

```powershell
.\gradlew.bat --no-daemon installDist
```

Labels (`-client`), checked at startup against the runtime:

| Label | `GRPC_EXPERIMENTAL_XDS_RLS_LB` | Jitter flag in `RetriableStream` |
| --- | --- | --- |
| `java` | unset | `true` |
| `javaNoJitter` | `false` | `false` |

The client also refuses to run unless grpc is 1.84.2, the channel builder
is `io.grpc.netty.NettyChannelBuilder`, and the system property of the same
name is unset.

Check without making a call, then run (the log file must not already exist):

```powershell
java -cp "build\install\cs4client\lib\*" cs4.Client -client java -check
java -cp "build\install\cs4client\lib\*" cs4.Client -client java -scenario S -n 20 -run r1 -out java_S.jsonl
```

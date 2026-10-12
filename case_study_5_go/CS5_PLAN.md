# Case Study 5: Go reproducible toolchains, selection and pre-registration

Written 2026-10-12, before any toolchain has been built for this study and
before any built archive has been compared with a published hash. To be
committed and pushed (branch `cs5-go`, from `origin/main`) before any build
below runs. Any later change is a dated amendment, written before the run
it affects. Selection and pre-registration are combined in one document to
fit a single evening's session; this is a departure from Case Study 4's
separate draft and plan.

## Selection

CBV (`PHOENIX_VERIFICATION_PROTOCOL.md`) governs. The four-category
taxonomy line (`FIFTH_CASE_STUDY_PROTOCOL.md`) is separate and does not.

Against the six selection criteria:

| Criterion | Go toolchain build |
| --- | --- |
| Deterministic execution | A compiler and linker: a function from source to bits |
| Persistent, replayable state | A rebuild from the same source is the replay |
| Integrity artifacts | SHA-256 of every published archive; go.dev/rebuild report |
| Stated claims | The Go Blog, "Perfectly Reproducible, Verified Go Toolchains", Russ Cox, 2023-08-28 |
| Real seams | Host OS, bootstrap compiler, build path, environment variables |
| Different philosophy | Deterministic *transformation* (vs FoundationDB's simulation, raft's protocol, Phoenix's replay) |

This is an **in-class** study, unlike Case Study 4.

Candidates considered on 2026-10-12 and not selected: the Linux OOM
killer's `memory.oom.group` (out of class; the kernel's own self-tests in
`tools/testing/selftests/cgroup/test_memcontrol.c` cover the documented
claim and its `-1000` exception; no usable memory controller in the
sandbox); curl multi-member gzip (issue #22156 resolved upstream by
`df350dd`, 2026-06-29, as a deliberate clear error, shipped in 8.22.0);
SQLite deferred foreign keys (kept for a later discovery-oriented screen).

## Claims (quoted from the blog post)

- C1. "Go 1.21.0 is the first Go toolchain with perfectly reproducible builds."
- C2. "its only relevant input is the source code for that build." Host
  platforms and bootstrap compilers: "None of that changes the toolchains
  that are built."
- C3. Release builds on Linux and Windows: "The two systems must produce
  bit-for-bit identical archives or else we do not proceed with the
  release."
- C4. For user programs: "a reproducible build is as simple as compiling
  with `CGO_ENABLED=0 go build -trimpath`." (Not tested tonight.)

## What the official verifier does (read before this plan)

`golang.org/x/build/cmd/gorebuild`, `golang/build` `ea616ad` (2026-10-10):

- Source: the git tree at `refs/tags/<version>` as a tarball from
  go.googlesource.com (`report.go` 219); no `.git` directory.
- Bootstrap for go1.27.x: `go1.24` (`build.go` 20-44).
- Build: fresh unpack per target, `make.bash -distpack` with only `GOOS`
  and `GOARCH` set (`report.go` 334-343), and about twenty variables
  **cleared** because they "would leak into defaults in the toolchain and
  change the generated binaries": `CC`, `CGO_ENABLED`, `GOAMD64`,
  `GOEXPERIMENT`, `GO_GCFLAGS`, `GO_LDFLAGS` and others (`build.go`
  152-176).
- Comparison: byte equality with the posted archive (`report.go` 373);
  darwin only falls back to comparing after stripping signatures.

So the verifier itself treats a set of environment variables as inputs.
That is the boundary C2 states without: tested as B1 below.

## Prior art

- go.dev/rebuild, run 2026-08-26 00:02-01:58 UTC: go1.27.0
  `windows-amd64.zip` PASS (hash prefix `f0c0a0d33ba94f4d`), `.msi` PASS
  (contents against the zip), `linux-amd64.tar.gz` PASS (`675c26c449cbb18f`),
  `src.tar.gz` PASS (`7002403d7cc44529`). That is Go's own verifier on Go's
  own infrastructure (Ubuntu); this study is an independent check.
- Published SHA-256 (go.dev/dl, JSON index), read through a fetch tool, so
  treated as expected values to be confirmed by an independent download
  (W1):
  - `go1.27.0.windows-amd64.zip`: `f0c0a0d33ba94f4d2c5dbc887334ce678b21813504ddb3aafcb06e60a5a667c4`
  - `go1.27.0.linux-amd64.tar.gz`: `675c26c449cbb18fc24b74650de1eabbae6e16f64326fd85a283fb3b58280685`
  - `go1.27.0.src.tar.gz`: `7002403d7cc44529ef6d26f69a44818263395ead7c16c05a5808ae047ebeb0e5`
  The rebuild report's prefixes agree with these.

## Inputs, pinned

| Item | Value |
| --- | --- |
| Source | `golang/go` tag `go1.27.0`, commit `8af21751f066eced273ca3ce49506b366847c623` (GitHub mirror), exported with `git archive` (no `.git`); `VERSION` = `go1.27.0` / `time 2026-08-18T21:24:23Z` |
| Bootstrap A | official `go1.24.7 linux/amd64` (`/usr/local/go` in the sandbox) |
| Bootstrap B | the sandbox's `go1.27.0 linux/amd64`, built from source with bootstrap A on 2026-10-12 (for Case Study 4) |
| Build host | sandbox: Linux 6.18 x86-64, 2 CPUs; host C compiler `gcc` 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1) present |
| Environment | as gorebuild: the cleared list set to empty, `GOTOOLCHAIN=local`, `GOROOT_BOOTSTRAP` set; then only the variables a run names |

## Runs and predictions

Each run: fresh `git archive` export into a new directory, then
`./make.bash -distpack` in `src/` with the run's settings; the produced
`pkg/distpack/go1.27.0.<os>-<arch>.{zip,tar.gz}` is hashed with
`sha256sum` (not with Go) and compared with the published hash.

| Run | Target | Bootstrap | Variation | Predicted |
| --- | --- | --- | --- | --- |
| G1 | windows/amd64 | A | none | identical to `f0c0a0d3...a667c4` |
| G2 | windows/amd64 | B | different bootstrap major version | identical |
| G3 | linux/amd64 | A | none | identical to `675c26c4...80685` |
| G4 | windows/amd64 | A | export under a different, longer path with a space | identical |
| B1 | windows/amd64 | A | `GOAMD64=v3` left set | **differs** (verifier clears it) |
| B2 | linux/amd64 | A | `CGO_ENABLED=1` left set, host C compiler present | **differs** |
| K | windows/amd64 | A | one byte changed in a comment of `src/fmt/print.go` | **differs** (source is the input) |

K is the sensitivity control: it shows the comparison can see a change.
B1 and B2 test where C2's "only relevant input" needs the verifier's
qualification. The predictions for B1 and B2 come from the verifier's
own code comment, not from a test.

**Falsification.** C1/C2 for this host are false if G1 differs (with K
detected and W1 confirming the published hash). G2 or G4 differing
narrows C2 (bootstrap or path is an input). B1 or B2 *matching* means the
cleared variable did not affect this build, and the verifier's caution is
recorded as broader than needed for that variable.

**Replay rule.** G1 is built twice from two fresh exports; the two
archives must be byte-identical, or every result is reported as
uninformative (the host itself is not deterministic).

## Operator machine (independent anchors)

- W1. Download `go1.27.0.windows-amd64.zip` from go.dev/dl and
  `sha256` it with `Get-FileHash`. Must equal `f0c0a0d3...a667c4`;
  otherwise the expected values above are wrong and are corrected by
  amendment before any comparison is scored.
- W2. Compare the installed toolchain (`C:\Program Files\Go`, from the
  MSI) with the zip's contents: every file in the zip hashed and compared
  with the installed file. Predicted: all equal, except files the MSI is
  known not to install, recorded as found.

## Stop rule and scope

Hard stop 22:00 local on 2026-10-12. Whatever has run by then is
committed and reported; nothing is rerun to change a result. Not in
scope tonight: a Windows-host rebuild, C4 (user programs, including the
Case Study 4 binaries), other targets, other Go versions.

## Development disclosure

Before this plan: on 2026-10-12 the sandbox built `go1.27.0 linux/amd64`
from the GitHub tag with bootstrap A, for Case Study 4 (`make.bash`, no
`-distpack`; never compared with any published hash). The blog post,
go.dev/rebuild, the go.dev/dl index and `gorebuild` source were read. No
distpack archive has been built.

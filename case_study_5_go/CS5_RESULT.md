# Case Study 5 result: Go reproducible toolchains

Written 2026-10-12 from committed data only (`cs5-go` at `49f6f28`).
Governing documents: `CS5_PLAN.md` (`762c841`) and `CS5_AMENDMENT_1.md`
(committed in `4f91a9e`; see section 5). Section 2 records observations
only; interpretation starts in section 3.

**Status: every pre-registered prediction held. Go's reproducibility claim
survived every test this study put to it, including the two boundary
runs. Nothing new about Go is claimed: B1 and B2 were predicted from the
verifier's own code comment.**

## 1. What was run

| Item | Value |
| --- | --- |
| Source | tag `go1.27.0`, commit `8af21751f066eced273ca3ce49506b366847c623`, `git archive` per run (`source_commit.txt`, `source_VERSION.txt`) |
| Bootstrap A / B | `go1.24.7 linux/amd64` / sandbox-built `go1.27.0 linux/amd64` (`bootstrap_A.txt`, `bootstrap_B.txt`) |
| Build host | sandbox, Linux x86-64, 2 CPUs, gcc 13.3.0 |
| Script | `harness/run_cs5.sh`, SHA-256 `F883FF45...3228C`, unchanged from before the first start |
| Session | 2026-10-12 22:23:31 to 23:13:08 UTC (second start; amendment 1), all 8 runs `make.bash` exit 0 |
| Operator machine | W1 and W2 (`harness/run_cs5_w.ps1`), Windows, 2026-10-12 22:05 UTC |
| Expected hashes | go.dev/dl index: windows zip `f0c0a0d3...a667c4`, linux tar.gz `675c26c4...80685` (plan, "Prior art") |

## 2. Observations

From `results/results.tsv`; archive hashes also in `results/SHA256SUMS.txt`
(the archives themselves are not committed).

| Run | Target | Bootstrap | Variation | SHA-256 of archive | Equal to published |
| --- | --- | --- | --- | --- | --- |
| G1a | windows/amd64 | A | none | `f0c0a0d3...a667c4` | yes |
| G1b | windows/amd64 | A | replay of G1a | `f0c0a0d3...a667c4` | yes |
| K | windows/amd64 | A | one byte in a `src/fmt/print.go` comment | `87c84e42...8ca9f` | no |
| G2 | windows/amd64 | B | bootstrap B | `f0c0a0d3...a667c4` | yes |
| G3 | linux/amd64 | A | none | `675c26c4...80685` | yes |
| G4 | windows/amd64 | A | path with spaces, two directory levels deeper | `f0c0a0d3...a667c4` | yes |
| B1 | windows/amd64 | A | `GOAMD64=v3` | `f6ea4580...2df34` | no |
| B2 | linux/amd64 | A | `CGO_ENABLED=1`, gcc present | `bb74755d...dd9f0` | no |

Contents of the differing archives against their baseline
(`results/ARCHIVE_DIFFS.txt`; same entry list in every pair, 15,636
entries for windows, 17,350 for linux):

- K vs G1a: 1 entry differs, `go/src/fmt/print.go`. Every binary is equal.
- B1 vs G1a: 11 entries differ: `go/src/internal/buildcfg/zbootstrap.go`
  (`DefaultGOAMD64` `v1` -> `v3`) and 10 executables (`go.exe`,
  `gofmt.exe`, and `asm`, `cgo`, `compile`, `cover`, `fix`, `link`,
  `preprofile`, `vet` under `pkg/tool`).
- B2 vs G3: 10 entries differ: `zbootstrap.go` (`DefaultCGO_ENABLED` `""`
  -> `"1"`) and 9 executables (the same set less `gofmt`).

Operator machine (`results/operator/summary.txt`):

- W1: downloaded `go1.27.0.windows-amd64.zip`, 78,924,880 bytes, SHA-256
  `F0C0A0D3...A667C4`: MATCH.
- W2: installed `go1.27.0 windows/amd64` (MSI) at `C:\Program Files\Go`
  against the zip: 15,636 equal, 0 differ, 0 missing, 0 extra
  (`w2_differences.tsv` holds only its header).

Not pre-registered, recorded as found (`make_*.log`, the `distpack:`
lines, which print 16 hex digits): every run also packed
`go1.27.0.src.tar.gz` with prefix `7002403d7cc44529`, the published
source archive's prefix, except K (`25b4853ca440396b`).

## 3. Readings against the plan

Preconditions: W1 confirms the expected windows hash independently; the
replay rule holds (G1a and G1b byte-identical); K is detected. Every run
is therefore informative.

- **C1 / C2 for this host: hold.** The falsification condition (G1
  differs, with K detected and W1 confirming) did not occur. A Linux host
  cross-compiling for Windows produced the published Windows archive
  bit for bit, and the native Linux archive also matched (G3).
- **G2, G4: C2 not narrowed.** Neither the bootstrap's major version
  (1.24.7 vs 1.27.0) nor a longer build path with spaces changed a byte.
- **B1, B2: differ, as predicted.** `GOAMD64` and `CGO_ENABLED` are
  inputs: each sets one default baked into `internal/buildcfg`, and every
  toolchain binary built from it changes. C2's "its only relevant input
  is the source code" therefore holds as the verifier applies it, with
  its listed variables cleared, not for an arbitrary environment. This is
  the qualification `gorebuild` already states in its code; the study
  confirms it on two of the roughly twenty cleared variables and says
  nothing about the rest.
- **W2:** the MSI installs exactly the zip's files; predicted, held.
- **C3** (Google's release process requires Linux and Windows builders to
  agree) and **C4** (user programs) were not tested.

## 4. What K shows and what it does not

K shows the comparison detects a one-byte change anywhere in the archive.
It does not show that the compiled toolchain is sensitive to source
changes: the edit was a same-length comment change, which alters no
compiled output, and the archive differs only because it ships the
source file. The binary-level sensitivity in this study comes from B1 and
B2, not from K. A sharper control would change one byte of code.

## 5. Deviations and process errors

Kept here as they happened.

1. **Container restart (amendment 1).** The first start (22:04:33 UTC)
   was killed when the sandbox restarted at about 22:22 UTC, during G1a,
   before any archive or hash existed (`make_G1a_interrupted.log`). The
   amendment was written and hashed (`FCBBB783...6DB57`) in the session
   before the second start at 22:23:30, but committed only afterwards, in
   `4f91a9e`, with the results. Its text says "about 22:24 UTC"; the
   restart was at 22:23:30. Left as written.
2. **Per-run `GOCACHE`** (plan, "Inputs"; script header): gorebuild uses
   the default cache. Recorded deviation; no observed effect.
3. **Source from the GitHub mirror via `git archive`**, not
   go.googlesource.com's tarball as gorebuild fetches it. The matching
   `src.tar.gz` prefixes (section 2) are consistent with identical trees;
   only 16 hex digits were compared.
4. **Logs dropped by `.gitignore`.** The results commit `4f91a9e` omitted
   the 10 `*.log` files (`.gitignore` line 33). The commit script checked
   file hashes but not what `git add` staged. Fixed by `49f6f28`, which
   force-adds only those 10 after re-checking their hashes; all 22
   delivered files then verified from a fresh clone.

## 6. Limits

- One build host (Linux) and one operator machine; no Windows-host build.
- Bootstrap B was itself built with bootstrap A, so G2 is not a test with
  an independent compiler lineage.
- Two of about twenty cleared variables tested; one Go version; two
  targets.
- B1 and B2 were predicted from the verifier's source, so they confirm a
  documented boundary rather than find one.
- The plan, script, checks and this write-up are by the same party; the
  verdict recomputation from the committed `results.tsv` (sandbox, clone
  of `49f6f28`) shows the arithmetic, not independence.

## 7. What this case adds

Case Study 4 was out of class and found a behaviour under contract review.
This one is in class: a deterministic transformation with published
integrity artifacts and a specific claim. CBV's bounded reading here is
that the claim holds within the boundary its own verifier draws, and
that boundary is real (B1, B2). A system that keeps its claim is a valid
outcome for the protocol; it is not evidence of a weakness in Go.

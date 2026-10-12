# Case Study 3 harness (etcd raft ReadIndex)

Deterministic simulator for `CS3_EXECUTION_PLAN.md`. Three `RawNode`s, a
seeded network and client schedule generated before any run, histories
checked with Porcupine v1.3.1.

## Files

| File | Role |
| --- | --- |
| `common.go` | Version-neutral types and the `Peer` adapter interface |
| `adapter_v36.go`, `adapter_v37.go` | The only files that touch raft; one per release, chosen by build tag. They differ because v3.7.0 moved to standard protobuf (pointer fields) |
| `detrand.go` | Seeds `crypto/rand.Reader`, which raft uses for election timeouts, and checks the override works |
| `schedule.go` | Schedule generation and the per-message `Fate` function |
| `sim.go` | Network, faults, nodes, clients, attribution flags, conformance checks |
| `history.go` | History records and the Porcupine register model |
| `p1a.go` | The directed #392 scenario |
| `selftest.go` | Oracle and encoding self-test |
| `trial.go`, `main.go` | Trial runner and command line |
| `raft360.mod`, `raft370.mod` | Operator module files; they differ only in the raft version line |
| `build.ps1`, `prerun.ps1` | Operator build, self-test, schedule generation and pre-run hashing |
| `dev36.mod`, `dev37patched.mod` | **Development only**, see below |

## Operator sequence (Windows, Go 1.26+)

```powershell
cd C:\Users\gosur\phoenix-verify\case_study_3_raft\harness
.\build.ps1        # builds h360.exe and h370.exe, runs both self-tests
.\prerun.ps1       # generates schedules, writes ..\HASHES_BEFORE_RUN.txt
cd C:\Users\gosur\phoenix-verify
git add case_study_3_raft
git commit -m "Case Study 3: harness, schedules and pre-run hashes (no runs)"
git push
```

Then, in order, and only after the push:

```powershell
cd case_study_3_raft\harness
.\h360.exe p1a -from 0 -to 20 -out ..\results\P1a                    # gate
.\h360.exe selftest -p1a-history ..\results\P1a\p1a_0_history.jsonl
.\h370.exe selftest -p1a-history ..\results\P1a\p1a_0_history.jsonl
.\h360.exe run -arm P1b -schedules ..\schedules\P1b_P2 -from 1 -to 2000 -out ..\results\P1b
.\h370.exe run -arm P2  -schedules ..\schedules\P1b_P2 -from 1 -to 2000 -out ..\results\P2
.\h370.exe run -arm P3  -schedules ..\schedules\P3     -from 2001 -to 3000 -out ..\results\P3
.\h360.exe diverge -a ..\results\P1b -b ..\results\P2 -from 1 -to 2000 > ..\results\divergence.txt
```

If P1a does not succeed (`success=true` for at least one jitter value in
`p1a_summary.txt`), stop: the plan says nothing further is run.

## Development builds

This sandbox could not reach `proxy.golang.org` or download Go 1.26. During
development:

- `dev36.mod` built against raft v3.6.0 source checked out from GitHub at
  the release tag, with an empty stub for `golang.org/x/tools` (required in
  the module graph by gogo/protobuf, never compiled).
- `dev37patched.mod` built against a **patched copy** of v3.7.0 in which
  Go 1.26 `new(expression)` calls were rewritten to a helper so it compiles
  under Go 1.25. It was used only to type-check and exercise the v3.7
  adapter. No result from it is evidence.

Scored runs use only `raft360.mod` and `raft370.mod` with unmodified
releases fetched through the Go module proxy and checksum database.

# Case Study 3: development log (before hashing)

Session of 2026-10-11, about 23:15-00:00 EDT. Everything here was run on
development builds in Claude's sandbox. None of it is a scored result.

## Environment constraints

- The sandbox's egress proxy refused `proxy.golang.org` (HTTP 403 on
  CONNECT), so neither Go modules nor the Go 1.26 toolchain could be
  downloaded. Local toolchains: Go 1.24.7 and 1.25.1.
- v3.7.0 declares `go 1.26` and uses the Go 1.26 `new(expression)`
  form (79 sites), so it cannot compile under Go 1.25.

What was done instead:

- **v3.6.0:** built from the release tag checked out from GitHub
  (`f35a022`), with `google.golang.org/protobuf` and `gopkg.in/yaml.v3`
  from their GitHub sources at the required tags, and an empty module
  stub for `golang.org/x/tools`, which gogo/protobuf lists in its module
  graph but which is never compiled. Module file: `dev36.mod`.
- **v3.7.0:** a copy of the release tag (`b867cf1`) with its `go`
  directive lowered to 1.25 and every `new(expression)` rewritten to a
  generic helper `ptrTo(expression)` by a small AST tool, in 13 files.
  Used only to type-check and exercise the v3.7 adapter. Module file:
  `dev37patched.mod`. **No result from this copy is evidence.**

## Findings that changed the plan (draft 3)

1. Both releases take election timeouts from `crypto/rand.Reader`
   (`raft.go`, `lockedRand.Intn`). A seed alone could not reproduce a
   run. Fix: seeded Reader per trial, with a self-check.
2. v3.7.0's protobuf migration changed `Message`, `Entry`, `Snapshot`,
   `HardState` and `Ready` to pointer types. Fix: one adapter per release.
3. `MemoryStorage.ApplySnapshot` rejects a snapshot at index 0, so nodes
   start from a snapshot at index 1, term 1, with the three-voter
   configuration (the library's restart-from-snapshot path).
4. Writing P1a forced the trace corrections listed in the plan's draft 3
   notes (client 3 writes; the retry comes from a delayed response; node
   1's ticks stall during the partition).
5. The first jittered P1a runs aborted because jitter delayed the very
   heartbeat responses the scenario holds. Jitter now excludes the read
   path.

## Runs

All P1a runs below used the development builds. Reserved values (jitter
1-20, randomized seeds 1-3000) were not used.

| Build | Run | Result |
| --- | --- | --- |
| v3.6.0 (release source) | `selftest` | passed, Go 1.24.7 |
| v3.6.0 | P1a jitter 0 (canonical) | Illegal, #392 shape, conformance clean, replay identical: **success** |
| v3.6.0 | P1a jitter 1001-1020, first harness version | 7 success, 13 aborted (jitter on the read path) |
| v3.6.0 | P1a jitter 1001-1020, after the fix | 20 of 20 success |
| v3.6.0 | `selftest` with the recorded P1a history as case (d) | passed |
| v3.7.0 (patched dev copy) | `selftest` with the v3.6.0 P1a history | passed, Go 1.25.1 |
| v3.7.0 (patched dev copy) | P1a jitter 0 | Ok; node 1 produced no ReadState for read B |
| v3.6.0 | randomized seeds 900001-900010 (development schedules) | 10 Ok; no flags; #392 shape 0 of 10 |
| v3.6.0 | seed 900001 rerun | history byte-identical |

Canonical P1a on v3.6.0, as recorded: node 1 leader in term 1, commit 2;
read A confirmed at node 1 at tick 10 with its response to node 2 held;
retry held; new leader node 3 in term 2 at tick 22; write 42 committed
at index 4 and completed; read B on node 1 got `ReadState` index 2 and
returned 0. Client-history bound 4, library bound 4, both flags set.

Randomized development trials ran 976-1452 ticks, about 8,000 messages
each with about 5 per cent dropped, 11-22 fault windows, and 18-25 per
cent of reads needing more than one submission. Ten trials take under a
second.

## Open points for the operator run

- Whether `crypto/rand.Int` honours a replaced Reader under Go 1.26.
  The self-test checks it; if it fails, determinism must be solved
  before any arm.
- The v3.7 adapter has only been compiled against the patched copy. It
  must compile unchanged against the real release under Go 1.26.
- Reachability of the #392 shape by the randomized workload is unknown.
  0 of 10 development trials reached it. P1b is a measurement, not a
  gate; see the plan, section 7.

## After reconciling the August raft study (same evening)

`sim.go` now records a conformance failure if any non-normal entry (for
example `EntryConfChange`) is committed, which the selection record
states. Development checks rerun with the same development seeds:
self-test passed; P1a jitter 0 on v3.6.0 succeeded with a byte-identical
history to the earlier run; jitter 1001-1020 succeeded 20 of 20; seeds
900001-900010 all Ok with no conformance failures; P1a on the patched
v3.7.0 copy unchanged (no ReadState for read B).

## Operator build, first attempt (2026-10-11 23:47)

`build.ps1` failed on the operator's machine (Windows PowerShell, Go
1.27.0): unquoted `-modfile=raft360.mod` was split at the dot, and the
script did not stop when Go exited non-zero. Fixed in `build.ps1` and
`prerun.ps1`: arguments are passed as quoted arrays and every native
call is checked. No binary was built and nothing was run by that attempt.

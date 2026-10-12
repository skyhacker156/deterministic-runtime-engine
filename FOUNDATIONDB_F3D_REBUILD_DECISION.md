# F-3d — Rebuild Feasibility Decision and Final F-3 Status

**Status:** decision reached, applying the pre-registered rule exactly as
specified before any construction began. No source modification made. No
rebuild attempted.

## Step 1 — Narrow-build feasibility, checked directly, not estimated

**Is `fdbserver` a separable target?** Confirmed from the real
`CMakeLists.txt`: `fdbserver` links against `fdbclient`, `metacluster`,
`sqlite`, and (optionally) RocksDB — a real, non-trivial dependency
chain, not a standalone small binary.

**Real file counts, counted directly, not estimated:** `fdbserver`,
`fdbclient`, `flow`, `fdbrpc`, and `metacluster` together comprise **464
real, non-test `.cpp` source files.** This is not a small subset of the
codebase — it is the system's core.

**Memory risk, checked directly against the actual file that would need
modification:** `storageserver.actor.cpp` — the file this construction
would need to touch — is **16,106 lines**, among the largest in the
entire repository (`DDTeamCollection.actor.cpp` at 7,196 and
`VersionedBTree.actor.cpp` at 11,630 are the next largest in the
dependency set). Flow-actor-compiled files of this size are known to
require substantial per-file compilation memory; this sandbox has **1
CPU core and ~3.8GB total RAM.** A single heavy translation unit
plausibly consuming a large fraction of total available memory, on a
single-threaded build with no parallelism to amortize the risk, is a
real and specific concern here — not a generic "builds are hard"
caution.

**Verdict on Step 1: does not clear the resource envelope.** Both named
disqualifying conditions from the pre-registered decision rule are met
independently: the target does not separate meaningfully from the bulk
of the codebase, and estimated memory usage is unsafe given the specific
file in question and the specific hardware available.

## Step 2 — Existing hook search, narrow, targeted, completed

Searched specifically for mutation-corruption hooks in the Resolver,
commit proxy, and transaction log layers (no `BUGGIFY` found there
touching mutation content — consistent with `F-3c`), and for existing
test workloads that intentionally modify mutations.

**Found: `StorageCorruption.actor.cpp` and its real backing mechanism,
`StorageCorruptionBug` (`SimBugInjector`-managed), with a real,
ready-to-run test file (`tests/negative/StorageCorruption.toml`).** Read
directly in source (`storageserver.actor.cpp`, `writeMutationsBuggy`,
~line 14000): for each mutation, **each storage server independently**
draws from its own `deterministicRandom()` stream and, with a configured
probability, **drops** that mutation from its own local disk write —
never applying it. Confirmed decisively: this is a per-replica,
independent-corruption mechanism (the shape needed for the "Independent
corruption" control condition), not a shared, pre-fan-out
mutation-content alteration (the shape `F-3`'s actual proposition
requires). It also corrupts by *omission* (dropping a mutation), not by
*alteration* (writing a different value) — a further, smaller structural
mismatch from the precise construction requested.

**This confirms, from a second independent angle, `F-3c`'s finding:** no
existing, already-compiled mechanism was found — in this search or the
prior one — that operates on a mutation before replica fan-out in a way
that would produce shared, identical, incorrect state across replicas.

## Step 3 — Decision, applying the pre-registered rule

Per the rule set before this construction began:

> Do not rebuild if: `fdbserver` pulls essentially the entire
> compilation burden; estimated memory usage is unsafe; or an existing
> simulator/test mechanism can perform the same construction.

**Two of the three disqualifying conditions are independently confirmed:
the compilation burden is not separable in any meaningful way, and
estimated memory usage is unsafe given the specific hardware and the
specific file involved.** (The third condition — an existing mechanism
performing the *same* construction — is not met; what exists performs a
*different*, independent-corruption construction instead, which is real
and useful for a different purpose but does not substitute for the
shared-corruption proposition.)

**Decision: do not rebuild.**

## Final F-3 status, stated precisely rather than weakened

Per the standing instruction not to substitute a weaker construction
merely to claim `F-3` was experimentally tested:

> The source-level evidence (`FOUNDATIONDB_F3_DECOMPOSITION.md`,
> `FOUNDATIONDB_F3B_ORACLE_INVENTORY.md`, `FOUNDATIONDB_F3C_SIMULATOR_CAPABILITY.md`)
> establishes the observation boundary: `ConsistencyCheck` and
> `AuditStorage`'s `replica` mode compare replicas against each other,
> not against an independently-derived ground truth; no independent
> correctness oracle for application-level data was found across a
> systematic search of the most likely candidate mechanisms; and no
> existing simulator or test mechanism — searched specifically and
> confirmed by reading real trigger code — produces the shared,
> pre-replication-fan-out corruption the central proposition requires.
> **The correlated-corruption proposition itself — would `ConsistencyCheck`
> accept identical incorrect state across all replicas — remains
> experimentally untested under the available environment.** This is a
> real, honest limitation of this phase's findings, not a claimed result.

## What remains genuinely available, and clearly distinguished from what
   doesn't

The **independent-corruption control** (the second of the three
originally proposed conditions) is real, ready to run, requires no
rebuild, and would provide genuine additional evidence that
`ConsistencyCheck` does catch per-replica divergence — closing the loop
on the "control" side of the original three-condition design, even
though the "shared corruption" condition (the actual proposition) remains
out of reach in this environment. Whether this is worth running as a
standalone confirmation, clearly labeled as testing a different and
already-well-evidenced question, is a decision for whoever reviews this
finding — not decided or assumed here.

## Explicitly not done

No source modification. No rebuild attempted or partially attempted. The
`StorageCorruption` workload was read but not run in this pass.

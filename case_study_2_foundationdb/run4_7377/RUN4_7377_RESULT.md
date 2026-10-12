# Case Study 2, Step 3: run 4 on release 7.3.77 — result

Date: 2026-10-11. Plan: `CONFIRMATION_RUN4_7377.md`, hashed before any 7.3.77 run (`HASHES_BEFORE_RUN.txt`).
Binary: official `fdbserver.x86_64` 7.3.77 (source version 3ea44ce1d9003ad095e408039e1f755c319c4dfb,
SHA-256 6fe47a94…b5ada1), the release FoundationDB's releases page marked "Latest" on this date.

## Result

The deletion reproduces on the current production release.

| Prediction | Outcome |
| --- | --- |
| P1. Every cluster with no stored region configuration: all storage servers dispose their stores, the test fails, a further restart fails | 9 of 9 (150 of 150 storage servers) |
| P2. No cluster with a stored region configuration shows full disposal | 0 of 11 |
| P3. Both controls pass | 20 of 20 each |

Screening: 61 of 400 seeds (10000-10798) produced two-datacenter clusters; the first 20 were run.

## Caveat, same as runs 1 and 3
On seed 10112 the simulator's own random zone rename fired in the untouched control, so that seed's control is not a
pure no-rename control. Excluding it, P1 holds on 8 of 8.

## Combined with 7.3.63
Across 7.3.63 (runs 1 and 3) and 7.3.77 (run 4): 27 of 27 target clusters lost every storage server's data; no
cluster outside the target class lost storage data; both controls passed on every seed.

## What this changes in earlier records
`CS2_STEP3_RESULT.md` and the protocol entry say only 7.3.63 was run. That is now out of date for 7.3.77. 7.4.x, 8.0.0
and main remain untested (all pre-release or unreleased on this date).

## Pre-run checks (from the plan)
The 7.3.77 test pair is byte-identical in content to the 7.3.63 pair (folder renamed to `from_7.3.50_until_7.4.0`).
`SimulatedCluster.actor.cpp` lines 1300-1500 are identical between the two releases; the `worker_removed` throw and the
`dispose()` call are present.

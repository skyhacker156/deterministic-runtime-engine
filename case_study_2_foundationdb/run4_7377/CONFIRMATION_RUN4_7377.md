# Case Study 2, Step 3: run 4 on release 7.3.77 (written and hashed before any 7.3.77 run)

Date: 2026-10-11. Reason: 7.3.77 is the release FoundationDB's releases page marks "Latest"; the 7.4.x and 8.0.0
builds are marked pre-release. Runs 1-3 used 7.3.63.

## Pre-run checks already done (source and files only, nothing executed)
- Binary: official `fdbserver.x86_64` 7.3.77, source version 3ea44ce1d9003ad095e408039e1f755c319c4dfb.
- Test pair: `tests/restarting/from_7.3.50_until_7.4.0/ConfigureTestRestart-{1,2}.toml` at tag 7.3.77, byte-identical
  in content to the 7.3.63 pair used before (the folder was renamed). The same tests/T1.toml and tests/T2.toml are used.
- `SimulatedCluster.actor.cpp` lines 1300-1500 (restart path: zone-only rename, two-datacenter region auto-config)
  are identical between 7.3.63 and 7.3.77. The `worker_removed` throw and the `dispose()` call are still present.

## Selection
Screen seeds 10000, 10002, ..., 10798 (400 seeds) with 7.3.77, phase 1 only; take the first 20, in increasing order,
with exactly 2 datacenters. Report the two-datacenter rate.

## Run, definitions
As run 3 (CONFIRMATION_RUN3.md, CONFIRMATION_RUN2.md), with only the binary path changed (scripts/run4_one.sh is
scripts/run2_one.sh with FDB and output directory changed).

## Predictions
P1. Every class X seed: `dc` shows full deletion, phase 2 fails, dc_keep restart fails; controls pass without full deletion.
P2. No selected seed outside class X shows full deletion in any condition.
P3. `none` and `zone` pass on every selected seed.
Fewer than 3 class X seeds: uninformative for P1.
If P1 fails on 7.3.77, the restart code being identical points to a change elsewhere, to be located, not assumed.

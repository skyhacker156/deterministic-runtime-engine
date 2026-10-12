# Case Study 2, Step 3: amendment to the bounded construction (written before any confirmatory run)

Date: 2026-10-11. Supersedes the delivery mechanism and scoring of CS2_STEP3_RUN.md (2026-09-28). The prediction is kept.

## What changed and why
1. Delivery: no source patch and no rebuild. The simulator's restart path reads each machine's `dcUID` and `zoneId`
   from `simfdb/restartInfo.ini` (SimulatedCluster, `restartSimulatedSystem`). Editing that file between phase 1 and
   phase 2 renames the IDs at the same point the 13-line patch would have. Reason: the build was the blocker.
2. Binary: official release `fdbserver.x86_64` v7.3.63 (source version 5140696da2df47c143ae74c0f4207b65d0d94876),
   not main commit a2f0c6d. Test pair: `tests/restarting/from_7.3.50/ConfigureTestRestart-{1,2}.toml` at tag 7.3.63.
3. Conditions (same three): none = file untouched; zone = every zoneId -> modified/<zoneId>;
   dc = zone change plus every non-empty dcUID -> modified/<dcUID>. Each condition starts from a byte copy of the
   same phase-1 state. Phase 1 seed S, phase 2 seed S+1, `--buggify off`, as in the September script.
4. Seeds: 9000, 9002, ..., 9078 (40 seeds). Never run before this file is hashed. Dev seeds 1000 and 1002 only.
5. Per-run real-time limit 300 s (a normal phase 2 took about 9 s on the dev seed). A timeout is recorded as a failure.

## Disclosure of the dev look (seeds 1000, 1002)
- All three conditions passed on seed 1000.
- `KVSRemoved` with `Reason=worker_removed` and `StorageServerTerminated` appeared 5 times in the UNTOUCHED control.
  They are routine when the ConfigureDatabase workload changes storage engines. The September prediction said the
  controls would show none of these events; that part was wrong and cannot be scored as written.
- The ConfigureDatabase workload only issues region configurations when the simulated cluster has 2 or more than 3
  datacenters, and it hardcodes region datacenter ids "0" and "1". So in condition dc the region config names the OLD
  ids, while in #4089 it named the NEW ids. This construction is therefore the rename the September patch specified,
  not an exact replay of #4089. That limit applies equally to the patch.

## Scoring (fixed now)
- Manipulation check: dc rows must show trace events carrying a modified datacenter id and none/zone rows must show
  zero; zone and dc rows must show modified zone ids. Rows failing this do not count.
- Primary outcome: phase 2 fails (non-zero exit, timeout, or no "tests passed" line) in dc on a seed where none and
  zone both pass.
- #4089 signature: `TLogPeekLocalNoBestSet` > 0 in dc and 0 in both controls on the same seed.
- KVSRemoved/worker_removed and StorageServerTerminated counts are reported, not scored.
- Region exposure is reported per seed: datacenter count, and whether phase 2 issued a non-empty `regions=` config.

## Prediction (unchanged from September)
In condition dc, at least one seed shows TLogPeekLocalNoBestSet and phase 2 fails. Conditions none and zone show no
TLogPeekLocalNoBestSet and pass.

## Reading of outcomes
- dc shows the signature and fails, controls clean: the #4089 deletion path is reachable in simulation by a rename the
  simulator never performs.
- dc fails without the signature: renaming breaks the cluster by another route.
- dc passes everywhere: this rename is tolerated in 7.3.63 under this workload; the comment/code gap remains the finding.
- a control fails: the harness or the same-binary restart is unsound and no row counts until explained.

# Case Study 2, Step 3: confirmation run on fresh seeds (written and hashed before any of these seeds is run)

Date: 2026-10-11. Reason: the deletion finding in run 1 (seeds 9000-9078) was identified after seeing the data, and both
trace signatures fixed in the amendment turned out to be non-specific (they appear in untouched controls). Under the
project's own rule, a finding shaped after the fact needs fresh seeds.

## Fixed inputs
Same binary (fdbserver 7.3.63), same test pair, same three conditions, same edit script, `--buggify off`.
Seeds 9100, 9102, ..., 9178 (40 seeds). Never run before this file is hashed.

## Definitions (fixed now)
- Class X seed: the simulated cluster has exactly 2 datacenters AND the first recovered configuration after restart in
  the UNTOUCHED control (`none`) has no region configuration. Class is read from the control, never from `dc`.
- Restored storage servers: distinct ids logging `StorageServerRestoreDurableState` in phase 2.
- Full deletion: every restored storage server logs `KVSRemoved` within 30 simulated seconds of restart.
- dc_keep restart: restart once more from the `dc` end state with the renamed file (names consistent with the stored
  configuration), seed S+2.

## Predictions
P1. Every class X seed: `dc` shows full deletion, phase 2 fails, and the dc_keep restart fails; `none` and `zone` pass
    and do not show full deletion.
P2. No seed outside class X shows full deletion in any condition.
P3. `none` and `zone` pass on all 40 seeds.
Falsified by: one class X seed without full deletion in `dc`; one non-class-X seed with full deletion; or a control failure.
If fewer than 3 class X seeds occur, the run is uninformative for P1 and is reported as such.

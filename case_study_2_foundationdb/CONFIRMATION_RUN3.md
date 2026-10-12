# Case Study 2, Step 3: second confirmation run, seeds selected by cluster shape (written and hashed before any run)

Date: 2026-10-11. Reason: run 2 (seeds 9100-9178) produced zero class X seeds (one two-datacenter cluster in 40, with
stored regions) and was uninformative for P1 by its own rule. P2 and P3 held there.

## Selection (pre-treatment only)
Screen seeds 9200, 9202, ..., 9998 (400 seeds) by running PHASE 1 ONLY and counting distinct non-empty dcUID values in
restartInfo.ini. No phase 2 is run during screening. Take the first 20 seeds, in increasing order, with exactly 2
datacenters. If fewer than 20 exist, take all of them. The two-datacenter rate over the 400 seeds is reported.

## Run
Same binary, test pair, conditions, edit script and harness as run 2 (scripts/run2_one.sh, unchanged, same hash).

## Definitions: as CONFIRMATION_RUN2.md (class X read from the untouched control; full deletion; dc_keep restart).

## Predictions
P1. Every class X seed: `dc` shows full deletion, phase 2 fails, dc_keep restart fails; `none` and `zone` pass without
    full deletion.
P2. Every selected seed outside class X (two datacenters WITH stored regions): no full deletion in any condition.
P3. `none` and `zone` pass on every selected seed.
Falsified by one class X seed without full deletion in `dc`, one non-class-X seed with full deletion, or a control failure.
Fewer than 3 class X seeds: uninformative for P1, reported as such, and no further run today.

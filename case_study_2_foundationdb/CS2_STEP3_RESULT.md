# Case Study 2 (FoundationDB), Step 3: bounded construction for issue #4089 — result

Date: 2026-10-11. System under test: FoundationDB official release binary `fdbserver.x86_64` v7.3.63
(source version `5140696da2df47c143ae74c0f4207b65d0d94876`, SHA-256 `4b10b947…5b74400`).
Test pair: `tests/restarting/from_7.3.50/ConfigureTestRestart-{1,2}.toml` at tag 7.3.63. `--buggify off`.

## Result in one paragraph

Renaming datacenter IDs across a simulated restart destroys every storage server's data in every tested
two-datacenter cluster that had no stored region configuration: 11 of 11 in the pre-registered confirmation run,
7 of 7 in the earlier exploratory run. None of the 82 other clusters tested lost storage data. Both controls
(untouched, and zone IDs renamed) passed on all 100 seeds. The sequence is the one reported in apple/foundationdb
issue #4089. FoundationDB's simulator never produces this input: its restart code carries a comment saying it
renames datacenter IDs, and renames zone IDs only.

## Construction

The simulator's restart path reads each machine's `dcUID` and `zoneId` from `simfdb/restartInfo.ini`. Editing that
file between phase 1 and phase 2 renames the IDs at the point where the September patch would have. No source patch,
no rebuild. Three conditions, each started from a byte copy of the same phase-1 state:

| Condition | Edit |
| --- | --- |
| `none` | file untouched |
| `zone` | every `zoneId` becomes `modified/<zoneId>` (the rename FDB already models) |
| `dc` | the zone edit, plus every non-empty `dcUID` becomes `modified/<dcUID>` |

Phase 1 uses seed S, phase 2 uses S+1.

## Three runs

| Run | Seeds | Status | What it showed |
| --- | --- | --- | --- |
| 1 | 9000–9078 (40) | Plan hashed first; deletion pattern found afterwards | `dc` fails on 25 of 40; 7 of those are full deletion |
| 2 | 9100–9178 (40) | Predictions hashed first | Uninformative for P1: zero class X seeds occurred. P2 and P3 held |
| 3 | 20 two-datacenter seeds from 9200–9998 | Predictions hashed first; seeds selected on phase 1 only | P1, P2, P3 all held |

**Class X** (defined before runs 2 and 3): exactly 2 datacenters, and the first recovered configuration after restart
in the untouched control has no region configuration.
**Full deletion**: every storage server restored from disk in phase 2 logs `KVSRemoved` within 30 simulated seconds.

### Run 3 (the confirmatory result)

| Prediction | Outcome |
| --- | --- |
| P1. Every class X seed: `dc` shows full deletion, phase 2 fails, a further restart with consistent names fails; controls pass without full deletion | Held, 11 of 11. 183 storage servers restored, 183 disposed |
| P2. No selected seed outside class X shows full deletion | Held, 0 of 9 |
| P3. `none` and `zone` pass on every selected seed | Held, 20 of 20 each |

The 9 seeds outside class X had a stored region configuration naming the old IDs. They became unavailable under `dc`
and deleted nothing. In run 1, the 4 clusters of that kind recovered once the original names were restored (4 of 4).

### Run 1, scored as its plan was written

- Controls: 40 of 40 pass in both.
- Primary outcome (`dc` fails where both controls pass): 25 of 40. Two seeds (9018, 9058) fail the plan's validity
  check because the simulator's own random zone rename fired in the untouched control; excluding them, 24 of 38.
- Trace signature (`TLogPeekLocalNoBestSet` in `dc`, absent in controls): 0 seeds. The event appears in the
  untouched control on 22 seeds. It is routine and cannot identify this failure.
- September prediction: half right. `dc` did fail with that event present. The controls did not stay free of it.

## Mechanism, read from the 7.3.63 source

1. `SimulatedCluster.actor.cpp:1310–1313`: the comment reads "Randomly change data center id names to test that
   localities can be modified on cluster restart". The code below it sets `renameZoneIds`.
2. `SimulatedCluster.actor.cpp:1460–1485`: on restart of a cluster with exactly two datacenter IDs, the simulator
   itself issues `single usable_regions=2 regions=[…]`, built from the IDs it just read. Under `dc` those are the
   new names. So the harness supplies the "configure regions" step of #4089 on its own.
3. `TagPartitionedLogSystem.actor.cpp:960–967`: a storage server whose tag locality has no matching log set logs
   `TLogPeekLocalNoBestSet` and throws `worker_removed`.
4. `storageserver.actor.cpp:13655–13659`: on `worker_removed` the server logs `KVSRemoved` and calls
   `persistentData->dispose()`.

On main at commit `b386c88` (2026-10-11) the same sites exist, by reading only: `SimulatedCluster.cpp:1355–1358`
and `:1491`, `logsystem/LogSystemConsumer.cpp:359–366`, `storageserver/storageserver.cpp:13032–13033`.

## What this establishes

- The #4089 deletion sequence is reproducible in release 7.3.63 inside FoundationDB's own simulator.
- The simulator's input space excludes it by one rename, while a comment in the code says the rename happens.
- Claim origin: this gap sits inside the project (a code comment), not in outside descriptions of it.

## What it does not establish

- That 7.4.x, 8.0.0 or main behave the same. Only 7.3.63 was run.
- That FoundationDB's maintainers regard this as a bug and not an unsupported operation. The #4089 thread, as
  fetched, records no maintainer resolution.
- Anything with fault injection on, or with another workload. One test pair, `--buggify off`.
- Independent reproduction (protocol step 6). One harness, one operator; the oracle is FoundationDB's own test
  verdict and trace events.
- Why the renamed datacenter leaves storage servers without a matching log set. Steps 3 and 4 of the mechanism above were read in
  source and seen in traces. The link before them (a stale entry in `\xff/tagLocalityList` keeping the old
  locality tag) is the #4089 reporter's account and was not checked here.

## Deviations and corrections (left visible)

- The September plan specified a 13-line source patch on main commit `a2f0c6d`. This run used a file edit on the
  7.3.63 release instead. Reason: the build was the blocker.
- The amendment said the construction would not replay #4089 exactly, because the workload hardcodes region IDs
  "0" and "1". That was wrong for two-datacenter clusters: the restart code configures regions with the new names.
- Both trace signatures fixed in advance were non-specific. The finding rests on storage-server disposal counts
  and restart outcomes.
- Run 1's first recoverability check could not separate destroyed data from a naming mismatch. A corrected arm
  (restart with names matching the stored configuration) was added before it was run; it failed on 7 of 7.
- Run 2's first launch was interrupted after about two minutes and relaunched from seed 9100. No output of the
  interrupted launch was read. The simulation is deterministic per seed.
- Run 3's screening was cut off once by a command time limit and rerun unchanged. Screening runs phase 1 only.
  Two-datacenter rate: 71 of 400 seeds.
- The pre-run hashes in `HASHES_BEFORE_RUN.txt` were recorded in the working session. They are not externally
  timestamped. `EXPLORATORY_PHASE3.md` no longer matches its recorded hash, because the correction section was
  appended to it after hashing; every other hashed file still matches.

## Reproduce

Linux, about two hours on two cores. Scripts use fixed paths `/tmp/cs2` and `/tmp/fdbbin`.

```bash
mkdir -p /tmp/fdbbin /tmp/cs2 && cd /tmp/cs2 && unzip <path>/cs2_step3_bundle.zip
curl -L -o /tmp/fdbbin/fdbserver.7.3.63 https://github.com/apple/foundationdb/releases/download/7.3.63/fdbserver.x86_64
chmod +x /tmp/fdbbin/fdbserver.7.3.63 && sha256sum /tmp/fdbbin/fdbserver.7.3.63   # compare with HASHES_BEFORE_RUN.txt
mkdir -p run3 && cat run3_seeds.txt | xargs -P 2 -I{} sh -c 'scripts/run2_one.sh {} > run3/row_{}.json'
cat run3/row_*.json > run3_rows.jsonl && python3 scripts/score3.py
```

## Files in the bundle

Plans: `CS2_STEP3_AMENDMENT.md`, `EXPLORATORY_PHASE3.md`, `CONFIRMATION_RUN2.md`, `CONFIRMATION_RUN3.md`,
`HASHES_BEFORE_RUN.txt`. Results: `summary.csv`, `run1_score.txt`, `run1_phase3_rows.csv`,
`run1_phase3_dc_keep_rows.csv`, `run2_rows.jsonl`, `run2_score.txt`, `screen3.json`, `run3_seeds.txt`,
`run3_rows.jsonl`, `run3_score.txt`. Evidence: key trace events for the 7 run-1 deletion seeds. Harness: `scripts/`,
`tests/`. Full trace files (about 15 GB) are not included; they regenerate from the seeds.

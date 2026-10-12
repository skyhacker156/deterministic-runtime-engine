# FoundationDB Case Study — Frozen

**Status:** frozen at the current evidence boundary. The full FDB rebuild
is not pursued under present resource constraints (1 CPU core, ~3.8GB
RAM — confirmed insufficient via direct measurement against the actual
464-file dependency chain and the 16,106-line file the construction
would need to touch, per `FOUNDATIONDB_F3D_REBUILD_DECISION.md`).

## What is established, real, and decisive

- **F-1a/F-1b** (`FOUNDATIONDB_ATTACK_001_F1_DETERMINISM.md`): the real
  `fdbserver 7.4.6` simulator produces byte-identical output under a
  fixed seed, confirmed under genuine CPU contention — narrowed
  explicitly to the tested workload/seed, not generalized.
- **F-2a/F-2b** (`FOUNDATIONDB_ATTACK_002_F2_FAULT_SCHEDULE.md`): the
  fault schedule itself (not just aggregate output) is deterministically
  reproduced; `-fi off` produced no observable difference for the tested
  workload — reported honestly as a null-ish result, not forced into a
  more dramatic claim.
- **F-3 decomposition** (`FOUNDATIONDB_F3_DECOMPOSITION.md`): real source
  read directly — `ConsistencyCheck`'s core comparison is cross-replica
  agreement, not comparison against an independently-derived ground
  truth.
- **F-3b oracle inventory** (`FOUNDATIONDB_F3B_ORACLE_INVENTORY.md`): a
  systematic search across five candidate oracle categories found no
  genuine independent correctness oracle for application-level data.
- **F-3c** (`FOUNDATIONDB_F3C_SIMULATOR_CAPABILITY.md`): no existing
  simulator mechanism found that corrupts a mutation before replica
  fan-out.
- **F-3d** (`FOUNDATIONDB_F3D_REBUILD_DECISION.md`): rebuild infeasibility
  confirmed via direct measurement, applying the pre-registered decision
  rule exactly; a second, independent existing-hook search confirmed
  `F-3c`'s finding via `StorageCorruption.actor.cpp` (real, but
  per-replica-independent, not the shared-corruption shape needed).

## What remains explicitly unresolved

**The correlated pre-replication corruption proposition — would
`ConsistencyCheck` accept identical incorrect state arising deterministically
across all replicas — is preserved as experimentally untested, not
resolved by inference or by a weaker substitute construction.** This is a
real, honest limitation, stated precisely rather than glossed over.

`F-4` (recovery), `F-5` (simulation/production correspondence), and `F-6`
(what deterministic simulation actually justifies) were never
constructed.

## Available, not conflated with what's untested

The independent-corruption control (`StorageCorruption.toml`) remains
runnable without any rebuild, should this case study be revisited — kept
distinct from the untested shared-corruption proposition in all prior
documents.

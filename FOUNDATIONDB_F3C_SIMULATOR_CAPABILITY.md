# F-3c — Can the Existing Simulator Generate a Correlated Replica Fault?

**Status:** decomposition, grounded in real source search of FoundationDB
`7.4.6`. No code modification. No rebuild. Answers the precise
pre-registered question before any construction: can unmodified
FoundationDB, driven only by its existing simulator fault model, be made
to produce a scenario where multiple replicas deterministically converge
on the *same incorrect* state — as opposed to independent, uncorrelated
divergence (which `ConsistencyCheck` would already catch, per
`FOUNDATIONDB_F3_DECOMPOSITION.md`)?

## Method

Searched real source for every `BUGGIFY`-gated fault-injection point in
the three layers most relevant to whether a fault could affect *many
replicas identically* versus *one replica independently*: the storage
server layer (where replicas actually live), and the two layers upstream
of replica fan-out — the commit proxy and the transaction log, where a
single fault touching the *shared* mutation stream, before it is
replicated out, could plausibly propagate identically to every replica
that receives it.

## What was found

**Storage server layer (`storageserver.actor.cpp`):** numerous real
`BUGGIFY`/`BUGGIFY_WITH_PROB` calls exist, but each runs **within its own
simulated process's independent execution**, evaluated against that
process's own position in its own deterministic random stream. Structurally,
this means a `BUGGIFY`-triggered event at this layer affects *one*
storage server's own behavior — there is no mechanism found here by
which the same `BUGGIFY` draw is shared across multiple replicas'
processes. This argues against, not for, correlated corruption
originating at this layer.

**Commit proxy and transaction log layers (`CommitProxyServer.actor.cpp`,
`TLogServer.actor.cpp`):** real `BUGGIFY` calls found here are
predominantly **timing and threshold perturbations** — delay durations,
memory limits, batch-size thresholds (e.g., `BUGGIFY ?
SERVER_KNOBS->BUGGIFY_TLOG_STORAGE_MIN_UPDATE_INTERVAL`, spill thresholds,
recovery memory limits). No fault-injection point was found in this
search that corrupts a mutation's **value** upstream of replication —
the closest structural candidate for producing correlated identical
corruption across replicas via unmodified code.

**The one direct "corrupt the data" hit found (`IPager.cpp`, line ~65):**
read in full context, this is a **unit test** — it deliberately flips a
bit in a single page, then asserts that the checksum mechanism correctly
throws a decoding-failure error. It confirms the local page-checksum
detector (already classified in `FOUNDATIONDB_F3B_ORACLE_INVENTORY.md`
as a real but narrow-scope, single-machine integrity check) works as
designed. It is not a general-purpose, live-simulation fault-injection
hook usable to corrupt data flowing through a real running simulated
cluster.

## The result

**No existing simulator mechanism was found, in this search, that
operates on the mutation stream before replica fan-out in a way that
would deterministically produce identical incorrect data across multiple
replicas.** Value-corruption-related code found either operates
per-process at the storage-server layer (after fan-out, hence
independent per replica) or is a local unit test of the corruption
*detector*, not a fault-injector usable against a live simulated cluster.

**Stated with the precision this search earns, per the standing
discipline of this whole case-study series:** this is real evidence
toward "no," not proof of "no." The search covered the three most
structurally relevant files by name and reasoning, not the entire
mutation pipeline (the Resolver, wire-protocol encoding/decoding, and
other commit-path files were not exhaustively searched). A correlated-
corruption fault-injection point could exist elsewhere and not have
surfaced in this pass.

## What this means, per the pre-registered decision rule

Per the hierarchy set before this construction began: **F-3c's answer, as
found, is "not found via the existing simulator's fault model, in this
search."** This is itself a real, reportable result — it suggests the
hypothesized correlated-corruption failure mode may be structurally
difficult to produce under FoundationDB's normal, unmodified fault model,
at least via the mechanisms searched. Per the pre-registered plan, this
means: **minimal, microscopic, auditable source-level fault injection is
the next step if this proposition is to be tested further** — not because
the search failed to look hard enough to justify skipping the "try
unmodified first" step, but because that step was genuinely attempted,
genuinely came back empty-handed within its search scope, and the
pre-registered decision rule for exactly this outcome was to proceed to
minimal source modification, deliberately, rather than either abandoning
the question or forcing a heavier construction than the evidence yet
justifies.

## Explicitly not done

No source modification. No rebuild. No live simulation run in this pass
— this is a pure source-search decomposition, matching the discipline
applied throughout this whole series before any construction. The
Resolver and wire-protocol layers were not searched — named explicitly as
gaps in this search's coverage, not silently omitted. Whether a minimal,
auditable fault injection is worth pursuing next is a decision for
whoever reviews this finding, not decided here.

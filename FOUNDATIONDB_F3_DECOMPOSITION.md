# F-3 Decomposition — Independence of the Consistency-Checking Layer

**Status:** mechanism decomposition, grounded directly in real
FoundationDB `7.4.6` source code (`fdbserver/workloads/ConsistencyCheck.actor.cpp`)
and real official documentation (`documentation/sphinx/source/auditstorage.rst`,
both from the cloned `apple/foundationdb` repo at the matching tag) — not
inference, not documentation summary alone. No live construction in this
pass; the source-level finding is decisive enough to report on its own,
and a full live demonstration would require rebuilding FoundationDB from
source with a deliberately introduced shared-replica bug — a
substantially heavier undertaking than anything else in this case study,
flagged explicitly at the end rather than silently attempted or silently
skipped.

## The question, precisely, per instruction

Not "does FoundationDB check consistency" (confirmed already, `F-3` in
the evidence baseline). The sharper question: **does the
consistency-checking/invariant machinery provide an independent
observation layer over deterministic execution, or does it check using
substantially the same state/mechanisms that produced the behavior?**
This is the direct FoundationDB analogue of Phoenix A's `CI-005` finding
(reproducibility ≠ correctness) and the oracle-independence question this
whole series of case studies has returned to repeatedly.

## What the real source shows — `ConsistencyCheck.actor.cpp`

The core comparison, read directly (lines ~640–753): for a given shard,
the workload reads the same key range from every storage server holding
a replica of that shard (`iter_ss[j]` for each server `j`). The **first**
server's response is designated `reference`. Every subsequent server's
response (`current`) is compared **against that first server's
response** — key by key, value by value — and any mismatch is logged as
`CacheConsistencyCheck_DataInconsistent`.

**This is a cross-replica agreement check, not a comparison against an
independently-derived ground truth.** There is no re-derivation of "what
this key's value *should* be" from a separate source (such as the
transaction log's committed mutation history, or a maintained checksum
computed independently of the storage-server read path) — the check
asks only "do the copies agree with each other," never "do the copies
agree with what was actually committed."

## What the real documentation confirms — `AuditStorage`

FoundationDB has a second, newer consistency-checking mechanism,
`AuditStorage`, documented directly (not inferred): its `replica` audit
type is described in the official design doc as checking **"the
consistency of user data between replicas of all DCs"** — the same
structural pattern as `ConsistencyCheck`'s comparison, confirmed by the
tool's own stated purpose, not merely by analogy.

**A genuinely different, more independent check does exist, and is worth
preserving precisely rather than flattening into a single verdict:**
`AuditStorage`'s other two modes — `locationmetadata` and `ssshard` —
compare **two different subsystems' independently-recorded state**
against each other: `KeyServer` metadata (in the system key space)
against `ServerKey` metadata, and `ServerKey` metadata against each
storage server's own local shard mapping. This is structurally different
from replica-vs-replica comparison — it is one record of "what should be
where" checked against a *different* record of the same fact, maintained
through a different path. Whether this constitutes genuine independence
in the `CI-005` sense (two mechanisms that could diverge under a shared
bug) or merely a different kind of shared-assumption check was not
determined in this pass — flagged as the natural next decomposition
question, not resolved here.

## The finding, stated at the precision this evidence earns

**For the specific, load-bearing question "is this key's stored value
correct" — as distinct from "is the location metadata self-consistent" —
FoundationDB's primary consistency-checking mechanisms (`ConsistencyCheck`
and `AuditStorage`'s `replica` mode) check replica agreement, not
independent derivation from a separately-maintained source of truth.** A
bug that caused every replica of a shard to receive or store the same
incorrect value — for instance, a bug in the shared mutation-application
logic applied identically and deterministically across all replicas —
would, per this source-level reading, produce full agreement across every
replica and would not be flagged by either mechanism's core comparison
logic.

This is not evidence of a defect — replica-agreement checking is a real,
useful, and standard technique, and detecting a *particular class* of
corruption (a replica silently diverging from its peers) is exactly what
it is designed for and does. The finding is narrower and more precise:
this specific, common form of consistency checking does not, by
construction, provide independent observation of correctness in the
`CI-005` sense — it provides independent observation of *replica
divergence*, a different and narrower property.

## What would be needed to demonstrate this live, and why it wasn't
   attempted in this pass

A full adversarial demonstration — analogous to `CI-005`'s real,
constructed shared-regression proof in Phoenix A — would require
introducing a deliberate bug into FoundationDB's own mutation-application
or replication code such that all replicas of a shard receive an
identical, incorrect value, then confirming `ConsistencyCheck` reports no
inconsistency. This requires **rebuilding FoundationDB from source**,
including its custom Flow-to-C++ actor compiler and the full CMake/Boost
toolchain — a substantially heavier lift than any construction in this
case study so far (Temporal's constructions needed only `go build`
against a pre-built SDK; this would need a full C++ compile of a large,
unfamiliar codebase). **Not attempted in this pass.** Flagged explicitly
as a real, deliberate scope boundary — not silently skipped, and not
claimed as done when it wasn't.

## Explicitly not done

No live simulation run in this pass — this is a source-and-documentation-level
decomposition only, matching the discipline applied to `T-4a`/`T-6a`
before their own constructions. `checkDataConsistency` (a second,
related function referenced in the same file, not yet located and read)
was not traced further — the core comparison logic already found is
decisive enough for this finding without it. `F-4`, `F-5`, `F-6`
untouched.

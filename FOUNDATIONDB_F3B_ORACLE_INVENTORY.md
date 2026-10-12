# F-3b — Independent Oracle Inventory

**Status:** systematic decomposition, grounded directly in real
FoundationDB `7.4.6` source code. No construction, no rebuild. This
answers the precise question posed: does *any* mechanism in FoundationDB's
verification stack establish correctness independently of the state being
checked — not limited to `ConsistencyCheck`, and not assuming the answer
is no just because `ConsistencyCheck` isn't one.

## Method

Searched the real source tree for every checksum, digest, cross-subsystem
comparison, and log-derived-reconstruction mechanism findable by name and
usage pattern, then read each candidate's actual code to classify it —
not merely noted its existence.

## Candidates found and classified

### 1. `AsyncFileWriteChecker` (`fdbrpc/AsyncFileWriteChecker.cpp`)

A per-page checksum (`WriteInfo`, LRU-cached) computed by the storage
engine at write time and compared against a freshly-computed checksum at
read time. **Classification: real, but narrow-scope.** This detects
local disk corruption (bit rot, torn writes) on the machine that wrote
the page — a genuine integrity check — but the checksum is computed by
the *same* process, from the *same* data, at write time, and compared by
essentially the *same* code path at read time. It verifies "did this
byte sequence survive intact on this disk," not "was this the correct
value to have written in the first place." A bug that caused the wrong
*correct-looking* value to be written would pass this check every time —
this mechanism was never designed to catch that class of error, and
correctly doesn't claim to.

### 2. `DiskQueue`'s page checksum (`fdbserver/DiskQueue.actor.cpp`)

The transaction log's own durable write-ahead structure. Read directly:
`checksum_crc32c()`, `checksum_xxhash3()`, and `checksum_hashlittle2()`
are all computed **over the page's own content**, stored alongside it,
and re-verified against a freshly-recomputed checksum on read.
**Classification: identical in kind to #1** — a local, self-referential,
write-then-verify-own-integrity check. Real, useful, and protects against
a genuinely different failure class (storage-media corruption) than
application-level correctness.

### 3. `AuditStorage`'s `locationmetadata` and `ssshard` modes
   (`documentation/sphinx/source/auditstorage.rst`)

Confirmed directly from the official design doc: these compare **two
different subsystems' independently-recorded state** — `KeyServer`
metadata (system key space) against `ServerKey` metadata, and
`ServerKey` against each storage server's own local shard mapping.
**Classification: genuinely different in structure from `ConsistencyCheck`**
— this is not replica-vs-replica, it is record-vs-different-record. This
is real cross-subsystem comparison. **What it verifies, precisely
stated:** whether the system's own bookkeeping about *where data lives*
is internally consistent across the places that bookkeeping is
independently maintained. **What it does not verify:** whether the
*data itself*, once you've found the right replica, holds the value that
was actually committed — that remains `ConsistencyCheck`'s and
`AuditStorage`'s `replica` mode's territory, already classified in
`FOUNDATIONDB_F3_DECOMPOSITION.md` as replica-agreement, not independent
derivation.

### 4. Transaction-log-derived state reconstruction (recovery)

Checked directly against `recovery-internals.md` and the real recovery
mechanism it describes: the Cluster Controller computes a
`knownCommittedVersion` and a `recoveryVersion`, and recovery **copies**
mutation data from old transaction logs to a newly recruited set, for
versions between those two bounds, to restore the configured replication
factor. **Classification: the transaction log is genuinely authoritative
here — but as a *source* state is derived *from*, not as an independent
*check* against already-derived state.** Storage servers pull mutations
from the log and apply them; recovery re-copies log data to repair
replication. No mechanism was found, in this search, that takes a storage
server's *existing* state and independently verifies it against what the
transaction log says it should be — the log is upstream of storage-server
state by construction, not a separate oracle checking it after the fact.

### 5. Cryptographic commitments

No cryptographic hash-chain or commitment scheme analogous to Phoenix A's
`provenance_hash`/`decision_hash` pattern was found anywhere in this
search, applied to application-level data correctness. `BlobCipher.cpp`
and `EncryptUtils.h` exist and handle encryption-at-rest — a genuinely
different property (confidentiality) than correctness verification, not
a candidate oracle for this question.

## The inventory's conclusion

**No genuine independent correctness oracle for application-level data
correctness was found anywhere in this search.** Every real checksum
mechanism found (`AsyncFileWriteChecker`, `DiskQueue`'s page checksums)
protects against local storage-media corruption via a
self-referential write-then-verify pattern — not independent derivation.
The one genuinely independent cross-subsystem comparison found
(`AuditStorage`'s `locationmetadata`/`ssshard` modes) verifies
*bookkeeping consistency about where data lives*, not *whether the data
itself is correct*. The transaction log is authoritative as a source of
truth that state is derived from, but no mechanism was found that
independently re-checks derived state against it after the fact.

**Stated at the precision this inventory earns — this is a search
result, not a proof of absence:** this does not prove no independent
oracle exists anywhere in a codebase of FoundationDB's size — it reports
what a systematic, source-grounded search for the candidate categories
named (checksums, log-derived reconstruction, cross-subsystem invariants,
cryptographic commitments, independently reconstructed state) actually
found. A mechanism outside these searched categories, or one not
discoverable by the naming/usage patterns searched, could exist and would
not appear here.

## Why this justifies the expensive live construction

Per the framing that motivated this inventory: if a genuine independent
oracle had been found, the FoundationDB case study would need to route
around it rather than construct a "gotcha" against a check that was
never claimed to be independent. **None was found**, across a real,
systematic search of the most likely candidate mechanisms. This gives the
live construction (rebuilding FoundationDB with a deliberately shared
replica bug, to directly demonstrate `ConsistencyCheck`'s blind spot) a
precise, now well-evidenced proposition to test — not merely an attempt
to manufacture a failure, but the natural next step given what this
inventory actually found.

## Explicitly not done

No live construction, no rebuild. This inventory does not exhaustively
cover FoundationDB's entire codebase — it covers the candidate categories
named in the question, searched systematically and read in context, not
guessed at. `F-4`, `F-5`, `F-6` untouched.

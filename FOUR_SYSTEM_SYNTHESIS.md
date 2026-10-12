# Four-System Synthesis: What Does Each Oracle Actually Establish?

**Status:** Ethereum frozen at `E-003`. This document supersedes the
three-system version's blunter "blind spot" language with the four
categories below, and re-classifies every prior finding across all four
systems against them. No new construction.

**The final question this document answers:**

> Across Temporal, FoundationDB, Raft, and Ethereum, when a system
> claims to "verify correctness," what exactly is its oracle capable of
> establishing independently, and what correctness claims are instead
> inherited from the system's inputs, participants, specification, or
> prior computations?

---

## The four categories, replacing "blind spot"

1. **Unobserved behavior** — something real happens, and the verification
   mechanism never sees it at all. Not wrong, not right — absent.
2. **Causal ambiguity** — the resulting state *is* observed, but what
   produced it is not. Two different real causes look identical to the
   verifier.
3. **Agreement without external validation** — the verifier confirms
   that participants agree with each other (or with a majority), not
   that the agreed value corresponds to anything outside the system.
4. **Independent derivation** — the verifier reconstructs the claimed
   result itself, from its own computation, and can therefore genuinely
   reject a disagreement. The positive control case.

Every real finding across all four case studies is re-classified below.
Category 4 is included deliberately, not as an afterthought — `E-003`
proved it's a real, reachable category, not a theoretical ideal no real
system achieves.

---

## Temporal

| Finding | Category | Note |
|---|---|---|
| Command *kind and position* match original execution (`TA-001`, `TA-002`) | **4** | Replay genuinely re-executes and compares — a real independent derivation, for this narrow slice |
| Command *content* (`TA-003`, `TA-005`) | **1** | Argument content is never inspected by the comparison mechanism at all — not merely disagreed with, absent from consideration |
| Signal payload content (`TA-008`) | **1** | Same shape as Command content — trusted verbatim, never independently re-verified |
| Live recovery vs. explicit `WorkflowReplayer` testing (`TA-006`/`TA-007`) | **1**, for the live path specifically | The identical divergence was invisible to live recovery while fully caught by explicit testing — the *same* mechanism has a real observation gap depending on invocation path |

## FoundationDB

| Finding | Category | Note |
|---|---|---|
| `ConsistencyCheck` / `AuditStorage` replica comparison | **3** | Confirmed directly from source: compares replicas to each other, not to an independently-derived ground truth |
| `AsyncFileWriteChecker` / `DiskQueue` page checksums | **4**, narrowly scoped | A real independent-derivation check — but only for "did this byte sequence survive on disk," not "was the value correct to begin with" |
| `AuditStorage`'s `locationmetadata`/`ssshard` modes | **4**, for metadata placement specifically | Genuine cross-subsystem comparison — independent in structure, but scoped to *where data lives*, not *whether the data is correct* |
| Correlated pre-replication corruption proposition | **3**, hypothesized, unconfirmed (Level B evidence) | Never empirically demonstrated live — the rebuild was judged disproportionate; remains a real, source-grounded but untested claim |
| Simulation/fault-schedule determinism (`F-1`, `F-2`) | *not a verification-boundary finding* | A precondition for verification (reproducibility), not itself an instance of any of the four categories |

## Raft

| Finding | Category | Note |
|---|---|---|
| `R-1`–`R-5` core safety properties, as enforced (`isUpToDate`, `matchTerm`/`findConflict`, `maybeCommit`'s term gate) | **4** | Confirmed directly from source — these are genuine independent checks that reject a bad value, not vote-counting. **This is an important, previously under-emphasized parallel to Ethereum's `E-003`**: Raft's *core*, formally-proven properties have real Category 4 enforcement |
| PreVote, ReadIndex, leadership-transfer *messages* (`RA-002` through `RA-006`) | **1** | Confirmed empirically, on a corrected production harness, real execution + real TLC: entirely absent from the trace/model, and validation succeeds with 100% progress despite their occurrence |
| `CheckQuorum`-triggered stepdown | **2** | The resulting `BecomeFollower` transition *is* traced — but `traceEvent`'s own fields record only the resulting state, not the cause; a quorum-loss stepdown is trace-identical to any other |
| The resulting election after a leadership transfer | **2**, layered on top of the transfer messages' own Category 1 | The election itself is fully traced, but indistinguishable from an accidental one — an observed effect with an invisible cause, exactly matching Category 2's definition |

**The Raft parallel to Ethereum, stated precisely:** Raft's formally-specified,
paper-proven core (election safety, log matching, commit rules) has real
Category 4 enforcement — independent derivation, genuine rejection. Its
*extensions beyond the base algorithm* (PreVote, ReadIndex, transfer,
CheckQuorum) fall into Categories 1 and 2. This is structurally the same
split Ethereum exhibits between state-root verification and `eth1_data`
— **the pattern is not "Raft has a weaker oracle than Ethereum," it is
"both systems draw the same kind of line between their formally-core
mechanisms and their layered extensions,"** independently arrived at by
two unrelated engineering teams.

## Ethereum

| Finding | Category | Note |
|---|---|---|
| `eth1_data` acceptance (`E-001`) | **3** | Confirmed by real execution against the actual reference implementation: majority-agreement is sufficient by the specification's own design; no independent re-derivation exists anywhere in the acceptance path |
| Execution-layer state-root verification (`E-003`) | **4** | Confirmed by real execution against the actual `ethereum-execution` package: a genuinely wrong-but-well-formed claim was rejected, because the mechanism truly recomputes and compares |
| Attestation content (`E-002`, item 2) | **3** | Signature verifies authenticity of the voter; the attested content itself is not independently re-derived by the function that counts it |
| Fork choice head selection (`E-002`, item 3) | **3**, operating over a Category-4-filtered candidate set | Pure weighted vote count on its own terms — but only among blocks that already survived independent state-transition validation upstream; the two mechanisms compose |
| Finality (`E-002`, item 4) | **3**, inferred only, not independently confirmed | Flagged honestly as unconfirmed by direct source reading — should not be cited with the same confidence as the other Ethereum findings |

---

## The sharpened synthesis

**Every system studied contains multiple categories simultaneously — none
is purely one thing.** This is the real refinement Ethereum forced: the
original three-system framing risked reading as "each system has *a*
blind spot." The four-category breakdown shows every system has a
*profile* — a specific, inspectable distribution across all four
categories, not a single verdict.

**Two systems (Raft and Ethereum) show the same structural split
independently:** a formally-specified, provably-correct core with real
Category 4 enforcement, surrounded by extensions that fall into
Categories 1–3. This did not need to be true — Raft's designers and
Ethereum's designers solved unrelated problems decades apart, in
different languages, for different purposes, and arrived at the same
shape of boundary between "the part we formally verify" and "the part we
extended pragmatically." That convergence is more informative than any
single system's finding on its own.

**`E-001` and `E-003` together demonstrate that the difference is oracle
design, not system identity, exactly as instructed.** The same
architecture, the same team, adjacent mechanisms — one deliberately
agreement-only, one deliberately independent. This rules out the reading
that "some systems just have better verification than others" — the
right unit of analysis is the individual acceptance boundary, not the
system as a whole.

## What this establishes, at the precision the evidence earns

Restating `CROSS_CASE_SYNTHESIS.md`'s Level C proposition with the
four-category refinement folded in:

> A verification mechanism's assurance is bounded by what it was built
> to observe, and that boundary takes one of (at least) four
> recognizable shapes — unobserved behavior, causal ambiguity, agreement
> without external validation, or genuine independent derivation — often
> multiple shapes within the same system, at different points, by
> deliberate design rather than uniform oversight.

This remains Level C (generalized interpretation) — a pattern extracted
from Level A (empirically demonstrated) findings across four systems,
not itself a fifth empirical measurement. Whether a fifth, sixth
architecture would reveal a category not yet seen here is a genuinely
open question this document does not claim to close.

## Explicitly not done

No new construction. Finality (Ethereum item 4) and the correlated-corruption
proposition (FoundationDB) remain at Level B — real, source-grounded,
not empirically confirmed — and are not promoted to Level A by inclusion
in this synthesis table.

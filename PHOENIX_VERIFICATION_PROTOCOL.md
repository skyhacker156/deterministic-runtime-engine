# Claim-Bounded Verification: A Reproducible Protocol for Deterministic Execution Architectures

**Status:** protocol extraction, not a validated general methodology. This
document generalizes the discipline applied to Phoenix A across 19 traced
claims into a stated, reusable sequence, then checks each step against
real prior art before making any claim about what, if anything, is new.
That check follows the same standing discipline the Phoenix A campaign
applied to itself throughout — construct or cite before asserting, name
overclaims precisely, don't let a compelling narrative substitute for
checked evidence.

---

## The protocol

**1. Claim extraction.** Turn architectural documentation into atomic,
individually falsifiable guarantees. Not "the system is secure" but "the
Bridge→Kernel transformation has exactly one implementation."

**2. Enforcement classification.** For each atomic claim, identify how —
if at all — it is enforced: formal proof, structural mechanism, behavioral
test, oracle-independent verification, absent, or explicitly excluded
(and if excluded, whether that exclusion is itself proven, deliberate, or
merely undecided).

**3. Bounded adversarial construction.** Construct the smallest object or
workload capable of violating the claim — not the most elaborate attack
available, the minimal one that isolates the specific property under
test.

**4. Reachability analysis.** For any violation found, classify it:
currently reachable through the system's real, sanctioned entry points;
unreachable by construction (blocked by something incidental, not
designed); reachable only through a future extension not yet built; or
genuinely unknown.

**5. External workload testing.** Introduce inputs whose values,
distributions, and edge cases were derived from an independently-written
specification, not from the implementation's own test fixtures or
internal assumptions.

**6. Independent reproduction.** Reproduce the result that matters most
using an implementation that does not import, and was not derived from,
the code under test — a genuinely separate oracle, not a second run of
the same logic.

**7. Claim calibration.** Rewrite the architectural claim to state exactly
what the evidence supports — narrower where the evidence demands it, and
explicitly not "fixed" merely because a gap between claim and reality was
found. Narrowing the claim and correcting the implementation are both
valid outcomes; the protocol does not presuppose which one applies.

---

## Prior art, mapped step by step

**Step 1 (claim extraction) and step 7 (claim calibration), together, are
the shape of an established field: argument-based assurance cases** —
Goal Structuring Notation (GSN), the Claims-Arguments-Evidence (CAE)
notation, and the ISO/IEC/IEEE 15026 series. Decomposing a top-level claim
into falsifiable sub-claims backed by evidence, in a form a third party
can challenge, has been standard practice in aerospace, rail, nuclear, and
medical-device certification for decades. What's less commonly emphasized
in that literature, and worth naming precisely rather than claiming as
new: assurance cases are typically built to support a claim, with
evidence gathered to strengthen it. This protocol's step 7 treats
*narrowing* the claim as an equally valid, equally first-class outcome —
several of the traced findings below ended not in a fix but in a
rewritten, more accurate claim.

**Step 2's enforcement taxonomy** (formal / structural / behavioral /
oracle-independent / absent / excluded) has clear precedent in the same
assurance-case literature's evidence typing, and in software assurance
levels more broadly (e.g. DO-178C's design assurance levels, which
distinguish formal analysis, structural coverage, and test-based
evidence). The specific six-way split used here, and particularly the
three-way subdivision of "excluded" into proven-impossible /
deliberately-traded-away / genuinely-undecided, is a refinement rather
than an invention — but a real one, since collapsing those three into one
"out of scope" bucket is exactly the kind of imprecision this protocol
exists to avoid.

**Step 3 (bounded adversarial construction)** is closely related to
established minimization practice in mutation testing, fuzzing, and
property-based testing (e.g. QuickCheck-style shrinking to a minimal
failing case) — not a new technique on its own.

**Step 4 (reachability analysis)** has direct precedent in security
practice — reachability and exploitability triage in taint analysis and
vulnerability assessment routinely distinguish "reachable from an
untrusted entry point" from "present in code but unreachable." Applying
the same discipline to architectural claims generally, not only to
security vulnerabilities specifically, is the generalization made here.

**Step 5 (external workload testing)** is a form of differential and
black-box testing against inputs not derived from the implementation —
an established practice, not a new one.

**Step 6 (independent reproduction)** is the most directly and precisely
matched to existing literature: this is **the test oracle problem**,
named and studied since at least Chen et al.'s introduction of
metamorphic testing, and the subject of a substantial, decades-deep body
of work specifically because an implementation's own tests confirming its
own behavior is a well-recognized, well-named failure mode — not a new
observation. `CI-005` and `EW-004` demonstrated this concretely inside a
running system rather than discussing it abstractly; the demonstration is
real, but the underlying concern is not new.

---

## Honest novelty assessment

**None of the seven steps is individually novel.** Several are decades
old and formalized in mature, cited literature. A claim that this
protocol invents new verification techniques would not survive the
comparison above, for the same reason Candidate C in
`PHOENIX_RESEARCH_CLAIM_ASSESSMENT.md` did not survive it.

**What is plausibly distinctive, stated at the scope it actually earns:**
the specific integration of all seven steps into one sequenced protocol,
applied to a *specific, narrower system class* — deterministic,
hash-chained, replay-verifiable execution architectures, where "does
reproducibility equal correctness" and "does delegation equal
verification" are live, concrete, checkable questions rather than
abstract concerns. General assurance-case methodology targets safety
broadly; general metamorphic testing targets the oracle problem broadly;
neither, as far as this search found, combines both with an explicit
reachability step and an external-workload step in one fixed sequence
aimed specifically at systems built around cryptographic hash chains and
replay guarantees.

**This is an integration claim, not an invention claim**, and it is
validated by exactly one case study. `PHOENIX_RESEARCH_CLAIM_ASSESSMENT.md`
already names the four concrete instances where following this sequence
changed a conclusion `VERIFIED`/tests-passing status would have hidden
(`CI-002`, `CI-003`, `CI-005`, `EW-004`). That is real evidence the
protocol, as sequenced, has value — for one system, applied by the people
who built its own verification apparatus.

---

## What this document does not establish

Not that the protocol generalizes beyond Phoenix A. Not that another team,
applying it to a different deterministic execution system, would find
comparably interesting results — that is untested and would require
exactly the kind of independent application this protocol's own step 6
insists on for individual results. Not that the specific six-way
enforcement taxonomy or the three-way exclusion subdivision is the
correct or only useful classification scheme — it is one that worked here.

**The research question this document actually poses, stated precisely:**
does this specific seven-step sequence, applied by a party other than the
one that built both the system and the protocol, to a deterministic
execution architecture other than Phoenix A, produce comparable
discovery of the gap between documented claims and actual enforcement? That
question is not answered here, and answering it would require the
protocol to leave this project — the one test this document cannot
perform on itself.

---

## Case studies

**Case Study 1: Phoenix A.** Frozen here. 19 claims traced
(`CI-001`–`CI-005`, `EW-001`–`EW-004`), full evidence in
`ADVERSARIAL_METHODOLOGY.md` and `VERIFICATION_COVERAGE_MATRIX.md`,
classification summary in `GUARANTEE_MATRIX.md`, research-claim framing in
`PHOENIX_RESEARCH_CLAIM_ASSESSMENT.md`. Four concrete instances where
following this sequence changed a conclusion conventional "tests pass /
VERIFIED" reporting would have hidden: `CI-002`, `CI-003`, `CI-005`,
`EW-004`. This is the protocol's only validation to date, applied by the
same party that built both the system and the protocol.

**Case Study 2: FoundationDB — partial application.** Selected 2026-09-09.
Steps 1, 2 and 4 were done from FoundationDB's paper, documentation and
source (2026-09-09, 2026-09-28). Step 3 was executed on 2026-10-11 against
the official 7.3.63 release binary. Step 5 was substituted and step 6 was
not performed. Applied by the same party that wrote this protocol. An
earlier study of FoundationDB (August 2026, release 7.4.6) asked a
different question, what its oracles establish independently, under the
four categories of `FOUR_SYSTEM_SYNTHESIS.md`. It is used below as
evidence for `C1a` and `C3` and is not itself an application of the seven
steps. The sections above this one were written before this entry and are
left as written; "validated by exactly one case study" and "the protocol's
only validation to date" were true when written.

Selection criteria, stated in advance and kept verbatim:

- genuinely deterministic execution (same input → same output, verifiably)
- persistent, replayable state
- cryptographic or integrity-relevant artifacts (hash chains, signatures,
  Merkle structures, or equivalent)
- meaningful architectural claims stated in the project's own
  documentation — something with a real `VERIFIED`/"guaranteed" surface to
  extract claims from, not a toy
- enough real complexity to have seams — multiple modules, a real seam
  between ingestion and execution, something analogous to Phoenix A's own
  Bridge→Kernel boundary
- a **different implementation philosophy** from Phoenix A — different
  language, different domain, different design lineage, not a
  reimplementation or close relative of anything already examined here

**Fit against those criteria.** Five are met. One is met only loosely:
FoundationDB's integrity artifacts are page and disk-queue checksums, not
hash chains or signatures. It is a deterministic-simulation system, which
puts it at the edge of the "hash-chained, replay-verifiable" class named
in the novelty assessment above, not inside it. The different-philosophy
criterion is met plainly: C++ and Flow, a distributed database, and
deterministic simulation of a whole cluster in place of replay of recorded
decisions. Runner-up considered: Ethereum, not chosen because
independent-client state-root convergence is already its well-studied
headline claim.

**Step 1 — claims extracted** from the SIGMOD 2021 paper and the project's
testing documentation:

| ID | Claim |
| --- | --- |
| `C1a` | The same seed produces the same simulated run |
| `C1b` | The simulated network, disk, process and clock fault model stands in for real hardware failure |
| `C2` | The same server code runs in simulation and in production, with only the I/O interfaces swapped |
| `C3` | Test oracles (workload invariants and assertions) verify the database's contracts |
| `C4` | Every feature is tested under a wide range of faults (a breadth claim, not a completeness claim) |

**Step 2 — enforcement classification.**

| ID | Classification | Basis |
| --- | --- | --- |
| `C1a` | Structural, plus a sampled behavioral check | Single-threaded Flow execution. The test harness re-runs a sample of seeds and compares the final "unseed" (`contrib/TestHarness2/test_harness/run.py:570–611`, read at tag 7.3.63). Line 580 of that file reads "FIXME: support unseed checks for restarting tests". Executed in August 2026: `fdbserver` 7.4.6 gave byte-identical output and an identical fault schedule under a fixed seed, including under CPU contention, for the tested workload and seed (`F-1`, `F-2`) |
| `C1b` | Behavioral inside simulation; no independent anchor available to this study | The documentation names "hardware-based failure testing" as the outside anchor and does not describe it |
| `C2` | Structural for Flow code; excluded (deliberate) beyond it | The paper states that simulation cannot test third-party libraries, non-Flow code, or the real OS and filesystem contract |
| `C3` | Behavioral, by agreement; oracle-independent only in two narrow scopes | Workload checks such as the Cycle test. `ConsistencyCheck` compares replicas with each other, not with an independently derived value (`F-3`). A search across five candidate oracle categories found no independent correctness oracle for application-level data (`F-3b`). Page and disk-queue checksums, and the `AuditStorage` metadata modes, do derive independently, for byte survival and for data placement only. Same shape as `CI-005` |
| `C4` | Documentation-level breadth claim, with a stated exclusion | The paper states that simulation does not reliably detect performance pathologies |

The paper and documentation statements in this table were gathered on
2026-09-28 and were not re-read on 2026-10-11. The `run.py` lines were
read on 2026-10-11. The `F-` items are taken as recorded in
`FOUNDATIONDB_CASE_STUDY_FROZEN.md` and `FOUR_SYSTEM_SYNTHESIS.md`, on
release 7.4.6; step 3 below used 7.3.63.

**Step 5 — substituted, not performed as specified.** No independently
specified workload was built. Three documented incidents were examined in
its place:

| Incident | Mechanism known | Status after analysis |
| --- | --- | --- |
| A. ext4 kernel deadlock, Ubuntu 12.04/12.10 | Yes (kernel bug) | Consistent with the exclusion `C2` already documents. Not a gap |
| B. Issue #2068, data loss after a `locality_data_hall` reconfiguration | No | Unverified report. Whether simulation models the action is unknown |
| C. Issue #4089, all data lost after a `datacenter_id` rename followed by a regions configuration | Yes, traced by the reporter | Carried into steps 4 and 3 |

**Step 4 — reachability of incident C** (done before step 3). The
simulator reads each machine's datacenter ID from the restart file
unchanged and renames only zone IDs. No workload renames a datacenter ID.
The comment above that code reads "Randomly change data center id names to
test that localities can be modified on cluster restart"
(`SimulatedCluster.actor.cpp:1310–1313` at 7.3.63;
`SimulatedCluster.cpp:1355–1358` on main at `b386c88`). Classification:
outside the inputs simulation generates, by omission. Nothing found in the
paper or documentation lists it as an exclusion. As of 2026-09-28 the
issue had been open since November 2020 with no assignee, label or linked
fix.

**Step 3 — bounded construction.** The datacenter IDs in the simulator's
restart file were renamed between the two phases of FoundationDB's own
`ConfigureTestRestart` test pair. Controls: file untouched, and zone IDs
renamed (the rename the simulator already performs). Full record in
`CS2_STEP3_RESULT.md`. In the run whose predictions were hashed
beforehand, on 20 two-datacenter clusters selected from phase 1 alone:

| Prediction | Outcome |
| --- | --- |
| Every cluster with no stored region configuration: all storage servers dispose their stores, the test fails, and a further restart fails | 11 of 11 (183 of 183 storage servers) |
| No cluster with a stored region configuration shows full disposal | 0 of 9 |
| Both controls pass | 20 of 20 each |

An earlier exploratory run showed the same split (7 of 7). Across all
runs, none of the 82 clusters outside the target class lost storage data,
and both controls passed on all 100 seeds. The simulator supplies the
second half of the #4089 sequence unaided: on restart of a two-datacenter
cluster it configures regions from the IDs it has just read
(`SimulatedCluster.actor.cpp:1460–1485`). The disposal path was read in
source: `TagPartitionedLogSystem.actor.cpp:960–967` throws
`worker_removed`, and `storageserver.actor.cpp:13655–13659` calls
`dispose()`.

**Step 6 — not performed.** One harness, one operator. The verdict comes
from FoundationDB's own test result and its own trace events.

**Step 7 — calibrated claims.** These are this study's rewrites.
FoundationDB's maintainers have not seen or accepted them.

- `C1a`: the same seed produces the same run; the re-run comparison is
  sampled and, at 7.3.63, not applied to restarting tests.
- `C3`: simulation verifies agreement, between replicas and with
  FoundationDB's own workload invariants. Independent derivation was found
  only for byte survival on disk and for metadata placement.
- `C4`, as the restart code states it: restart tests randomly rename zone
  IDs. Datacenter IDs are never renamed.
- New, bounded: in release 7.3.63, under simulation, renaming datacenter
  IDs across a restart of a two-datacenter cluster with no stored regions,
  followed by a regions configuration, makes every storage server dispose
  its store.

**What following the sequence changed.** Four conclusions, two of which
removed a finding:

1. Incident A was first recorded as a crack in `C1`/`C2`. Step 2 showed
   FoundationDB had already documented that boundary. Withdrawn.
2. Incident B was first recorded as an unmodeled administrative input.
   Reading the workloads showed configuration changes are modeled
   (`ChangeConfig.actor.cpp`, `KillRegion.actor.cpp`). Downgraded to
   unknown.
3. Step 4 found a coverage statement in a code comment that the code
   beneath it does not carry out.
4. Step 3 showed that the #4089 sequence is reachable in FoundationDB's
   own simulator through one input it never generates.

One addition to the protocol came out of this: **claim origin**. Phoenix A
could not show it, because one party wrote both the system and its claims.
In FoundationDB the paper bounds its claims with care, a code comment
overstates coverage, and outside descriptions overstate further. Step 1
should record where each claim comes from: paper or documentation, code
comment, or outside description.

**What this case study does not establish.**

- That the protocol discovered a defect. A user reported #4089 in November
  2020. The protocol located why simulation does not reach it and showed
  that simulation can.
- That the research question posed above is answered. It asks for a party
  other than the protocol's author. This was the same party.
- Steps 5 and 6.
- Why the renamed datacenter leaves storage servers without a matching log
  set. That link is the #4089 reporter's account (a stale entry in
  `\xff/tagLocalityList`) and was not checked here.
- Behaviour on 7.4.x, 8.0.0 or main (source read only), with fault
  injection on, or under any other workload.
- The correlated-corruption proposition left open in August: whether
  `ConsistencyCheck` would accept identical wrong state arising on every
  replica. Still untested.
- Whether FoundationDB's maintainers regard the behaviour as a defect or
  as an unsupported operation.

**Errors made during this case study, left visible.**

- Predicted that Jepsen-class external testing would be the likely source
  of a gap. Jepsen's author reportedly declined to test FoundationDB
  because of its simulator.
- Incidents A and B were each misclassified before correction, as recorded
  above.
- Both trace signatures fixed before the first step 3 run
  (`TLogPeekLocalNoBestSet`, and `KVSRemoved` with `worker_removed`)
  appear in untouched controls. They are routine and identify nothing. The
  result rests on disposal counts and restart outcomes.
- The step 3 amendment stated that the construction would not replay #4089
  exactly. For two-datacenter clusters it does.
- The first confirmation run produced no cluster of the target class and
  was reported as uninformative, by a rule written before it ran.
- The first draft of this entry classified `C3` as having no
  oracle-independent verification at all. The August inventory had already
  recorded two narrow independent checks. Corrected above.

Evidence: `CS2_STEP3_RESULT.md` and the accompanying bundle in
`case_study_2_foundationdb/` (plans with pre-run hashes, result tables,
key trace events, harness); `FOUNDATIONDB_CASE_STUDY_FROZEN.md` and
`FOUR_SYSTEM_SYNTHESIS.md` for the August items. The pre-run hashes were
recorded in the working session and are not externally timestamped.

**The research question this progression is building toward, stated
precisely:** does Claim-Bounded Verification retain useful discriminatory
power — does it find real gaps between documented claims and actual
enforcement — when applied to a system its own author never designed it
around? Case Study 2 gives a partial answer: on one such system it found
one gap between a stated coverage claim and the code, and confirmed the
consequence by a pre-registered run. It was applied by the protocol's own
author, with two of seven steps not performed. A full application, by
another party, is the next real test.
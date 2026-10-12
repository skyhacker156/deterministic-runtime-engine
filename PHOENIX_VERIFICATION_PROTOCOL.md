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

**Later runs, 2026-10-11, after this entry was written.** The operator
re-ran run 3 on a second machine; the score file was identical
(`run3_score_patrick_rerun.txt`, `c37ff04`). Run 4 used the official
7.3.77 release, which FoundationDB's releases page marked "Latest" that
day, under a plan hashed before any 7.3.77 run (`run4_7377/`,
`b3471f0`). Its restart code and test pair were checked first and are
unchanged from 7.3.63. Every cluster with no stored region configuration
disposed every store (9 of 9, 150 of 150 storage servers), no cluster
with stored regions did (0 of 11), and both controls passed (20 of 20
each). On seed 10112 the simulator's own zone rename fired in the
untouched control; excluding it, 8 of 8. Across both releases, 27 of 27
target clusters lost every storage server's data. The statements above
that step 3 ran only on 7.3.63, and the bullet on untested releases, are
left as written; 7.4.x, 8.0.0 and main remain untested.

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
**A candidate screened out before Case Study 3: git's object model.**
Recorded so that the history is complete. On 2026-08-24 a working
session applied the seven steps to git's object model and reproduced
the pre-2.46.0 gap in which `transfer.fsckObjects` did not apply to
fetches from a bundle. None of it was committed, pre-registered or
hashed, and its evidence no longer exists; it is an unregistered pilot
and supports nothing here. On 2026-10-11 git was screened again as Case
Study 3, on the guarantee of `git push --atomic` that either every ref
is updated or, on error, none are. The screen stopped it: git's own
`Documentation/BreakingChanges.adoc` already states that multi-reference
writes are not atomic with the "files" backend, so a conventional
reading of the documentation finds the limitation without the protocol,
and the most the study could have claimed was a documentation-scope
result. This is the first time the selection screen stopped a target
before any construction. Record: `case_study_3_raft/CS3_SELECTION.md`.

**Case Study 3: etcd raft, linearizable reads under `ReadOnlySafe`.**
Selected 2026-10-11; all steps done 2026-10-11 to 2026-10-12. Applied by
the same party that wrote this protocol. The design was reviewed three
times by an outside model before hashing; that review is not an
independent application. Full records in `case_study_3_raft/`:
`CS3_SELECTION.md`, `CS3_EXECUTION_PLAN.md` (draft 3), `DEV_LOG.md`,
`CS3_RESULT.md`, the harness, the schedules, `HASHES_BEFORE_RUN.txt`
and `results/`.

**Prior internal work.** etcd raft was examined in August 2026
(`RAFT_CASE_STUDY_BASELINE.md`, `RAFT_RA001`–`RA006`, summarised in
`FOUR_SYSTEM_SYNTHESIS.md`; the RA files committed in `8ed1f7a`). That
study asked what etcd raft's TLA+ trace validation can see, and found
(`RA-003`, `RA-005`) that ReadIndex messages are never traced and that
trace validation passes with a real ReadIndex in the execution. It did
not test whether reads are correct, and it was not an application of
the seven steps. Case Study 3 is its direct follow-up: it tests the
behaviour that check cannot see. As with FoundationDB, the overlap with
"anything already examined here" is disclosed rather than treated as
disqualifying.

**Fit against the selection criteria.** Deterministic execution: the
library is a deterministic state machine; the harness drives it from a
seed, with its election randomness, drawn from `crypto/rand`, replaced
by a seeded source. Persistent, replayable state: the replicated log.
Integrity artifacts: met only loosely, as with FoundationDB; terms, log
indices and commit indices, no hash chain. Stated architectural claims:
met (below). Seams: met; the library leaves network, storage and the
read-serving step to the application, and the claim lives on that seam.
Different philosophy: met; Go, a consensus library, quorum-confirmed
reads. The screen used for this study added five further conditions: a
narrow falsifiable guarantee, an identifiable enforcement point,
reachable adversarial states, an independent oracle, and a conventional
baseline to compare against.

**Step 1 — claims extracted.** Claim origin recorded, per the addition
from Case Study 2.

| ID | Claim | Origin |
| --- | --- | --- |
| `R1` | `ReadOnlySafe` guarantees the linearizability of read-only requests by communicating with a quorum; it is the default and suggested option | Code comment and API documentation (`raft.go` lines 61 and 235 at v3.7.0; 59 and 233 at v3.6.0) |
| `R2` | Requests can be lost without notice, and retrying ReadIndex is the user's job | API documentation (`node.go` line 223 at both releases) |
| `R3` | "Efficient linearizable read-only queries served by both the leader and followers" | README (line 27 at v3.7.0) |

`R1` carries no condition. The lease-based mode, by contrast, is
documented as unsafe under unbounded clock drift.

**Step 2 — enforcement classification.**

| ID | Classification | Basis |
| --- | --- | --- |
| `R1` | Behavioral (unit tests); outside the formal model | The leader postpones reads until it has committed in its term, then confirms leadership by heartbeat acknowledgments (`read_only.go`). The TLA+ specification, byte-identical at both releases and unchanged since 2024-04-18, models none of the read path; the August study found the same from the trace side. At v3.7.0 a regression test for duplicated requests exists (`TestReadOnlyDuplicateRequest`); at v3.6.0 it does not. etcd's system-level robustness suite checks linearizability with Porcupine |
| `R2` | Application obligation | Not enforced by the library. The narrower rule that a retry must use a new context exists only on the unreleased `release-3.6` branch (`5a1e8a2`, 2026-03-09), added after issue #392; v3.7.0 states the restriction is lifted |

**Step 4 — reachability** (done before step 3). Issue #392: with a
retried or duplicated read request, a stale leader can confirm a later
read using acknowledgments gathered for an earlier one, returning a
read index below what linearizability requires. Fixed in v3.7.0 (PR
#397), absent from v3.6.0. The triggering retry reuses the request
context. That is compliant with the published contract of both
releases (`R2`), and every other ingredient is a legal network delay or
partition. Classification on v3.6.0: currently reachable through
sanctioned entry points. The duplicate can also come from the network
itself; whether that is legal is undocumented, so it was excluded.

**Step 3 — bounded construction.** A deterministic simulator driving
three `RawNode`s through the documented Ready contract, with a
conformance check on every Ready and every read. The directed scenario
(P1a) is the #392 sequence in eleven labelled steps, each library
behaviour, a legal network action, or a compliant caller action. On
the pinned v3.6.0 release (Go 1.27.0, module checksums verified), 19 of
21 runs produced a non-linearizable history with the #392 signature, a
clean conformance check, and an identical replay. Two aborted at setup
without a verdict.

**Step 5 — performed, with a coverage result.** Workloads were
generated from a schedule specification written for this study, not
from the library's test fixtures: 3,000 pre-generated schedules, one
register, three clients, message loss, delay with a long tail, and node
isolation and pause. On v3.6.0 (P1b, 2,000 trials, 420,715 reads) the
workload never reached the #392 signature; on v3.7.0 (P2, 2,000 trials;
P3, 1,000 leader-targeted trials) no violation occurred. Because P1b
found nothing on the release known to be faulty, P2 and P3 cannot speak
to the fix. The plan stated that consequence before the runs.

**Step 6 — partly performed.** The oracle, Porcupine v1.3.1, does not
import or derive from the code under test and judges client-observed
histories only. The v3.7.0 build's oracle also judged the recorded
v3.6.0 P1a history non-linearizable. The 3,000 schedules were
regenerated independently on a second platform with a different Go
version and were byte-identical. The harness that drives the library
was written by the same party, and there was one operator.

**Step 7 — calibrated claims.** This study's rewrites; etcd's
maintainers have not seen them.

- `R1`, at v3.6.0: under `ReadOnlySafe`, a client that retries a read
  with the same request context, as the released contract permits, can
  receive a non-linearizable read after a leadership change. The
  unconditional comment overstates the release.
- `R1`, at v3.7.0: no violation found in 3,000 randomized trials, by a
  harness shown able to detect #392 when a schedule reaches it. The
  randomized workload did not reach #392 on v3.6.0 either, so this is
  not evidence that the fix is complete.
- `R2`: the retry rule differs between the released contract and the
  `release-3.6` branch. Users of v3.6.0 who follow the released
  documentation are exposed.

**What following the sequence changed.**

1. Git was stopped at selection by a documentation reading, before any
   construction.
2. The claim that the formal baseline does not cover reads was first
   written as a new finding. It is the project's own August result,
   corroborated.
3. The contract question changed the design. The first draft required
   the harness to obey the `release-3.6` retry rule. Checking the
   released contracts showed that rule applies to neither release, so
   the positive control and the main workload could share one
   compliant workload.
4. The pre-registered positive control stopped 3,000 clean v3.7.0
   trials from being read as support for the fix. This is the study's
   clearest methodological result.

**What this case study does not establish.**

- A new defect. #392 was reported upstream and fixed; the system-level
  bug behind it (etcd #20418) was found by Antithesis in July 2025.
- That the #392 fix is complete, or that v3.7.0 reads are linearizable
  for all legal executions.
- That the protocol outperforms conventional testing. etcd's robustness
  suite already checks the same property with the same oracle. This
  study adds a library-level, contract-compliant reproduction with
  index attribution.
- The research question posed above: the party was the same.
- Lease-based reads, crash and restart, membership changes during
  reads, clusters other than three voters, or network duplication.

**Errors made during this case study, left visible.**

- Git was first described as barely started; seven steps had been run
  in August, uncommitted. Etcd raft was first described as a fresh
  target; the August study existed on the operator's machine,
  uncommitted, and was found only when the untracked files were listed.
- The first draft of the success condition required the stale read to
  be the duplicated request. In #392 it is a different request,
  confirmed by acknowledgments gathered for the duplicated one.
- The first draft's network could not reach #392: delays were capped
  below the length of an election. A long-delay tail was added before
  hashing. P1b still did not reach it.
- The disclosed expectation for P1a was 21 of 21, from development
  runs; it was 19 of 21. The two setup aborts point to a precondition
  the harness does not check: that every follower knows the leader
  before the first read.
- P1a had been run on development builds before hashing. It was
  disclosed in the plan and the development log, and the reserved
  seeds were not used, but the scored P1a was not blind.
- The first operator build failed on a quoting error in the build
  script, before anything was built.

The pre-run hashes were committed in `a733851` and pushed at
2026-10-11 23:50:45, before any scored run (`e640291`, `09beef0`,
`ab528c1`). All 28 entries matched the committed files when checked
after the push. The push times are GitHub's record; the hashes are not
otherwise externally timestamped.

**The research question after Case Study 3.** Across two applications to
systems the protocol was not designed around, it located one coverage
gap in a code comment and confirmed its consequence (FoundationDB), and
it reproduced a known, fixed defect and prevented a clean randomized
result from being over-read (etcd raft). It has not yet found a defect
that was not already known, has not been applied by another party, and
has not been compared with conventional testing on equal terms. Those
remain the next real tests. The paragraph above was written after Case
Study 2 and is left as written.

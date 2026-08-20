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

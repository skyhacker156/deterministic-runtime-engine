# FA-001 — Deterministic Simulation Control and Environmental-Perturbation Test (F-1)

**Status:** frozen. First adversarial finding in the FoundationDB case
study. Real, genuine FoundationDB `7.4.6` `fdbserver` binary — downloaded
directly from the official GitHub release, not built or simulated by me
— run in its real `-r simulation` mode against a real test file
(`tests/Happy.txt`) from the matching source tag. No FoundationDB code
modified. No fix proposed.

## Decomposition — what is deterministic, and by what mechanism

Confirmed directly from the shipped binary's own `--dev-help` output
(not documentation, not a blog post — the actual binary's real,
authoritative option list): `fdbserver -r simulation -s SEED -f TESTFILE`
runs the deterministic simulator with an explicit, user-controlled random
seed. `-b [on,off]` (BUGGIFY) and `-fi [on,off]` (fault injection) are
real, confirmed flags — this **upgrades** both from the secondary-source
status flagged in `FOUNDATIONDB_EVIDENCE_BASELINE.md` to primary-source
confirmation, straight from the actual binary.

The mechanism under test for `F-1`: does an identical seed, against an
identical test file, produce identical simulated behavior — and does
that identity hold only incidentally (e.g., because nothing perturbs an
idle machine) or genuinely, independent of real environmental variation?

## The construction

**Control:** `fdbserver -r simulation -f tests/Happy.txt -s 12345`, run
twice, back to back, output captured in full (Run A, Run B).

**Adversarial/divergence check:** the same command with a different seed
(`-s 99999`, Run C) — confirms the seed genuinely drives the simulation
rather than the output being trivially constant.

**Independent evidence — the sharper test:** the same seed as the
control (`12345`), run a fourth time (Run D), but with genuine, real CPU
contention deliberately induced across every available core (busy-loop
processes launched immediately before, running concurrently) — testing
whether the determinism claim holds under real host-level scheduling
perturbation, not merely under back-to-back idle-machine conditions.

## Results

| Run | Seed | Contention | `Unseed` | Simulated elapsed | Real elapsed | Diff vs. Run A |
|---|---|---|---|---|---|---|
| A | 12345 | none | 11519 | 296.473553 simsec | 7.70s | — |
| B | 12345 | none | 11519 | 296.473553 simsec | 9.34s | **0 bytes, MD5-identical** |
| C | 99999 | none | 94746 | 604.204492 simsec | 14.63s | 437 lines differ |
| D | 12345 | **real, active** | 11519 | 296.473553 simsec | 18.19s | **0 bytes, MD5-identical** |

All comparisons exclude only the "real seconds" wall-clock line, which
is not itself part of the simulation's determinism claim (the simulation
claims deterministic *simulated* behavior, not deterministic *real*
runtime — confirmed precisely by this data: real elapsed time varied
substantially, 7.7s to 18.2s, entirely consistent with genuine
environmental perturbation, while every other line of output — including
the simulated elapsed time, every `Metric` line, every `Unseed` value —
remained byte-identical).

## The result, stated at the precision this evidence earns

**`F-1` is confirmed, and confirmed more strongly than the minimal
control alone would establish.** Same seed produces byte-identical
simulated output (Run A vs. B: the baseline claim). Different seed
produces genuinely different output (Run A vs. C: confirms the seed is
load-bearing, not decorative). Same seed produces byte-identical output
**even under real, measured, deliberately-induced CPU contention** (Run
A vs. D: rules out the more skeptical reading that apparent determinism
is an artifact of testing only on an idle, unperturbed machine).

**What this does not establish, stated as precisely as the finding
itself:** that the simulated behavior is *representative* of production
behavior — `F-1` is a claim about the simulation's internal repeatability,
not about `F-5`'s simulation-production correspondence question, which
remains a separate, unresolved claim in this case study. Nor does this
test any fault-injection behavior (`F-2`), any transactional-correctness
property (`F-3`), or recovery behavior (`F-4`) — the test file used
(`Happy.txt`) ran a simple cycle-test workload and, notably, reported its
own internal test as failing ("0 test clients passed; 8 test clients
failed," "1 SevError events logged") in this sandbox environment — this
is recorded as a real, honest observation, not glossed over, though it
does not affect `F-1`'s determinism finding, since the same failure
reproduced identically across every same-seed run.

## Explicitly not done

`F-2` through `F-6` untouched. No investigation of why `Happy.txt`'s
internal test failed in this environment (plausibly resource constraints
specific to this sandbox — not investigated, since it is orthogonal to
the determinism question this construction targeted). No fix, no
FoundationDB code modification. Per the standing case-study discipline,
this is a clean, decisive result and the natural stopping point for
`F-1` — not a reason to keep re-testing the same finding further.

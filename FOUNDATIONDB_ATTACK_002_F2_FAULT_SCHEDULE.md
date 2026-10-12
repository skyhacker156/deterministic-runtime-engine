# FA-002 — Fault Schedule Determinism and the `-fi` Boundary (F-2)

**Status:** frozen. Second adversarial finding in the FoundationDB case
study. Real `fdbserver 7.4.6` binary, same test file (`tests/Happy.txt`)
and seed (`12345`) as `FA-001`, extended with direct inspection of the
real trace XML output — not aggregate console output — to test the fault
schedule specifically, not merely overall determinism.

## The question, precisely, per instruction

Not "can FoundationDB survive failures" (too broad). **What fault space
does the deterministic simulation actually exercise, and does a fixed
seed deterministically reproduce the resulting fault schedule and
outcome?**

## Decomposition — real fault-relevant events found in trace output

Direct inspection of the real trace XML (not documentation, not
aggregate metrics) identified genuine fault/reboot-related event types
actually emitted during a run: `RebootWhenDurableTriggered`,
`RebootWhenDurableSet`, `SimulatedRebooterStarting`, `StorageServerReboot`,
`StorageServerRebootStart`, `StorageServerRequestedReboot`,
`DDAuditStorageLaunchFaultInjection`, plus connection/request-failure
events (`ConnectionFailure`, `AllAlternativesFailed`,
`NotifyAddressFailed`, and others). These are the concrete, observable
artifacts of "the fault schedule" for this construction.

## Construction and results

**Fault-schedule determinism (same seed, fault injection at its
default/on setting):** the exact `Time`, `Type`, and `Machine` triple for
every one of 48 fault-relevant events (the five reboot/fault-injection
types above) was extracted from two independent same-seed runs (`FA-001`'s
Run A and Run B) and diffed. **Zero differences.** The fault schedule
itself — not merely aggregate metrics — is reproduced exactly.

**The `-fi off` control:** the same test file and seed, with fault
injection explicitly disabled (`-fi off`), was run and its trace
similarly extracted. **Result, reported honestly rather than reshaped
into a more dramatic finding:** the same five fault-relevant event types
occurred, with the **exact same counts** (1 / 6 / 29 / 6 / 6) and — on
direct `Time`/`Type`/`Machine` comparison — the **exact same schedule**
as the fault-injection-on run. The full set of distinct event *types*
across the entire trace was also identical between the two runs (672
types in each, zero types unique to either side).

**One loose end, named rather than silently dropped:** total event
counts differed by exactly one (34246 vs. 34245) between the two runs.
A first attempt to isolate this single differing event was invalidated
by a real methodological error — the comparison inadvertently included
the `DateTime` attribute (real wall-clock time, which legitimately
differs between separate invocations) rather than only simulated `Time`,
making that specific diff meaningless. The one-event discrepancy was
**not** chased down further in this pass — recorded as an open, unresolved
detail rather than either explained away or ignored.

## The result, stated at the precision this evidence earns

**F-2a (confirmed):** for this specific tested workload and seed, the
fault schedule — the specific sequence of reboot/fault-injection-relevant
events, their simulated timing, and which simulated machine each occurs
on — is reproduced exactly across independent same-seed executions. This
extends `F-1a`'s aggregate-output determinism finding to the specific
mechanism `F-2` was built to test: not just "the output matches" but "the
injected fault sequence itself matches."

**F-2b (the honest, non-dramatic finding, stated precisely):** for this
specific workload and seed, toggling `-fi off` produced **no observable
difference** in the fault-relevant events actually recorded — same
counts, same schedule, same event-type set. **This does not establish
that `-fi` has no effect in general** — it establishes only that, for
this one minimal test file and this one seed, whatever `-fi` gates was
not observably exercised. Plausible explanations, none confirmed in this
pass: `Happy.txt` may be too short/simple a workload to reach the code
paths `-fi` actually gates; the reboot events observed may belong to a
different category of simulated process lifecycle management than what
`-fi` specifically controls (as distinct from `-b`/BUGGIFY, not
separately toggled in this construction); or `-fi`'s effect may only be
observable with a workload specifically designed to exercise it. **Not
resolved here — flagged as the precise next question**, not glossed over
or forced into a more decisive-sounding conclusion than the evidence
supports.

## Why this null-ish result is still a real result

Per the standing discipline of this whole case-study series: a clean,
non-dramatic finding is valuable precisely because it demonstrates the
protocol isn't merely a counterexample generator. `F-2a` is a genuine,
positive, decisive confirmation (fault-schedule determinism, not just
aggregate-output determinism). `F-2b` is an honest report of what this
specific minimal construction did *not* show — not a claim that `-fi` is
inert, and not stretched into a dramatic finding it doesn't support.

## Explicitly not done

`-b`/BUGGIFY not independently toggled in this construction (only `-fi`
was varied). The one-event count discrepancy not traced to its source.
No workload specifically designed to exercise fault-gated code paths was
attempted — a natural, named next step for a future `F-2` construction,
not started here. `F-3` through `F-6` untouched.

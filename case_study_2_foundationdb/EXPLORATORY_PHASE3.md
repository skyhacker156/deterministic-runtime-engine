# Case Study 2, Step 3: exploratory recoverability check (NOT pre-registered with the 40-seed run; written after seeing it)

Question: in the two-datacenter seeds, is the failure under datacenter rename reversible unavailability or destroyed data?
Method: take the end-of-phase-2 on-disk state of each of the 11 two-datacenter seeds, put back the ORIGINAL
restartInfo.ini (original datacenter and zone ids), and restart once more with the same phase-2 test (seed S+2).
Arms: from the `dc` end state (treatment) and from the `none` end state (harness control: shows a third restart works at all).
Prediction, written before running:
- deletion seeds (9004 9008 9028 9050 9056 9062 9076): `dc` arm fails, `none` arm passes.
- non-deletion seeds (9002 9024 9026 9030): both arms pass.

## Correction added after the first phase-3 run (before running the arm below)
The `dc` arm cannot separate destroyed data from a naming mismatch: in the deletion seeds phase 2 stored a region
configuration naming the RENAMED datacenters, so restoring the original names makes the cluster unavailable for the
same reason as the non-deletion seeds were in phase 2. New arm `dc_keep`: restart from the `dc` end state with the
RENAMED ini, so process names match the stored region configuration. Prediction: `dc_keep` fails on all 7 deletion seeds.
If it passes, the data was not destroyed and the phase-2 failure has another cause.

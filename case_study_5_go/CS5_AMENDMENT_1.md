# Case Study 5, amendment 1: sandbox restart during G1a

Written 2026-10-12 at about 22:24 UTC (18:24 local), before any CS5 run
has produced an archive. Governs only the restart below; the plan
(`CS5_PLAN.md`, `762c841`, SHA-256 `39D95245...3D243`) is otherwise
unchanged.

## What happened

- `harness/run_cs5.sh` (SHA-256 `F883FF45...3228C`) was started at
  22:04:33 UTC (`nohup`, background) with `WORK=.../scratchpad/cs5work`.
- The sandbox container restarted at about 22:22 UTC (`uptime` 1 minute
  at 22:23:03 UTC; kernel boot messages only). The script and every child
  process were gone.
- G1a had reached `Building packages and commands for target,
  windows/amd64.` (`make_G1a.log`, 7 lines, last written 22:08:12 UTC).
  No `pkg/distpack` archive exists; `results.tsv` holds only its header.
  No hash was computed; no outcome was observable.
- Inputs re-checked after the restart: script and plan hashes as above;
  bootstrap A `go1.24.7 linux/amd64`; bootstrap B `go1.27.0 linux/amd64`;
  tag `go1.27.0` at `8af21751f066eced273ca3ce49506b366847c623`.

## Restart procedure

1. `results/make_G1a.log` is kept, renamed `make_G1a_interrupted.log`.
   The partial tree in `cs5work` is left in place, unused.
2. The same script, unchanged, is started again from the beginning (all
   eight runs, same order) with a new `WORK=.../scratchpad/cs5work2` and
   the same `OUT`. `bootstrap_*.txt`, `source_*.txt` are rewritten by it
   with the same content (checked above).
3. The session polls in the foreground until the script ends, so the
   container is not left idle.

## Rule for any further interruption

A run that produced no archive was not observed and is restarted the
same way (new `WORK`, interrupted log kept under a new name, recorded
here or in a further amendment). A run that produced an archive and a
`results.tsv` row is never rerun. The 22:00 local hard stop is
unchanged.

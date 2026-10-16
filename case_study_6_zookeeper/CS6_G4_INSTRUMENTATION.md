# CS6 preflight finding: G4 instrumentation (follower applied-zxid witness)

Resolves open item 3 of `CS6_PLAN.md`. Source read at tag `release-3.9.6`,
commit `a355171b081b5b60749db8f19cca1528b0df936f`. Not run yet; this is a
source finding to be confirmed empirically in step 1 on the operator's box.

## Question

Can a follower's *applied* state (its `lastProcessedZxid`) be observed at the
moment it serves the read, so that G4 (S2 behind Z while serving) is a direct
observation and not an inference from a replication delay?

## Answer: yes, via a purpose-built endpoint

`server/admin/Commands.java` `ZabStateCommand` `L1111-1138`
(`/commands/zabstate`) returns, for a quorum server:
- `last_zxid` = `zkServer.getZKDatabase().getDataTreeLastProcessedZxid()` (`L1137-1138`)
- `zabstate` (e.g. `following`, `leading`, `synchronization`)
- `is_leader`, `voting`, `myid`

One call yields both halves of G4: the applied zxid AND confirmation the node
is a following follower.

## Why this is the right witness

`last_zxid` here is the *same* call `FinalRequestProcessor` uses at
`FinalRequestProcessor.java:165`
(`zks.getZKDatabase().getDataTreeLastProcessedZxid()`) to stamp the read reply
header (`L588`, G6). So G4 (server applied state) and G6 (reply-header zxid)
read the same underlying counter and corroborate by construction: if `zabstate`
shows S2 < Z and the read reply header shows < Z, they are the same number.

## Backups (same value, less convenient)

- 4lw `mntr`, `srvr`, `stat` and AdminServer `srvr`/`stat` expose it via
  `ServerStats.toString()` -> `Zxid: 0x...` (`ServerStats.java:132`,
  `getLastProcessedZxid` `L85-86`). These do not certify follower role as
  cleanly as `zabstate`, so use them only as a cross-check.

## Harness implication (for PREFLIGHT_AUDIT.md, not a plan change)

`zabstate` is a snapshot at call time; S2 could advance between the probe and
the read. Therefore the authoritative "state that served this read" value is
the read's OWN reply-header zxid (G6). `zabstate` is the pre-check (confirm S2
behind Z and `following` before issuing the read) and the corroborator. The
reply-header zxid is primary.

## Step-1 empirical check (to run on the operator's machine)

Stand up a 3-node 3.9.6 ensemble with AdminServer enabled, then confirm each
node's `zabstate` reports its own `last_zxid` and role, and that a follower
held behind shows a lower `last_zxid` than the leader while still answering
`getData`. Commands are in the resume note.

Status: G4 witness confirmed available in source. First fork resolves green;
the harness build can proceed once step 1 confirms the endpoint behaves as
read.

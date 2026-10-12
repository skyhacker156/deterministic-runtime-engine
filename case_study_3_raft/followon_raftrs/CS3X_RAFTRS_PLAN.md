# Case Study 3, follow-on X1: does the #392 sequence transfer to raft-rs?

Pre-registration. Written 2026-10-12, before any raft-rs harness code
exists and before the #392 scenario has been run against raft-rs in any
form. To be committed and pushed before that code is written. Any later
change is a dated amendment, written before the run it affects.

## Label and governance

- This is a **Case Study 3 follow-on** (cross-implementation transfer,
  the protocol's step 6 for Case Study 3), **not Case Study 4**. raft-rs
  is a port of etcd raft, so it fails the "different implementation
  philosophy" selection criterion, and a matching result would show
  transfer within one design lineage, not generality across unrelated
  designs.
- The CBV protocol in `PHOENIX_VERIFICATION_PROTOCOL.md` governs. The
  four-category taxonomy protocol (`FIFTH_CASE_STUDY_PROTOCOL.md`) is a
  separate research line and does not govern this work.
- Case Study 4 is selected separately, after this follow-on closes. The
  leading candidate is gRPC retries; it is not selected here.

## Question

Under `ReadOnlyOption::Safe`, does the issue #392 sequence (Case Study
3, `CS3_EXECUTION_PLAN.md` section 3) make raft-rs return a read index
below what linearizability requires, so that a client observes a stale
read?

## Targets, pinned

| Item | Value |
| --- | --- |
| Release | crate `raft` 0.7.0 from crates.io; tag `v0.7.0`, `10c6e9db6792b85c81784e44fc278f895d5f0ab0` (2023-03-07); latest release |
| Development head | `tikv/raft-rs` main, `ad13f3d90780f53aea2488c6a4b76c0d334bf136` (2026-05-13) |
| Positive control | etcd raft v3.6.0, Case Study 3 P1a (`e640291`): 19 of 21 reproduced |
| Negative control | etcd raft v3.7.0, Case Study 3 development runs only; see "Controls" |
| Oracle | Porcupine v1.3.1, single-register model, same history encoding as Case Study 3 |
| Toolchain | Rust and Go versions recorded at build; `Cargo.lock` committed |

## Basis for the prediction (source reading, done before this plan)

- `src/read_only.rs` at both pins has the structure of etcd v3.6.0's
  `read_only.go`: the request context is the heartbeat context;
  `add_request` skips a context only while it is still pending;
  `advance` pops every queued request up to and including the
  acknowledged context. etcd's fix for #392 (PR #397) changed exactly
  this, to unique heartbeat contexts. The file differs between the two
  pins only in how `Default` is derived.
- No commit in raft-rs history mentions duplicate read requests, stale
  read index, or #392 (searched 2026-10-12: "read index", "readindex",
  "read_only", "duplicate", "stale read", "392").
- The claim: `ReadOnlyOption::Safe` "guarantees the linearizability of
  the read only request by communicating with the quorum. It is the
  default and suggested option." (`src/read_only.rs`, v0.7.0). Origin:
  code comment and API documentation, identical in wording to etcd's.
- The contract: `RawNode::read_index` documents no retry rule at all,
  so retrying with the same context is neither required nor forbidden.
  This is weaker ground than etcd, where the released contract assigns
  retries to the user explicitly. The retry is therefore labelled
  "permitted by omission" for raft-rs.
- One known difference: a raft-rs leader that has not committed an
  entry in its term **drops** a ReadIndex request instead of
  postponing it (`src/raft.rs`, `MsgReadIndex` in the leader step). The
  scenario issues every read after the relevant leader has committed in
  its term, so this does not change the sequence.

## Prediction

**P-X1.** On both pins, the directed scenario produces at least one
run with a non-linearizable history showing the #392 signature: a read
submitted once, returned with an index below the client-history bound,
and confirmed while a twice-delivered context of a different read was
pending at the same stale leader.

**Falsification.** If every run that passes all reachability
checkpoints (below) yields no ReadState for read B, or a ReadState
whose index is at least the client-history bound, P-X1 is false for
that pin, provided the mutant control M1 is detected (below).

## Scenario

The Case Study 3 P1a sequence, unchanged in its eleven steps, driven
through raft-rs's `RawNode` and its Ready contract. Three voters,
`HeartbeatTick 1`, `ElectionTick 10`, `check_quorum true`,
`pre_vote true`, `read_only_option Safe`.

**Amendment relative to Case Study 3 P1a, declared here.** The two
Case Study 3 setup aborts point to a missing precondition: before read
A is issued, every follower must know the leader. The raft-rs scenario
waits for that (up to 40 ticks) and aborts if it does not hold.

**Determinism.** raft-rs draws election timeouts from
`rand::thread_rng()` within `[min_election_tick, max_election_tick)`.
The harness sets `max_election_tick = min_election_tick + 1`, which
makes the draw constant without changing library code. The node
expected to win each election is campaigned explicitly, as in Case
Study 3.

**Runs.** Jitter values 0-20 on each pin (42 runs). Jitter delays
messages outside the read path by 0-1 tick, as in Case Study 3.

## Reachability checkpoints (a run is informative only if all pass)

1. Node 1 is leader in term *t* and has committed an entry in *t*.
2. Nodes 2 and 3 both know node 1 as leader before read A.
3. Read A is confirmed at node 1, and its response to node 2 is held.
4. Client 2's retry of A reaches the network and is held.
5. A new leader is elected among nodes 2 and 3 in a term above *t* and
   commits an entry.
6. The write completes through the new leader, at an index above node
   1's commit index.
7. Read B is issued on node 1 while node 1 is still leader of term *t*.
8. On heal, node 1 receives the held retry of A before the held
   heartbeat responses, and A is pending at node 1 again when those
   responses arrive.

A run that fails a checkpoint is reported as "not reached" with the
checkpoint number and counts neither way.

## Controls

- **Oracle sensitivity:** the Go checker's self-test, including the
  recorded etcd v3.6.0 P1a history from `e640291` as an
  expected-non-linearizable case.
- **M1, planted-defect control, run only if P-X1 is falsified on a
  pin.** A copy of that pin with one change: `recv_ack` credits every
  acknowledgment to the last pending request regardless of context.
  The scenario must then produce a non-linearizable history. If it
  does not, the raft-rs harness is judged insensitive and the clean
  result is reported as uninformative.
- **etcd v3.7.0** is not re-run here; its behaviour on this scenario is
  known only from Case Study 3 development builds and is not cited as
  evidence.

## If P-X1 holds

Before any claim of a defect, in order:

1. Replay from seed; the history must be byte-identical.
2. Minimise: remove steps and confirm each remaining one is necessary.
3. Confirm the conformance check (Ready order, persistence, reads
   served only after applied index reaches read index) passed.
4. Trace the confirmation of read B to the source line in
   `read_only.rs`, and check whether anything else in raft-rs could
   prevent it.
5. Check how TiKV, the main user, issues and retries ReadIndex. No
   statement about TiKV impact is made unless that is verified.
6. Report to `tikv/raft-rs` with the minimal reproduction, after
   reading its contributing and security guidance, before any public
   write-up of the finding beyond this repository.

## What this follow-on cannot establish

- Generality of CBV across unrelated designs (same lineage).
- Anything about TiKV's end-to-end correctness unless step 5 above is
  done.
- Behaviour under the randomized workload (not run; Case Study 3 showed
  it does not reach #392).
- Independence of operator: same party as Case Study 3.

## Development disclosure

Before this plan: the raft-rs repository was cloned and read; crate
`raft` 0.7.0 was downloaded and a one-line program compiled to confirm
the toolchain works (it printed that the default read option is
`Safe`). No raft-rs node was created and no scenario was run.

package raft

import (
	"testing"

	pb "go.etcd.io/raft/v3/raftpb"
)

// RA-001: does restore() ever actually see StateLeader?
//
// Source-level decomposition (RAFT_PHASE2_ENFORCEMENT_DECOMPOSITION.md)
// found three independent reasons to expect this is unreachable:
//   1. Shared Step() pre-processing demotes to follower on any message
//      (including MsgSnap) with a higher term, BEFORE state dispatch.
//   2. stepLeader's switch has no case for MsgSnap at all -- a same-or
//      lower-term MsgSnap is silently dropped without ever reaching
//      handleSnapshot/restore.
//   3. The public API (Node/RawNode) exposes no direct call to restore()
//      that could bypass the message pipeline.
//
// This test empirically probes both live conditions: a MsgSnap with a
// HIGHER term than the leader's own, and one at the SAME term.

func TestRA001_RestoreNeverSeesLeaderState_HigherTerm(t *testing.T) {
	storage := newTestMemoryStorage(withPeers(1, 2, 3))
	r := newTestRaft(1, 10, 1, storage)
	r.becomeCandidate()
	r.becomeLeader()
	if r.state != StateLeader {
		t.Fatalf("setup failed: expected StateLeader, got %v", r.state)
	}
	leaderTerm := r.Term

	snap := pb.Snapshot{
		Metadata: &pb.SnapshotMetadata{
			Index: new(uint64(5)),
			Term:  new(uint64(leaderTerm + 1)),
			ConfState: &pb.ConfState{
				Voters: []uint64{1, 2, 3},
			},
		},
	}
	err := r.Step(&pb.Message{
		From:     new(uint64(2)),
		To:       new(uint64(1)),
		Term:     new(leaderTerm + 1), // HIGHER term than the leader's own
		Type:     pb.MsgSnap.Enum(),
		Snapshot: &snap,
	})
	if err != nil {
		t.Fatalf("Step returned error: %v", err)
	}

	// Per the source trace: a higher-term message forces becomeFollower
	// BEFORE state-specific dispatch -- restore() should have run with
	// r.state already StateFollower, never StateLeader.
	t.Logf("RA-001 [higher term]: post-Step state=%v term=%d committed=%d",
		r.state, r.Term, r.raftLog.committed)

	if r.state == StateLeader {
		t.Errorf("RA-001 [higher term]: RESULT C -- node is still StateLeader after processing MsgSnap; restore()'s guard precondition may have been reachable")
	} else {
		t.Logf("RA-001 [higher term]: RESULT A/B -- node transitioned to %v before/during snapshot handling, confirming the guard's precondition (r.state == StateLeader at restore time) was not met via this path", r.state)
	}
}

func TestRA001_RestoreNeverSeesLeaderState_SameTerm(t *testing.T) {
	storage := newTestMemoryStorage(withPeers(1, 2, 3))
	r := newTestRaft(1, 10, 1, storage)
	r.becomeCandidate()
	r.becomeLeader()
	leaderTerm := r.Term
	committedBefore := r.raftLog.committed

	snap := pb.Snapshot{
		Metadata: &pb.SnapshotMetadata{
			Index: new(uint64(5)),
			Term:  new(uint64(leaderTerm)), // SAME term as the leader's own
			ConfState: &pb.ConfState{
				Voters: []uint64{1, 2, 3},
			},
		},
	}
	err := r.Step(&pb.Message{
		From:     new(uint64(2)),
		To:       new(uint64(1)),
		Term:     new(leaderTerm), // SAME term
		Type:     pb.MsgSnap.Enum(),
		Snapshot: &snap,
	})
	if err != nil {
		t.Fatalf("Step returned error: %v", err)
	}

	t.Logf("RA-001 [same term]: post-Step state=%v term=%d committed=%d (was %d before)",
		r.state, r.Term, r.raftLog.committed, committedBefore)

	if r.state != StateLeader {
		t.Errorf("RA-001 [same term]: unexpected state transition -- expected to remain StateLeader (stepLeader has no MsgSnap case), got %v", r.state)
	}
	if r.raftLog.committed != committedBefore {
		t.Errorf("RA-001 [same term]: RESULT C -- committed index changed (%d -> %d) from a same-term MsgSnap while remaining leader; snapshot was applied despite no visible state transition",
			committedBefore, r.raftLog.committed)
	} else {
		t.Logf("RA-001 [same term]: RESULT A -- node remained StateLeader and committed index is unchanged; the MsgSnap was silently dropped exactly as the source trace predicted (no case in stepLeader's switch)")
	}
}

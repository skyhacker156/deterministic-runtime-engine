package raft

import (
	"os"
	"testing"

	pb "go.etcd.io/raft/v3/raftpb"
)

// RA-004 control: zero extensions enabled (no PreVote, no CheckQuorum,
// no ReadOnlyLeaseBased) -- the cleanest possible baseline. If this
// fails TraceMatched too, the divergence mechanism found in RA-002/the
// ReadIndex construction is not specific to those extensions at all,
// and the real cause must be sought elsewhere (e.g. proposal/
// replication trace granularity). If this SUCCEEDS, it isolates the
// failure specifically to the extensions under test.
func TestRA004Control_PlainElectionBaseline(t *testing.T) {
	f, err := os.Create("/tmp/ra004_control_trace.ndjson")
	if err != nil {
		t.Fatalf("create trace file: %v", err)
	}
	defer f.Close()
	writer := &jsonTraceWriter{f: f}

	cfgFunc := func(c *Config) {
		c.TraceLogger = writer
		// deliberately: no PreVote, no CheckQuorum, no ReadOnlyLeaseBased
	}

	nt := newNetworkWithConfig(cfgFunc, nil, nil, nil)
	n1 := nt.peers[1].(*raft)

	nt.send(pb.Message{From: 1, To: 1, Type: pb.MsgHup})
	if n1.state != StateLeader {
		t.Fatalf("setup failed: n1 should be leader, got %v", n1.state)
	}

	for i := 0; i < 25; i++ {
		nt.send(pb.Message{From: 1, To: 1, Type: pb.MsgProp, Entries: []pb.Entry{{Data: []byte("plain")}}})
	}

	f.Sync()
	t.Logf("RA-004 control: n1 state=%v term=%d commit=%d", n1.state, n1.Term, n1.raftLog.committed)
}

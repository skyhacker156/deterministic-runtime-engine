package raft

import (
	"os"
	"testing"

	pb "go.etcd.io/raft/v3/raftpb"
)

// RA-004: does the trace-validation boundary fail open or fail closed?
//
// RA-002 showed PreVote fails CLOSED (TraceMatched violated) because it
// introduces a new, traced-model-visible STATE (PreCandidate) with no
// corresponding trace event to justify it -- a structural mismatch the
// model's transition relation can detect.
//
// ReadIndex (ReadOnlyLeaseBased mode specifically, to avoid the
// ReadOnlySafe mode's incidental heartbeat-broadcast trace footprint) is
// the strongest candidate for the OPPOSITE outcome: it materially
// affects the protocol (a real linearizable read either succeeds or is
// unsafe) while leaving every traced state field (term, vote, commit,
// role) completely unchanged, per direct source reading
// (sendMsgReadIndexResponse's ReadOnlyLeaseBased branch calls r.send
// directly with a MsgReadIndexResp -- confirmed untraced in RA-003 --
// and touches no state field at all).

func TestRA004_ReadIndexFailOpenOrClosed(t *testing.T) {
	f, err := os.Create("/tmp/ra004_trace.ndjson")
	if err != nil {
		t.Fatalf("create trace file: %v", err)
	}
	defer f.Close()
	writer := &jsonTraceWriter{f: f}

	cfgFunc := func(c *Config) {
		c.CheckQuorum = true // required for ReadOnlyLeaseBased
		c.ReadOnlyOption = ReadOnlyLeaseBased
		c.TraceLogger = writer
	}

	nt := newNetworkWithConfig(cfgFunc, nil, nil, nil)
	n1 := nt.peers[1].(*raft)

	nt.send(pb.Message{From: 1, To: 1, Type: pb.MsgHup})
	if n1.state != StateLeader {
		t.Fatalf("setup failed: n1 should be leader, got %v", n1.state)
	}

	// A real committed entry in the current term is required before
	// ReadIndex will actually respond (committedEntryInCurrentTerm()).
	nt.send(pb.Message{From: 1, To: 1, Type: pb.MsgProp, Entries: []pb.Entry{{Data: []byte("seed")}}})

	stateBefore := n1.state
	termBefore := n1.Term
	voteBefore := n1.Vote
	commitBefore := n1.raftLog.committed

	// The real, adversarial construction: issue a real MsgReadIndex.
	ctx := []byte("linearizable-read-ctx")
	nt.send(pb.Message{From: 1, To: 1, Type: pb.MsgReadIndex, Entries: []pb.Entry{{Data: ctx}}})

	// Extend the scenario with more real activity, purely to clear the
	// TLA+ spec's Len(TraceLog) div 100 threshold (the same real,
	// unrelated constraint encountered in RA-002).
	for i := 0; i < 20; i++ {
		nt.send(pb.Message{From: 1, To: 1, Type: pb.MsgProp, Entries: []pb.Entry{{Data: []byte("filler")}}})
	}

	stateAfter := n1.state
	termAfter := n1.Term
	voteAfter := n1.Vote
	commitAfterReadIndex := n1.raftLog.committed // will differ due to filler proposals; recorded for the record only

	f.Sync()

	t.Logf("RA-004: state before=%v after=%v | term before=%d after=%d | vote before=%d after=%d",
		stateBefore, stateAfter, termBefore, termAfter, voteBefore, voteAfter)
	t.Logf("RA-004: commit before ReadIndex=%d, after (including filler proposals)=%d", commitBefore, commitAfterReadIndex)

	if len(n1.readStates) == 0 {
		t.Errorf("RA-004: construction invalid -- ReadIndex request produced no readState; the mechanism was not actually exercised")
	} else {
		t.Logf("RA-004: CONFIRMED ReadIndex materially completed -- %d real readState(s) produced, e.g. index=%d ctx=%q",
			len(n1.readStates), n1.readStates[0].Index, n1.readStates[0].RequestCtx)
	}

	readIndexEventsFound := 0
	totalEvents := 0
	fileBytes, err := os.ReadFile("/tmp/ra004_trace.ndjson")
	if err != nil {
		t.Fatalf("read back trace file: %v", err)
	}
	for _, line := range splitLines(fileBytes) {
		if len(line) == 0 {
			continue
		}
		totalEvents++
		if bytesContains(line, []byte(`"type":"MsgReadIndex"`)) || bytesContains(line, []byte(`"type":"MsgReadIndexResp"`)) {
			readIndexEventsFound++
		}
	}
	t.Logf("RA-004: total real trace events written to file: %d", totalEvents)
	t.Logf("RA-004: trace events tagged MsgReadIndex/MsgReadIndexResp: %d", readIndexEventsFound)

	if stateBefore == stateAfter && termBefore == termAfter && voteBefore == voteAfter {
		t.Logf("RA-004: CONFIRMED -- role/term/vote fields identical before and after the ReadIndex round-trip; if commit index also matches what a trace-only replay would compute, ReadIndex is a genuine candidate for a trace-invisible-yet-real mechanism")
	} else {
		t.Logf("RA-004: role/term/vote fields differ before/after -- ReadIndex construction was NOT trace-invisible in the intended sense")
	}
}

func splitLines(b []byte) [][]byte {
	var out [][]byte
	start := 0
	for i, c := range b {
		if c == '\n' {
			out = append(out, b[start:i])
			start = i + 1
		}
	}
	if start < len(b) {
		out = append(out, b[start:])
	}
	return out
}

func bytesContains(haystack, needle []byte) bool {
	if len(needle) == 0 || len(haystack) < len(needle) {
		return false
	}
	for i := 0; i+len(needle) <= len(haystack); i++ {
		match := true
		for j := range needle {
			if haystack[i+j] != needle[j] {
				match = false
				break
			}
		}
		if match {
			return true
		}
	}
	return false
}

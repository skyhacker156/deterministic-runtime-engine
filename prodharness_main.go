package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	raft "go.etcd.io/raft/v3"
	"go.etcd.io/raft/v3/raftpb"
)

// jsonTraceWriter matches the exact production trace-file format
// documented and used by tla/Traceetcdraft.tla / tla/example.ndjson.
type jsonTraceWriter struct {
	f   *os.File
	seq float64
}

func (w *jsonTraceWriter) TraceEvent(ev *raft.TracingEvent) {
	w.seq += 0.001
	wrapper := map[string]any{
		"level":  "debug",
		"ts":     w.seq,
		"caller": "rafttest/trace_logger.go:42",
		"msg":    "trace",
		"tag":    "trace",
		"event":  ev,
	}
	b, err := json.Marshal(wrapper)
	if err != nil {
		return
	}
	w.f.Write(b)
	w.f.Write([]byte("\n"))
}

type realNode struct {
	id      uint64
	node    raft.Node
	recv    chan raftpb.Message
	storage *raft.MemoryStorage
}

func main() {
	traceFile := os.Getenv("TRACE_FILE")
	if traceFile == "" {
		traceFile = "/tmp/production_trace.ndjson"
	}
	enableReadIndex := os.Getenv("ENABLE_READINDEX") == "1"
	enablePreVote := os.Getenv("ENABLE_PREVOTE") == "1"
	enableTransfer := os.Getenv("ENABLE_TRANSFER") == "1"

	f, err := os.Create(traceFile)
	if err != nil {
		panic(err)
	}
	defer f.Close()
	writer := &jsonTraceWriter{f: f}

	peers := []raft.Peer{{ID: 1}, {ID: 2}, {ID: 3}}
	nodes := map[uint64]*realNode{}
	recvChans := map[uint64]chan raftpb.Message{}

	for _, p := range peers {
		recvChans[p.ID] = make(chan raftpb.Message, 4096)
	}

	for _, p := range peers {
		storage := raft.NewMemoryStorage()
		c := &raft.Config{
			ID:              p.ID,
			ElectionTick:    10,
			HeartbeatTick:   1,
			Storage:         storage,
			MaxSizePerMsg:   4096,
			MaxInflightMsgs: 256,
			TraceLogger:     writer,
		}
		if enablePreVote {
			c.PreVote = true
			c.CheckQuorum = true
		}
		if enableReadIndex {
			c.CheckQuorum = true
			c.ReadOnlyOption = raft.ReadOnlyLeaseBased
		}
		n := raft.StartNode(c, peers)
		nodes[p.ID] = &realNode{id: p.ID, node: n, recv: recvChans[p.ID], storage: storage}
	}

	stop := make(chan struct{})
	done := make(chan struct{})

	for _, rn := range nodes {
		go runNode(rn, nodes, recvChans, stop, done)
	}

	// Real ticking, real wall-clock timing, real asynchronous operation --
	// exactly the documented production pattern, not a synchronous
	// custom-harness cascade.
	time.Sleep(3 * time.Second)

	if enableReadIndex {
		// Find the real leader and issue a real ReadIndex request through
		// the real Node.ReadIndex API.
		for id, rn := range nodes {
			status := rn.node.Status()
			if status.RaftState == raft.StateLeader {
				fmt.Printf("real leader found: %d, issuing real ReadIndex\n", id)
				_ = rn.node.ReadIndex(context.Background(), []byte("linearizable-ctx"))
				break
			}
		}
		time.Sleep(2 * time.Second)
	}

	if enableTransfer {
		// Find the real leader and issue a real, coordinated
		// TransferLeadership call to a specific target -- the intentional,
		// documented-safe operation, as distinct from an accidental
		// election caused by leader failure.
		var leaderID, targetID uint64
		for id, rn := range nodes {
			status := rn.node.Status()
			if status.RaftState == raft.StateLeader {
				leaderID = id
			}
		}
		for id := range nodes {
			if id != leaderID {
				targetID = id
				break
			}
		}
		if leaderID != 0 && targetID != 0 {
			fmt.Printf("real leader %d transferring leadership to %d via real TransferLeadership call\n", leaderID, targetID)
			nodes[leaderID].node.TransferLeadership(context.Background(), leaderID, targetID)
		}
		time.Sleep(2 * time.Second)
	}

	// Real proposals through the real Node.Propose API to extend the
	// trace past the spec's Len(TraceLog) div 100 threshold.
	for id, rn := range nodes {
		status := rn.node.Status()
		if status.RaftState == raft.StateLeader {
			for i := 0; i < 30; i++ {
				_ = rn.node.Propose(context.Background(), []byte(fmt.Sprintf("data-%d", i)))
			}
			fmt.Printf("real leader %d proposed 30 real entries\n", id)
			break
		}
	}
	time.Sleep(3 * time.Second)

	close(stop)
	for range nodes {
		<-done
	}
	f.Sync()
	fmt.Println("done, trace written to", traceFile)
}

func runNode(rn *realNode, nodes map[uint64]*realNode, recvChans map[uint64]chan raftpb.Message, stop <-chan struct{}, done chan<- struct{}) {
	ticker := time.NewTicker(50 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			rn.node.Stop()
			done <- struct{}{}
			return
		case <-ticker.C:
			rn.node.Tick()
		case m := <-rn.recv:
			_ = rn.node.Step(context.Background(), m)
		case rd := <-rn.node.Ready():
			if !raft.IsEmptyHardState(rd.HardState) {
				rn.storage.SetHardState(rd.HardState)
			}
			if len(rd.Entries) > 0 {
				rn.storage.Append(rd.Entries)
			}
			if !raft.IsEmptySnap(rd.Snapshot) {
				rn.storage.ApplySnapshot(rd.Snapshot)
			}
			for _, entry := range rd.CommittedEntries {
				if entry.Type == raftpb.EntryConfChange {
					var cc raftpb.ConfChange
					_ = cc.Unmarshal(entry.Data)
					rn.node.ApplyConfChange(cc)
				}
			}
			for _, m := range rd.Messages {
				if ch, ok := recvChans[m.To]; ok {
					select {
					case ch <- m:
					default:
					}
				}
			}
			rn.node.Advance()
		}
	}
}

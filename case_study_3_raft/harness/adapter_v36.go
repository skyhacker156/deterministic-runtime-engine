//go:build raftv36

package main

import (
	"io"
	"log"

	"go.etcd.io/raft/v3"
	pb "go.etcd.io/raft/v3/raftpb"
)

const raftVersion = "v3.6.0"

type peer36 struct {
	rn *raft.RawNode
	ms *raft.MemoryStorage
}

func newPeer(id uint64, peers []uint64) (Peer, error) {
	ms := raft.NewMemoryStorage()
	// Start every node from the same snapshot at index 1, term 1, holding the
	// three-voter configuration. This is the library's restart-from-snapshot
	// path and avoids ConfChange bootstrapping.
	if err := ms.ApplySnapshot(pb.Snapshot{Metadata: pb.SnapshotMetadata{
		Index: 1, Term: 1, ConfState: pb.ConfState{Voters: peers},
	}}); err != nil {
		return nil, err
	}
	cfg := &raft.Config{
		ID:              id,
		ElectionTick:    10,
		HeartbeatTick:   1,
		Storage:         ms,
		MaxSizePerMsg:   1 << 20,
		MaxInflightMsgs: 256,
		CheckQuorum:     true,
		PreVote:         true,
		ReadOnlyOption:  raft.ReadOnlySafe,
		Logger:          &raft.DefaultLogger{Logger: log.New(io.Discard, "", 0)},
	}
	rn, err := raft.NewRawNode(cfg)
	if err != nil {
		return nil, err
	}
	return &peer36{rn: rn, ms: ms}, nil
}

func conv36(m pb.Message) Msg {
	out := Msg{Type: m.Type.String(), From: m.From, To: m.To, Term: m.Term, Raw: m}
	switch m.Type {
	case pb.MsgReadIndex, pb.MsgReadIndexResp:
		if len(m.Entries) > 0 {
			out.Ctx = append([]byte(nil), m.Entries[0].Data...)
		}
	case pb.MsgHeartbeat, pb.MsgHeartbeatResp:
		out.Ctx = append([]byte(nil), m.Context...)
	}
	return out
}

func (p *peer36) Tick()                     { p.rn.Tick() }
func (p *peer36) Step(m Msg) error          { return p.rn.Step(m.Raw.(pb.Message)) }
func (p *peer36) Campaign() error           { return p.rn.Campaign() }
func (p *peer36) Propose(data []byte) error { return p.rn.Propose(data) }
func (p *peer36) ReadIndex(rctx []byte)     { p.rn.ReadIndex(rctx) }
func (p *peer36) HasReady() bool            { return p.rn.HasReady() }

func (p *peer36) Handle(send func(Msg), apply func([]Ent), logStep func(string)) []RS {
	rd := p.rn.Ready()
	if len(rd.Entries) > 0 {
		if err := p.ms.Append(rd.Entries); err != nil {
			panic(err)
		}
		logStep("entries")
	}
	if !raft.IsEmptyHardState(rd.HardState) {
		if err := p.ms.SetHardState(rd.HardState); err != nil {
			panic(err)
		}
		logStep("hardstate")
	}
	if !raft.IsEmptySnap(rd.Snapshot) {
		if err := p.ms.ApplySnapshot(rd.Snapshot); err != nil {
			panic(err)
		}
		logStep("snapshot")
	}
	for _, m := range rd.Messages {
		send(conv36(m))
	}
	logStep("send")
	ents := make([]Ent, 0, len(rd.CommittedEntries))
	for _, e := range rd.CommittedEntries {
		ents = append(ents, Ent{Index: e.Index, Data: e.Data, Normal: e.Type == pb.EntryNormal})
	}
	apply(ents)
	logStep("apply")
	p.rn.Advance(rd)
	logStep("advance")
	out := make([]RS, 0, len(rd.ReadStates))
	for _, r := range rd.ReadStates {
		out = append(out, RS{Index: r.Index, Ctx: append([]byte(nil), r.RequestCtx...)})
	}
	return out
}

func (p *peer36) Status() NodeStatus {
	st := p.rn.Status()
	return NodeStatus{Lead: st.Lead, Term: st.Term, Commit: st.Commit, Applied: st.Applied,
		State: st.RaftState.String()}
}

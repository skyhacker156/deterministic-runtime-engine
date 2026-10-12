//go:build raftv37

package main

import (
	"io"
	"log"

	"go.etcd.io/raft/v3"
	pb "go.etcd.io/raft/v3/raftpb"
)

const raftVersion = "v3.7.0"

type peer37 struct {
	rn *raft.RawNode
	ms *raft.MemoryStorage
}

func u64(v uint64) *uint64 { return &v }

func newPeer(id uint64, peers []uint64) (Peer, error) {
	ms := raft.NewMemoryStorage()
	if err := ms.ApplySnapshot(&pb.Snapshot{Metadata: &pb.SnapshotMetadata{
		Index: u64(1), Term: u64(1), ConfState: &pb.ConfState{Voters: peers},
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
	return &peer37{rn: rn, ms: ms}, nil
}

func conv37(m *pb.Message) Msg {
	out := Msg{Type: m.GetType().String(), From: m.GetFrom(), To: m.GetTo(), Term: m.GetTerm(), Raw: m}
	switch m.GetType() {
	case pb.MsgReadIndex, pb.MsgReadIndexResp:
		if len(m.GetEntries()) > 0 {
			out.Ctx = append([]byte(nil), m.GetEntries()[0].GetData()...)
		}
	case pb.MsgHeartbeat, pb.MsgHeartbeatResp:
		out.Ctx = append([]byte(nil), m.GetContext()...)
	}
	return out
}

func (p *peer37) Tick()                     { p.rn.Tick() }
func (p *peer37) Step(m Msg) error          { return p.rn.Step(m.Raw.(*pb.Message)) }
func (p *peer37) Campaign() error           { return p.rn.Campaign() }
func (p *peer37) Propose(data []byte) error { return p.rn.Propose(data) }
func (p *peer37) ReadIndex(rctx []byte)     { p.rn.ReadIndex(rctx) }
func (p *peer37) HasReady() bool            { return p.rn.HasReady() }

func (p *peer37) Handle(send func(Msg), apply func([]Ent), logStep func(string)) []RS {
	rd := p.rn.Ready()
	if len(rd.Entries) > 0 {
		if err := p.ms.Append(rd.Entries); err != nil {
			panic(err)
		}
		logStep("entries")
	}
	if rd.HardState != nil && !raft.IsEmptyHardState(rd.HardState) {
		if err := p.ms.SetHardState(rd.HardState); err != nil {
			panic(err)
		}
		logStep("hardstate")
	}
	if rd.Snapshot != nil && !raft.IsEmptySnap(rd.Snapshot) {
		if err := p.ms.ApplySnapshot(rd.Snapshot); err != nil {
			panic(err)
		}
		logStep("snapshot")
	}
	for _, m := range rd.Messages {
		send(conv37(m))
	}
	logStep("send")
	ents := make([]Ent, 0, len(rd.CommittedEntries))
	for _, e := range rd.CommittedEntries {
		ents = append(ents, Ent{Index: e.GetIndex(), Data: e.GetData(), Normal: e.GetType() == pb.EntryNormal})
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

func (p *peer37) Status() NodeStatus {
	st := p.rn.Status()
	return NodeStatus{Lead: st.Lead, Term: st.HardState.GetTerm(), Commit: st.HardState.GetCommit(),
		Applied: st.Applied, State: st.RaftState.String()}
}

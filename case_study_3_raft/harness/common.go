// Package main is the Case Study 3 harness: a deterministic simulator that
// drives three etcd raft RawNodes through a seeded, version-independent
// network and client schedule, records a client-observed history, and checks
// it with Porcupine. See CS3_EXECUTION_PLAN.md for the pre-registered design.
//
// The two library versions differ in their protobuf types, so all access to
// raft types goes through one adapter file per version, selected by build tag
// (adapter_v36.go with -tags raftv36, adapter_v37.go with -tags raftv37).
// Nothing outside the adapters imports raft.
package main

// Msg is a version-neutral view of a raft message. Raw holds the library's
// own message value and is what gets delivered.
type Msg struct {
	Type string
	From uint64
	To   uint64
	Term uint64
	// Ctx is the read request context for MsgReadIndex and MsgReadIndexResp
	// (the data of the first entry), and the heartbeat context for
	// MsgHeartbeat and MsgHeartbeatResp.
	Ctx []byte
	Raw any
}

// RS is a version-neutral ReadState.
type RS struct {
	Index uint64
	Ctx   []byte
}

// Ent is a committed entry, as the application sees it.
type Ent struct {
	Index  uint64
	Data   []byte
	Normal bool
}

// NodeStatus is the subset of raft status the harness uses.
type NodeStatus struct {
	Lead    uint64
	Term    uint64
	Commit  uint64
	Applied uint64
	State   string // "StateLeader", "StateFollower", ...
}

// Peer is the adapter interface. Handle processes exactly one Ready in the
// order the raft README requires and reports each step through logStep:
// "entries", "hardstate", "snapshot", "send", "apply", "advance".
type Peer interface {
	Tick()
	Step(m Msg) error
	Campaign() error
	Propose(data []byte) error
	ReadIndex(rctx []byte)
	HasReady() bool
	Handle(send func(Msg), apply func([]Ent), logStep func(string)) []RS
	Status() NodeStatus
}

var stepRank = map[string]int{
	"entries": 0, "hardstate": 1, "snapshot": 2, "send": 3, "apply": 4, "advance": 5,
}

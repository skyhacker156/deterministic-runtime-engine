package main

import (
	"fmt"
	"math/rand/v2"
)

// P1aResult is the outcome of one directed run of the #392 scenario
// (CS3_EXECUTION_PLAN.md section 3).
type P1aResult struct {
	Jitter      uint64     `json:"jitter"`
	Version     string     `json:"version"`
	Steps       []string   `json:"steps"`
	Ops         []OpRecord `json:"ops"`
	Verdict     string     `json:"verdict"`
	Shape392    bool       `json:"shape_392"`
	Conformance []string   `json:"conformance"`
	Aborted     string     `json:"aborted,omitempty"`
}

// RunP1a drives the section 3 trace. Every network action is a delay of a
// message (held, then released) or a partition; every client action is a
// ReadIndex, a retry with the same rctx, or a Propose. Jitter 0 is the
// canonical schedule; other values add 0-1 tick delays to messages outside
// the read path (votes, appends and their responses), which the trace
// should not depend on.
func RunP1a(jitter uint64) *P1aResult {
	res := &P1aResult{Jitter: jitter, Version: raftVersion}
	s, err := NewSim(defaultParams, 0xA1A1+jitter)
	if err != nil {
		res.Aborted = err.Error()
		return res
	}
	rng := rand.New(rand.NewPCG(jitter, 7))
	jit := func() int {
		if jitter == 0 {
			return 0
		}
		return rng.IntN(2)
	}
	step := func(label, f string, a ...any) {
		res.Steps = append(res.Steps, fmt.Sprintf("[tick %d] %s ", s.tick, label)+fmt.Sprintf(f, a...))
	}
	for n := 1; n <= 3; n++ {
		s.clients[n] = &client{id: n, node: uint64(n), cur: -1}
	}

	var ctxA string
	holdFirstRound, holdRetry, sawFirstA := false, false, false
	s.policy = func(m Msg) *holdRule {
		switch {
		case holdFirstRound && m.Type == "MsgHeartbeatResp" && m.To == 1:
			return &holdRule{Hold: true, Buf: "H"}
		case ctxA != "" && m.Type == "MsgReadIndexResp" && m.To == 2 && string(m.Ctx) == ctxA:
			return &holdRule{Hold: true, Buf: "RespA"}
		case ctxA != "" && m.Type == "MsgReadIndex" && m.To == 1 && string(m.Ctx) == ctxA:
			if !sawFirstA {
				sawFirstA = true
				return &holdRule{Delay: 0}
			}
			if holdRetry {
				holdRetry = false
				return &holdRule{Hold: true, Buf: "Dup"}
			}
		}
		switch m.Type {
		case "MsgHeartbeat", "MsgHeartbeatResp", "MsgReadIndex", "MsgReadIndexResp":
			return &holdRule{Delay: 0} // the read path is essential: never jittered
		}
		return &holdRule{Delay: jit()}
	}
	advance := func() {
		s.tick++
		s.tickH = 0
		for n := 1; n <= 3; n++ {
			s.clientStep(s.clients[n])
		}
		s.tickNodes()
		s.settle()
	}
	abort := func(f string, a ...any) *P1aResult {
		res.Aborted = fmt.Sprintf("tick %d: ", s.tick) + fmt.Sprintf(f, a...)
		res.Ops, res.Conformance = s.ops, s.Conformance
		return res
	}

	// 1. Node 1 elected leader in term t and its entry committed.
	s.peers[1].Campaign()
	s.settle()
	for i := 0; i < 40; i++ {
		if st := s.peers[1].Status(); st.State == "StateLeader" && st.Commit >= 2 {
			break
		}
		advance()
	}
	st1 := s.peers[1].Status()
	if st1.State != "StateLeader" {
		return abort("node 1 not leader after warmup")
	}
	termT, c1 := st1.Term, st1.Commit
	step("library", "node 1 leader, term %d, commit %d", termT, c1)

	// 2-3. Client 2 reads A through node 2; node 1's first heartbeat round
	// for it is answered, and the answers are delayed (held).
	holdFirstRound = true
	opA := s.invoke(s.clients[2], Op{Kind: "r"})
	ctxA = opA.Ctx
	idA := opA.ID
	s.settle()
	holdFirstRound = false
	step("client, compliant", "client 2 ReadIndex(%s) on node 2, forwarded to node 1", ctxA)
	step("network, legal delay", "%d heartbeat responses to node 1 held", len(s.holdBufs["H"]))
	if len(s.holdBufs["H"]) < 2 {
		return abort("expected two held heartbeat responses, got %d", len(s.holdBufs["H"]))
	}

	// 4. Later heartbeats confirm A at node 1, but the response to node 2 is
	// delayed, so client 2 times out and retries with the same rctx. The
	// retry is delayed in the network.
	for s.tick < opA.InvokeTick+s.P.ReadTimeout {
		holdRetry = true
		advance()
	}
	if len(s.holdBufs["RespA"]) == 0 {
		return abort("A was not confirmed at node 1 before the retry")
	}
	if len(s.holdBufs["Dup"]) != 1 {
		return abort("expected one held retry of %s, got %d", ctxA, len(s.holdBufs["Dup"]))
	}
	step("library", "node 1 confirmed %s; its MsgReadIndexResp to node 2 held (legal delay)", ctxA)
	step("client, compliant with released contract", "client 2 timed out, retried ReadIndex(%s), same rctx; retry held (legal delay)", ctxA)

	// 5. Node 1 partitioned; its tick source stalls (legal: timing is not
	// part of the safety model). Its process still handles messages.
	s.isolated[1] = true
	s.stalled[1] = true
	step("network, legal partition", "node 1 isolated; node 1 ticks stalled")

	// 6. Nodes 2 and 3 elect a new leader and commit its entry.
	var newLead uint64
	for i := 0; i < 120 && newLead == 0; i++ {
		advance()
		for _, n := range []uint64{2, 3} {
			if st := s.peers[n].Status(); st.State == "StateLeader" && st.Term > termT && st.Commit > c1 {
				newLead = n
			}
		}
	}
	if newLead == 0 {
		return abort("no new leader among nodes 2 and 3")
	}
	step("library", "node %d leader, term %d", newLead, s.peers[newLead].Status().Term)

	// 7. Client 3 writes w through node 3; it completes when node 3 applies it.
	const w = 42
	opW := s.invoke(s.clients[3], Op{Kind: "w", Value: w})
	idW := opW.ID
	for i := 0; i < 60 && s.ops[idW].Return < 0; i++ {
		advance()
	}
	if s.ops[idW].Return < 0 {
		return abort("write did not complete")
	}
	step("client, compliant", "client 3 write %d completed at log index %d", w, s.ops[idW].WriteIndex)

	// 8. After the write completed, client 1 reads B through node 1, which
	// still believes it is leader of term t.
	if st := s.peers[1].Status(); st.State != "StateLeader" || st.Term != termT {
		return abort("node 1 no longer leader of term %d: %+v", termT, st)
	}
	opB := s.invoke(s.clients[1], Op{Kind: "r"})
	idB := opB.ID
	s.settle()
	step("client, compliant", "client 1 ReadIndex(%s) on node 1 (stale leader)", s.ops[idB].Ctx)

	// 9. Partition heals. The delayed retry of A, then the delayed first-round
	// heartbeat responses, reach node 1 first.
	s.isolated[1] = false
	for _, m := range s.holdBufs["Dup"] {
		s.deliver(m)
	}
	for _, m := range s.holdBufs["H"] {
		s.deliver(m)
	}
	s.holdBufs["Dup"], s.holdBufs["H"] = nil, nil
	s.handleAll()
	s.serveReads()
	step("network, legal reordering", "partition healed; delivered held retry of %s, then held heartbeat responses", ctxA)
	if rs := s.ops[idB].ReadStates; len(rs) > 0 {
		step("library", "node 1 ReadState for %s, index %d", s.ops[idB].Ctx, rs[0].Index)
	} else {
		step("library", "node 1 produced no ReadState for %s", s.ops[idB].Ctx)
	}

	// 10-11. Everything else is released; run a few ticks to finish.
	s.releaseIsolation()
	for _, m := range s.holdBufs["RespA"] {
		s.route(m)
	}
	s.holdBufs["RespA"] = nil
	s.stalled[1] = false
	s.policy = nil
	for i := 0; i < 30; i++ {
		advance()
	}
	_ = idA

	res.Ops, res.Conformance = s.ops, s.Conformance
	res.Verdict = Check(s.ops)
	res.Shape392 = has392Shape(s.ops)
	return res
}

// has392Shape reports a read whose first ReadState is flagged against the
// client-history bound, whose rctx was submitted once, and which was
// confirmed while another rctx with two or more deliveries was pending at
// the same node (CS3_EXECUTION_PLAN.md section 7).
func has392Shape(ops []OpRecord) bool {
	for _, o := range ops {
		if o.Kind != "r" || !o.FlagClient || len(o.Subs) != 1 || len(o.ReadStates) == 0 {
			continue
		}
		for _, p := range o.ReadStates[0].Pending {
			if p.Ctx != o.Ctx && p.Deliveries >= 2 {
				return true
			}
		}
	}
	return false
}

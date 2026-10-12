package main

import (
	"encoding/binary"
	"fmt"
	"hash/fnv"
	"sort"
)

type inflight struct {
	m     Msg
	at    int
	order int64
}

// holdRule lets a directed scenario (P1a) override the network for chosen
// messages. A nil policy means the pre-generated Fate is used.
type holdRule struct {
	Hold  bool
	Buf   string
	Delay int
}

type client struct {
	id      int
	node    uint64
	ops     []Op
	next    int
	readyAt int
	cur     int // index into Sim.ops, or -1
}

type Sim struct {
	P    Params
	seed uint64

	peers [4]Peer
	tick  int
	ev    int64
	order int64

	queue     []inflight
	isolated  [4]bool
	isoUntil  [4]int
	paused    [4]bool
	pauseUtil [4]int
	isoHold   []Msg
	pauseHold [4][]Msg
	linkSeq   map[[2]uint64]uint64

	reg          [4]int64
	applied      [4]uint64
	writeIdxByV  map[int64]uint64
	ops          []OpRecord
	clients      [4]*client
	started      bool
	ctxOwner     map[string]int
	pendingAt    [4]map[string]bool
	deliveriesAt [4]map[string]int

	// directed-scenario controls
	policy   func(m Msg) *holdRule
	holdBufs map[string][]Msg
	stalled  [4]bool

	// records
	Conformance []string
	FaultLog    []string
	TickHash    []uint32
	tickH       uint32
	Sent        int
	Dropped     int
}

func NewSim(p Params, seed uint64) (*Sim, error) {
	seedCryptoRand(seed)
	s := &Sim{P: p, seed: seed, linkSeq: map[[2]uint64]uint64{}, writeIdxByV: map[int64]uint64{},
		ctxOwner: map[string]int{}, holdBufs: map[string][]Msg{}}
	ids := []uint64{1, 2, 3}
	for _, id := range ids {
		pr, err := newPeer(id, ids)
		if err != nil {
			return nil, err
		}
		s.peers[id] = pr
		s.pendingAt[id] = map[string]bool{}
		s.deliveriesAt[id] = map[string]int{}
	}
	return s, nil
}

func (s *Sim) nextEv() int64 { s.ev++; return s.ev }

func (s *Sim) noteConformance(format string, a ...any) {
	s.Conformance = append(s.Conformance, fmt.Sprintf("tick %d: ", s.tick)+fmt.Sprintf(format, a...))
}

// ---- network ----

func (s *Sim) send(m Msg) {
	s.order++
	s.Sent++
	h := fnv.New32a()
	fmt.Fprintf(h, "%s|%d|%d|", m.Type, m.From, m.To)
	s.tickH = s.tickH*16777619 ^ h.Sum32()

	link := [2]uint64{m.From, m.To}
	seq := s.linkSeq[link]
	s.linkSeq[link] = seq + 1

	if s.policy != nil {
		if r := s.policy(m); r != nil {
			if r.Hold {
				s.holdBufs[r.Buf] = append(s.holdBufs[r.Buf], m)
				return
			}
			s.queue = append(s.queue, inflight{m: m, at: s.tick + r.Delay, order: s.order})
			return
		}
	}
	drop, delay := Fate(s.P, s.seed, m.From, m.To, seq)
	if drop {
		s.Dropped++
		return
	}
	s.queue = append(s.queue, inflight{m: m, at: s.tick + delay, order: s.order})
}

func (s *Sim) cut(a, b uint64) bool { return s.isolated[a] || s.isolated[b] }

// route applies isolation and pause at delivery time.
func (s *Sim) route(m Msg) {
	switch {
	case s.cut(m.From, m.To):
		s.isoHold = append(s.isoHold, m)
	case s.paused[m.To]:
		s.pauseHold[m.To] = append(s.pauseHold[m.To], m)
	default:
		s.deliver(m)
	}
}

func (s *Sim) deliver(m Msg) {
	s.nextEv()
	if m.Type == "MsgReadIndex" {
		c := string(m.Ctx)
		s.pendingAt[m.To][c] = true
		s.deliveriesAt[m.To][c]++
	}
	_ = s.peers[m.To].Step(m) // errors such as dropped proposals are library behaviour
}

func (s *Sim) dueCount() int {
	n := 0
	for _, f := range s.queue {
		if f.at <= s.tick {
			n++
		}
	}
	return n
}

func (s *Sim) deliverDue() bool {
	var due, rest []inflight
	for _, f := range s.queue {
		if f.at <= s.tick {
			due = append(due, f)
		} else {
			rest = append(rest, f)
		}
	}
	if len(due) == 0 {
		return false
	}
	sort.SliceStable(due, func(i, j int) bool {
		if due[i].at != due[j].at {
			return due[i].at < due[j].at
		}
		return due[i].order < due[j].order
	})
	s.queue = rest
	for _, f := range due {
		s.route(f.m)
	}
	return true
}

func (s *Sim) releaseIsolation() {
	var keep []Msg
	for _, m := range s.isoHold {
		if s.cut(m.From, m.To) {
			keep = append(keep, m)
			continue
		}
		if s.paused[m.To] {
			s.pauseHold[m.To] = append(s.pauseHold[m.To], m)
			continue
		}
		s.deliver(m)
	}
	s.isoHold = keep
}

func (s *Sim) releasePause(n uint64) {
	held := s.pauseHold[n]
	s.pauseHold[n] = nil
	for _, m := range held {
		s.route(m)
	}
}

// ---- nodes ----

func (s *Sim) pendingSnapshot(n uint64) []PendingEntry {
	var keys []string
	for k, v := range s.pendingAt[n] {
		if v {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)
	out := make([]PendingEntry, 0, len(keys))
	for _, k := range keys {
		out = append(out, PendingEntry{Ctx: k, Deliveries: s.deliveriesAt[n][k]})
	}
	return out
}

func (s *Sim) handle(n uint64) {
	pend := s.pendingSnapshot(n)
	var steps []string
	rss := s.peers[n].Handle(
		func(m Msg) {
			if m.Type == "MsgReadIndexResp" {
				delete(s.pendingAt[n], string(m.Ctx))
			}
			s.send(m)
		},
		func(ents []Ent) { s.apply(n, ents) },
		func(step string) { steps = append(steps, step) },
	)
	last := -1
	for _, st := range steps {
		if stepRank[st] < last {
			s.noteConformance("node %d Ready steps out of contract order: %v", n, steps)
			break
		}
		last = stepRank[st]
	}
	if len(steps) == 0 || steps[len(steps)-1] != "advance" {
		s.noteConformance("node %d Ready not advanced: %v", n, steps)
	}
	for _, r := range rss {
		s.onReadState(n, r, pend)
	}
}

func (s *Sim) handleAll() bool {
	any := false
	for n := uint64(1); n <= 3; n++ {
		for !s.paused[n] && s.peers[n].HasReady() {
			s.handle(n)
			any = true
		}
	}
	return any
}

func (s *Sim) apply(n uint64, ents []Ent) {
	for _, e := range ents {
		if e.Index != s.applied[n]+1 && s.applied[n] != 0 {
			s.noteConformance("node %d applied index %d after %d", n, e.Index, s.applied[n])
		}
		s.applied[n] = e.Index
		if !e.Normal {
			// Nodes start from a snapshot holding the configuration and no
			// configuration change is ever proposed, so this must not happen.
			s.noteConformance("node %d committed a non-normal entry at index %d", n, e.Index)
			continue
		}
		if len(e.Data) != 8 {
			continue
		}
		v := int64(binary.LittleEndian.Uint64(e.Data))
		s.reg[n] = v
		if _, ok := s.writeIdxByV[v]; !ok {
			s.writeIdxByV[v] = e.Index
		}
		c := s.clients[n]
		if c != nil && c.cur >= 0 {
			op := &s.ops[c.cur]
			if op.Kind == "w" && op.Value == v && op.Return < 0 {
				op.WriteIndex = e.Index
				op.Return = s.nextEv()
				op.ReturnTick = s.tick
				s.finish(c)
			}
		}
	}
}

func (s *Sim) onReadState(n uint64, r RS, pend []PendingEntry) {
	c := string(r.Ctx)
	delete(s.pendingAt[n], c)
	id, ok := s.ctxOwner[c]
	if !ok {
		s.noteConformance("node %d ReadState for unknown ctx %q", n, c)
		return
	}
	op := &s.ops[id]
	if uint64(op.Client) != n {
		s.noteConformance("ReadState for ctx %q arrived at node %d, not the client's node %d", c, n, op.Client)
	}
	op.ReadStates = append(op.ReadStates, RSRecord{Node: n, Index: r.Index, Tick: s.tick, Event: s.ev,
		Term: s.peers[n].Status().Term, Pending: pend})
	if len(op.ReadStates) == 1 {
		var bound uint64
		for i := range s.ops {
			w := &s.ops[i]
			if w.Kind == "w" && w.Return >= 0 && w.Return < op.Invoke && w.WriteIndex > bound {
				bound = w.WriteIndex
			}
		}
		op.ClientBound = bound
		op.LibraryBound = op.Subs[0].MaxCommit
		op.FlagClient = r.Index < bound
		op.FlagLibrary = r.Index < op.LibraryBound
	}
}

func (s *Sim) serveReads() {
	for n := uint64(1); n <= 3; n++ {
		c := s.clients[n]
		if c == nil || c.cur < 0 || s.paused[n] {
			continue
		}
		op := &s.ops[c.cur]
		if op.Kind != "r" || op.Return >= 0 || len(op.ReadStates) == 0 {
			continue
		}
		idx := op.ReadStates[0].Index
		if s.applied[n] < idx {
			continue
		}
		op.Value = s.reg[n]
		op.Return = s.nextEv()
		op.ReturnTick = s.tick
		s.finish(c)
	}
}

// settle delivers due messages and processes Readys until quiescent.
func (s *Sim) settle() {
	for i := 0; i < 100000; i++ {
		a := s.deliverDue()
		b := s.handleAll()
		s.serveReads()
		if !a && !b {
			return
		}
	}
	s.noteConformance("settle did not quiesce")
}

func (s *Sim) tickNodes() {
	s.nextEv()
	for n := uint64(1); n <= 3; n++ {
		if !s.paused[n] && !s.stalled[n] {
			s.peers[n].Tick()
		}
	}
}

// ---- clients ----

func (s *Sim) finish(c *client) {
	c.cur = -1
	if c.next < len(c.ops) {
		c.readyAt = s.tick + c.ops[c.next].Think
	}
}

func (s *Sim) maxCommit() uint64 {
	var m uint64
	for n := uint64(1); n <= 3; n++ {
		if v := s.peers[n].Status().Commit; v > m {
			m = v
		}
	}
	return m
}

func (s *Sim) submit(op *OpRecord) {
	n := uint64(op.Client)
	op.Subs = append(op.Subs, Submission{Tick: s.tick, Event: s.nextEv(), MaxCommit: s.maxCommit()})
	if s.peers[n].Status().State == "StateLeader" {
		s.pendingAt[n][op.Ctx] = true
		s.deliveriesAt[n][op.Ctx]++
	}
	s.peers[n].ReadIndex([]byte(op.Ctx))
}

func (s *Sim) invoke(c *client, op Op) *OpRecord {
	rec := OpRecord{ID: len(s.ops), Client: c.id, Kind: op.Kind, Value: op.Value, Return: -1,
		InvokeTick: s.tick, ReturnTick: -1}
	rec.Invoke = s.nextEv()
	s.ops = append(s.ops, rec)
	c.cur = rec.ID
	p := &s.ops[rec.ID]
	switch op.Kind {
	case "w":
		var b [8]byte
		binary.LittleEndian.PutUint64(b[:], uint64(op.Value))
		if err := s.peers[c.node].Propose(b[:]); err != nil {
			p.Dropped = true
		}
	case "r":
		p.Value = 0
		p.Ctx = fmt.Sprintf("c%d-%d", c.id, rec.ID)
		if _, dup := s.ctxOwner[p.Ctx]; dup {
			s.noteConformance("ctx %q reused across logical reads", p.Ctx)
		}
		s.ctxOwner[p.Ctx] = rec.ID
		s.submit(p)
	}
	return p
}

func (s *Sim) clientStep(c *client) {
	if s.paused[c.node] {
		return
	}
	if c.cur >= 0 {
		op := &s.ops[c.cur]
		switch op.Kind {
		case "r":
			if len(op.ReadStates) == 0 && s.tick-op.Subs[len(op.Subs)-1].Tick >= s.P.ReadTimeout {
				if len(op.Subs) < s.P.MaxSubmissions {
					s.submit(op)
				} else {
					s.finish(c) // incomplete read
				}
			}
		case "w":
			if s.tick-op.InvokeTick >= s.P.WriteTimeout {
				s.finish(c) // incomplete write
			}
		}
		return
	}
	if c.next >= len(c.ops) || s.tick < c.readyAt {
		return
	}
	op := c.ops[c.next]
	c.next++
	s.invoke(c, op)
}

func (s *Sim) clientsDone() bool {
	for n := 1; n <= 3; n++ {
		c := s.clients[n]
		if c.cur >= 0 || c.next < len(c.ops) {
			return false
		}
	}
	return true
}

// ---- faults ----

func (s *Sim) resolve(target string) (uint64, bool) {
	if target != "LEADER" {
		var n uint64
		fmt.Sscan(target, &n)
		return n, true
	}
	var best, bestTerm uint64
	for n := uint64(1); n <= 3; n++ {
		st := s.peers[n].Status()
		if st.State == "StateLeader" && st.Term >= bestTerm {
			best, bestTerm = n, st.Term
		}
	}
	return best, best != 0
}

func (s *Sim) applyFaults(sch *Schedule) {
	for n := uint64(1); n <= 3; n++ {
		if s.isolated[n] && s.isoUntil[n] == s.tick {
			s.isolated[n] = false
			s.FaultLog = append(s.FaultLog, fmt.Sprintf("%d end isolate %d", s.tick, n))
			s.releaseIsolation()
		}
		if s.paused[n] && s.pauseUtil[n] == s.tick {
			s.paused[n] = false
			s.FaultLog = append(s.FaultLog, fmt.Sprintf("%d end pause %d", s.tick, n))
			s.releasePause(n)
		}
	}
	for _, f := range sch.Faults {
		if f.Start != s.tick {
			continue
		}
		n, ok := s.resolve(f.Target)
		if !ok {
			s.FaultLog = append(s.FaultLog, fmt.Sprintf("%d skip %s %s (no leader)", s.tick, f.Kind, f.Target))
			continue
		}
		end := s.tick + f.Dur
		switch f.Kind {
		case "isolate":
			s.isolated[n] = true
			if end > s.isoUntil[n] {
				s.isoUntil[n] = end
			}
		case "pause":
			s.paused[n] = true
			if end > s.pauseUtil[n] {
				s.pauseUtil[n] = end
			}
		}
		s.FaultLog = append(s.FaultLog, fmt.Sprintf("%d %s %d (target %s) until %d", s.tick, f.Kind, n, f.Target, end))
	}
}

// ---- randomized trial ----

func (s *Sim) RunSchedule(sch *Schedule) {
	for n := 1; n <= 3; n++ {
		s.clients[n] = &client{id: n, node: uint64(n), ops: sch.Ops[n-1], cur: -1}
	}
	for s.tick = 0; s.tick < s.P.MaxTicks; s.tick++ {
		s.tickH = 0
		s.applyFaults(sch)
		if !s.started {
			for n := uint64(1); n <= 3; n++ {
				st := s.peers[n].Status()
				if st.State == "StateLeader" && st.Commit >= 2 {
					s.started = true
				}
			}
			if s.started {
				for n := 1; n <= 3; n++ {
					c := s.clients[n]
					if len(c.ops) > 0 {
						c.readyAt = s.tick + c.ops[0].Think
					}
				}
			}
		}
		if s.started {
			for n := 1; n <= 3; n++ {
				s.clientStep(s.clients[n])
			}
		}
		s.tickNodes()
		s.settle()
		s.TickHash = append(s.TickHash, s.tickH)
		if s.started && s.clientsDone() {
			break
		}
	}
}

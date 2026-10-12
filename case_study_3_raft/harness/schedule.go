package main

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/rand/v2"
)

// Schedule holds everything exogenous to the library for one trial. It is
// generated from the seed alone, before any run, and is identical for both
// library versions. Per-message fates are not stored: they are a keyed hash
// of (seed, from, to, per-link sequence number), defined by Fate below, whose
// parameters are part of the schedule and therefore of its hash.
type Schedule struct {
	Seed           uint64  `json:"seed"`
	LeaderTargeted bool    `json:"leader_targeted"`
	Params         Params  `json:"params"`
	Ops            [3][]Op `json:"ops"` // index 0 = client attached to node 1
	Faults         []Fault `json:"faults"`
}

type Params struct {
	Nodes          int     `json:"nodes"`
	OpsPerClient   int     `json:"ops_per_client"`
	ReadFraction   float64 `json:"read_fraction"`
	MaxTicks       int     `json:"max_ticks"`
	DropP          float64 `json:"drop_p"`
	LongDelayP     float64 `json:"long_delay_p"`
	ShortDelayMax  int     `json:"short_delay_max"`
	LongDelayMin   int     `json:"long_delay_min"`
	LongDelayMax   int     `json:"long_delay_max"`
	ReadTimeout    int     `json:"read_timeout"`
	MaxSubmissions int     `json:"max_submissions"`
	WriteTimeout   int     `json:"write_timeout"`
	FaultStart     int     `json:"fault_start"`
}

var defaultParams = Params{
	Nodes: 3, OpsPerClient: 100, ReadFraction: 0.70, MaxTicks: 6000,
	DropP: 0.05, LongDelayP: 0.02, ShortDelayMax: 5, LongDelayMin: 10, LongDelayMax: 40,
	ReadTimeout: 10, MaxSubmissions: 5, WriteTimeout: 60, FaultStart: 50,
}

type Op struct {
	Kind  string `json:"k"` // "r" or "w"
	Value int64  `json:"v,omitempty"`
	Think int    `json:"t"` // ticks to wait before invoking
}

type Fault struct {
	Kind   string `json:"kind"`   // "isolate" or "pause"
	Start  int    `json:"start"`  // tick
	Dur    int    `json:"dur"`    // ticks
	Target string `json:"target"` // "1", "2", "3" or "LEADER"
}

func GenSchedule(seed uint64, leaderTargeted bool) *Schedule {
	p := defaultParams
	r := rand.New(rand.NewPCG(seed, 0xc53))
	s := &Schedule{Seed: seed, LeaderTargeted: leaderTargeted, Params: p}
	for c := 0; c < 3; c++ {
		for k := 0; k < p.OpsPerClient; k++ {
			op := Op{Think: r.IntN(4)}
			if r.Float64() < p.ReadFraction {
				op.Kind = "r"
			} else {
				op.Kind = "w"
				op.Value = int64((c+1)*1_000_000 + k + 1) // unique across the run
			}
			s.Ops[c] = append(s.Ops[c], op)
		}
	}
	target := func() string {
		if leaderTargeted {
			return "LEADER"
		}
		return fmt.Sprint(1 + r.IntN(3))
	}
	for t := p.FaultStart + 100 + r.IntN(200); t < p.MaxTicks; t += 100 + r.IntN(201) {
		s.Faults = append(s.Faults, Fault{Kind: "isolate", Start: t, Dur: 15 + r.IntN(26), Target: target()})
	}
	for t := p.FaultStart + 150 + r.IntN(300); t < p.MaxTicks; t += 150 + r.IntN(301) {
		s.Faults = append(s.Faults, Fault{Kind: "pause", Start: t, Dur: 15 + r.IntN(26), Target: target()})
	}
	return s
}

func (s *Schedule) Hash() string {
	b, err := json.Marshal(s)
	if err != nil {
		panic(err)
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}

// Fate decides, independently of the library, what the network does to the
// seq-th message sent on the link from->to in this trial.
func Fate(p Params, seed, from, to, seq uint64) (drop bool, delay int) {
	var buf [32]byte
	binary.LittleEndian.PutUint64(buf[0:], seed)
	binary.LittleEndian.PutUint64(buf[8:], from)
	binary.LittleEndian.PutUint64(buf[16:], to)
	binary.LittleEndian.PutUint64(buf[24:], seq)
	h := sha256.Sum256(buf[:])
	u := func(i int) float64 { return float64(binary.LittleEndian.Uint64(h[i*8:])>>11) / (1 << 53) }
	if u(0) < p.DropP {
		return true, 0
	}
	if u(1) < p.LongDelayP {
		return false, p.LongDelayMin + int(u(2)*float64(p.LongDelayMax-p.LongDelayMin+1))
	}
	return false, int(u(3) * float64(p.ShortDelayMax+1))
}

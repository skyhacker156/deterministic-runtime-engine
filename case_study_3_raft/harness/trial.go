package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
)

type Result struct {
	Arm           string   `json:"arm"`
	Seed          uint64   `json:"seed"`
	Version       string   `json:"version"`
	ScheduleHash  string   `json:"schedule_hash"`
	HistoryHash   string   `json:"history_hash"`
	Verdict       string   `json:"verdict"` // Ok, Illegal, Unknown, or Discarded (conformance)
	Conformance   []string `json:"conformance,omitempty"`
	Ticks         int      `json:"ticks"`
	Reads         int      `json:"reads"`
	ReadsComplete int      `json:"reads_complete"`
	ReadsMultiSub int      `json:"reads_multi_sub"`
	Writes        int      `json:"writes"`
	WritesDone    int      `json:"writes_complete"`
	FlagClient    int      `json:"flag_client"`
	FlagLibrary   int      `json:"flag_library"`
	Shape392      int      `json:"shape_392"`
	Sent          int      `json:"sent"`
	Dropped       int      `json:"dropped"`
	Faults        []string `json:"faults"`
	Replayed      bool     `json:"replayed,omitempty"`
	ReplayMatch   *bool    `json:"replay_match,omitempty"`
}

// HistoryBytes is the canonical history file: one JSON object per line.
func HistoryBytes(ops []OpRecord) []byte {
	var b bytes.Buffer
	enc := json.NewEncoder(&b)
	for _, o := range ops {
		if err := enc.Encode(o); err != nil {
			panic(err)
		}
	}
	return b.Bytes()
}

func sha(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }

func TickHashBytes(th []uint32) []byte {
	b := make([]byte, 4*len(th))
	for i, v := range th {
		binary.LittleEndian.PutUint32(b[i*4:], v)
	}
	return b
}

// RunTrial runs one schedule and returns the result row, the history file
// and the per-tick message digests (for locating version divergence).
func RunTrial(arm string, sch *Schedule) (*Result, []byte, []byte, error) {
	s, err := NewSim(sch.Params, sch.Seed)
	if err != nil {
		return nil, nil, nil, err
	}
	s.RunSchedule(sch)
	// Operations still outstanding at the end stay incomplete (Return -1).
	hist := HistoryBytes(s.ops)
	r := &Result{Arm: arm, Seed: sch.Seed, Version: raftVersion, ScheduleHash: sch.Hash(),
		HistoryHash: sha(hist), Conformance: s.Conformance, Ticks: s.tick, Sent: s.Sent,
		Dropped: s.Dropped, Faults: s.FaultLog}
	for _, o := range s.ops {
		switch o.Kind {
		case "r":
			r.Reads++
			if o.Return >= 0 {
				r.ReadsComplete++
			}
			if len(o.Subs) > 1 {
				r.ReadsMultiSub++
			}
			if o.FlagClient {
				r.FlagClient++
			}
			if o.FlagLibrary {
				r.FlagLibrary++
			}
		case "w":
			r.Writes++
			if o.Return >= 0 {
				r.WritesDone++
			}
		}
	}
	for i := range s.ops {
		if has392Shape(s.ops[i : i+1]) {
			r.Shape392++
		}
	}
	if len(s.Conformance) > 0 {
		r.Verdict = "Discarded"
	} else {
		r.Verdict = Check(s.ops)
	}
	return r, hist, TickHashBytes(s.TickHash), nil
}

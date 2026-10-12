package main

import (
	"math"
	"time"

	"github.com/anishathalye/porcupine"
)

// OpRecord is one logical client operation. Invoke and Return are values of
// the simulator's global event counter, assigned at the moment each event
// happens (see CS3_EXECUTION_PLAN.md section 5). Return is -1 if incomplete.
type OpRecord struct {
	ID         int          `json:"id"`
	Client     int          `json:"client"` // 1..3, attached to node of the same number
	Kind       string       `json:"kind"`
	Value      int64        `json:"value"` // write value, or value returned by a read
	Invoke     int64        `json:"invoke"`
	Return     int64        `json:"return"`
	InvokeTick int          `json:"invoke_tick"`
	ReturnTick int          `json:"return_tick"`
	Ctx        string       `json:"ctx,omitempty"`
	Subs       []Submission `json:"subs,omitempty"`
	ReadStates []RSRecord   `json:"read_states,omitempty"`
	WriteIndex uint64       `json:"write_index,omitempty"` // log index at which a write was applied
	Dropped    bool         `json:"dropped,omitempty"`     // Propose returned an error
	// Attribution, filled when the first ReadState for the read arrives.
	ClientBound  uint64 `json:"client_bound,omitempty"`  // log index of latest write completed before invoke
	LibraryBound uint64 `json:"library_bound,omitempty"` // max commit index on any node at first submission
	FlagClient   bool   `json:"flag_client,omitempty"`
	FlagLibrary  bool   `json:"flag_library,omitempty"`
}

type Submission struct {
	Tick      int    `json:"tick"`
	Event     int64  `json:"event"`
	MaxCommit uint64 `json:"max_commit"`
}

// RSRecord is one ReadState received for this read, with harness-observed
// context: the node and its term, and which request contexts were pending at
// that node (delivered to it and not yet answered), with delivery counts.
type RSRecord struct {
	Node    uint64         `json:"node"`
	Index   uint64         `json:"index"`
	Tick    int            `json:"tick"`
	Event   int64          `json:"event"`
	Term    uint64         `json:"term"`
	Pending []PendingEntry `json:"pending"`
}

type PendingEntry struct {
	Ctx        string `json:"ctx"`
	Deliveries int    `json:"deliveries"`
}

type regIn struct {
	Write bool
	V     int64
}

var registerModel = porcupine.Model{
	Init: func() interface{} { return int64(0) },
	Step: func(state, input, output interface{}) (bool, interface{}) {
		in := input.(regIn)
		if in.Write {
			return true, in.V
		}
		return output.(int64) == state.(int64), state
	},
	Equal: func(a, b interface{}) bool { return a.(int64) == b.(int64) },
}

// ToPorcupine encodes a history: incomplete writes get an infinite return
// time (they may or may not have taken effect); incomplete reads are dropped
// (they have no effect and returned nothing).
func ToPorcupine(ops []OpRecord) []porcupine.Operation {
	var out []porcupine.Operation
	for _, o := range ops {
		if o.Invoke < 0 {
			continue // never invoked
		}
		switch o.Kind {
		case "w":
			ret := o.Return
			if ret < 0 {
				ret = math.MaxInt64
			}
			out = append(out, porcupine.Operation{ClientId: o.Client - 1, Input: regIn{Write: true, V: o.Value},
				Call: o.Invoke, Output: int64(0), Return: ret})
		case "r":
			if o.Return < 0 {
				continue
			}
			out = append(out, porcupine.Operation{ClientId: o.Client - 1, Input: regIn{},
				Call: o.Invoke, Output: o.Value, Return: o.Return})
		}
	}
	return out
}

const checkTimeout = 60 * time.Second

// Check returns "Ok", "Illegal" or "Unknown". Unknown is never a pass.
func Check(ops []OpRecord) string {
	return string(porcupine.CheckOperationsTimeout(registerModel, ToPorcupine(ops), checkTimeout))
}

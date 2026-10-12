package main

import "fmt"

// SelfTest checks the oracle and the history encoding on hand-built
// histories with known verdicts, through the same ToPorcupine path the
// harness uses (CS3_EXECUTION_PLAN.md section 5). p1aOps, if non-nil, is a
// recorded P1a history from the v3.6.0 build, expected non-linearizable.
func SelfTest(p1aOps []OpRecord) error {
	w := func(id, c int, v, call, ret int64) OpRecord {
		return OpRecord{ID: id, Client: c, Kind: "w", Value: v, Invoke: call, Return: ret}
	}
	r := func(id, c int, v, call, ret int64) OpRecord {
		return OpRecord{ID: id, Client: c, Kind: "r", Value: v, Invoke: call, Return: ret}
	}
	cases := []struct {
		name string
		ops  []OpRecord
		want string
	}{
		{"a1 overlapping writes, read sees first", []OpRecord{w(0, 1, 1, 1, 4), w(1, 2, 2, 2, 5), r(2, 3, 1, 3, 6)}, "Ok"},
		{"a2 overlapping writes, read sees second", []OpRecord{w(0, 1, 1, 1, 4), w(1, 2, 2, 2, 5), r(2, 3, 2, 3, 6)}, "Ok"},
		{"b write returns before read invoked, read stale", []OpRecord{w(0, 1, 1, 1, 2), r(1, 2, 0, 3, 4)}, "Illegal"},
		{"c read invoked before write returns, read old", []OpRecord{w(0, 1, 1, 1, 3), r(1, 2, 0, 2, 4)}, "Ok"},
		{"e1 incomplete write, read sees it", []OpRecord{w(0, 1, 1, 1, -1), r(1, 2, 1, 3, 4)}, "Ok"},
		{"e2 incomplete write, read does not", []OpRecord{w(0, 1, 1, 1, -1), r(1, 2, 0, 3, 4)}, "Ok"},
		{"e3 incomplete read is dropped", []OpRecord{w(0, 1, 1, 1, 2), r(1, 2, 0, 3, -1)}, "Ok"},
	}
	if p1aOps != nil {
		cases = append(cases, struct {
			name string
			ops  []OpRecord
			want string
		}{"d recorded P1a history (v3.6.0)", p1aOps, "Illegal"})
	}
	for _, c := range cases {
		if got := Check(c.ops); got != c.want {
			return fmt.Errorf("self-test %q: got %s, want %s", c.name, got, c.want)
		}
	}
	return checkCryptoRandOverride()
}

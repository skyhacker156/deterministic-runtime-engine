// Package oracle applies the CS4 pre-registered rules to the server and
// client logs. Every constant and prediction here is copied from
// CS4_PLAN.md (commit ca4ccaa), as amended by CS4_AMENDMENT_1.md (ae942d8).
// The expected behaviour comes from the plan, never from a client.
package oracle

import (
	"fmt"
	"sort"
	"strings"

	"cs4harness/internal/cs4"
)

// Calls per scenario per configuration.
const (
	DecisionCalls = 20
	TimingCalls   = 50
	TimingDelays  = 4 // maxAttempts 5
)

// X2 elapsed classes (deadline 2 s).
const (
	ImmediateBelowNs = 500_000_000
	WaitedAtLeastNs  = 1_800_000_000
)

// Timing thresholds, r = delay / 200 ms.
const (
	RLow          = 0.80
	RHigh         = 1.30
	A6MinAtMostHi = 0.95
	OldMinBelowLo = 0.70
)

// Timing classes.
const (
	ClassA6      = "A6_RANGE"
	ClassOld     = "OLD_RANGE"
	ClassNeither = "NEITHER"
)

// Verdicts.
const (
	Match            = "MATCH"
	Mismatch         = "MISMATCH"
	Nondeterministic = "NONDETERMINISTIC"
	Incomplete       = "INCOMPLETE"
	Recorded         = "RECORDED" // no prediction (X4)
	Unexpected       = "UNEXPECTED_CONFIG"
)

// DecisionPredictions: configuration -> scenario -> predicted tuple.
// Tuple format: "attempts,FINAL" or, for X2 rows, "attempts,class,FINAL"
// with FINAL "*" for waited calls (status recorded, not scored).
var DecisionPredictions = map[string]map[string]string{
	"go184": {
		"S": "2,OK", "X5": "1,OK", "X1": "1,INVALID_ARGUMENT",
		"X2HI": "1,waited,*", "X2MAX": "1,waited,*", "X2NEG": "1,immediate,UNAVAILABLE",
		"X4P": "", "X4Z": "",
	},
	"java": {
		"S": "2,OK", "X5": "2,OK", "X1": "2,OK",
		"X2HI": "1,immediate,UNAVAILABLE", "X2MAX": "1,waited,*", "X2NEG": "1,immediate,UNAVAILABLE",
		"X4P": "", "X4Z": "",
	},
	"goMX1": {"S": "2,OK", "X1": "2,OK"},
	"goMX5": {"S": "2,OK", "X5": "2,OK"},
}

// TimingPredictions: configuration -> predicted class for scenario T.
var TimingPredictions = map[string]string{
	"go168":        ClassOld,
	"go184":        ClassA6,
	"java":         ClassA6,
	"javaNoJitter": ClassOld,
}

func isX2(scenario string) bool { return strings.HasPrefix(scenario, "X2") }

// ElapsedClass classifies an X2 call's client-side elapsed time.
func ElapsedClass(ns int64) string {
	switch {
	case ns < ImmediateBelowNs:
		return "immediate"
	case ns >= WaitedAtLeastNs:
		return "waited"
	}
	return "other"
}

// Tuple builds the outcome tuple of one call.
func Tuple(scenario string, attempts int, final string, elapsedNs int64) string {
	if !isX2(scenario) {
		return fmt.Sprintf("%d,%s", attempts, final)
	}
	class := ElapsedClass(elapsedNs)
	if class == "waited" {
		final = "*"
	}
	return fmt.Sprintf("%d,%s,%s", attempts, class, final)
}

// DecisionResult is the verdict for one (configuration, scenario).
type DecisionResult struct {
	Config    string         `json:"config"`
	Scenario  string         `json:"scenario"`
	Calls     int            `json:"calls"`
	Tuples    map[string]int `json:"tuples"`
	Finals    map[string]int `json:"finals"`
	Predicted string         `json:"predicted"`
	Verdict   string         `json:"verdict"`
}

// TimingResult is the verdict for one configuration on scenario T.
type TimingResult struct {
	Config         string  `json:"config"`
	Calls          int     `json:"calls"`
	Delays         int     `json:"delays"`
	FracBelowLow   float64 `json:"frac_r_below_0_80"`
	FracAtMostHigh float64 `json:"frac_r_at_most_1_30"`
	MinR           float64 `json:"min_r"`
	MedianR        float64 `json:"median_r"`
	MaxR           float64 `json:"max_r"`
	Class          string  `json:"class"`
	Predicted      string  `json:"predicted"`
	Verdict        string  `json:"verdict"`
	MalformedCalls int     `json:"malformed_calls"`
}

// Report is the checker's whole output.
type Report struct {
	Decision        []DecisionResult `json:"decision"`
	Timing          []TimingResult   `json:"timing"`
	OrphanAttempts  int              `json:"orphan_server_attempts"`
	MislabeledCalls int              `json:"mislabeled_server_attempts"`
}

type key struct{ config, scenario string }

// Analyze applies the plan's rules to the logs.
func Analyze(server []cs4.ServerRecord, client []cs4.ClientRecord) Report {
	byCall := map[string][]cs4.ServerRecord{}
	for _, r := range server {
		byCall[r.CallID] = append(byCall[r.CallID], r)
	}
	seen := map[string]bool{}
	groups := map[key][]cs4.ClientRecord{}
	var rep Report
	for _, c := range client {
		seen[c.CallID] = true
		groups[key{c.Client, c.Scenario}] = append(groups[key{c.Client, c.Scenario}], c)
		for _, s := range byCall[c.CallID] {
			if s.Client != c.Client || s.Scenario != c.Scenario {
				rep.MislabeledCalls++
			}
		}
	}
	for id, rs := range byCall {
		if !seen[id] {
			rep.OrphanAttempts += len(rs)
		}
	}

	keys := make([]key, 0, len(groups))
	for k := range groups {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i].config != keys[j].config {
			return keys[i].config < keys[j].config
		}
		return keys[i].scenario < keys[j].scenario
	})

	for _, k := range keys {
		calls := groups[k]
		if k.scenario == "T" {
			rep.Timing = append(rep.Timing, analyzeTiming(k.config, calls, byCall))
			continue
		}
		rep.Decision = append(rep.Decision, analyzeDecision(k, calls, byCall))
	}
	return rep
}

func analyzeDecision(k key, calls []cs4.ClientRecord, byCall map[string][]cs4.ServerRecord) DecisionResult {
	d := DecisionResult{Config: k.config, Scenario: k.scenario, Calls: len(calls),
		Tuples: map[string]int{}, Finals: map[string]int{}}
	for _, c := range calls {
		d.Tuples[Tuple(k.scenario, len(byCall[c.CallID]), c.FinalCode, c.ElapsedNs)]++
		d.Finals[c.FinalCode]++
	}
	preds, okConfig := DecisionPredictions[k.config]
	pred, okScenario := preds[k.scenario]
	d.Predicted = pred
	switch {
	case !okConfig || !okScenario:
		d.Verdict = Unexpected
	case len(calls) != DecisionCalls:
		d.Verdict = Incomplete
	case len(d.Tuples) != 1:
		d.Verdict = Nondeterministic
	case pred == "":
		d.Verdict = Recorded
	default:
		d.Verdict = Mismatch
		if d.Tuples[pred] == len(calls) {
			d.Verdict = Match
		}
	}
	return d
}

// Delays returns the server-side gaps between consecutive attempts of one
// call, ordered by attempt number. ok is false if attempt numbers are not
// exactly 1..n.
func Delays(rs []cs4.ServerRecord) (delays []int64, ok bool) {
	sorted := append([]cs4.ServerRecord(nil), rs...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].Attempt < sorted[j].Attempt })
	for i, r := range sorted {
		if r.Attempt != i+1 {
			return nil, false
		}
		if i > 0 {
			delays = append(delays, r.TNanos-sorted[i-1].TNanos)
		}
	}
	return delays, true
}

// ClassifyTiming applies the plan's timing classification to ratios r.
func ClassifyTiming(rs []float64) (class string, fracBelow, fracAtMost float64) {
	if len(rs) == 0 {
		return ClassNeither, 0, 0
	}
	below, atMost := 0, 0
	for _, r := range rs {
		if r < RLow {
			below++
		}
		if r <= RHigh {
			atMost++
		}
	}
	n := float64(len(rs))
	fracBelow, fracAtMost = float64(below)/n, float64(atMost)/n
	switch {
	case below == 0 && fracAtMost >= A6MinAtMostHi:
		class = ClassA6
	case fracBelow >= OldMinBelowLo:
		class = ClassOld
	default:
		class = ClassNeither
	}
	return class, fracBelow, fracAtMost
}

func analyzeTiming(config string, calls []cs4.ClientRecord, byCall map[string][]cs4.ServerRecord) TimingResult {
	t := TimingResult{Config: config, Calls: len(calls)}
	var rs []float64
	for _, c := range calls {
		ds, ok := Delays(byCall[c.CallID])
		if !ok || len(ds) != TimingDelays {
			t.MalformedCalls++
		}
		for _, d := range ds {
			rs = append(rs, float64(d)/float64(cs4.BackoffNanos))
		}
	}
	t.Delays = len(rs)
	t.Class, t.FracBelowLow, t.FracAtMostHigh = ClassifyTiming(rs)
	if len(rs) > 0 {
		s := append([]float64(nil), rs...)
		sort.Float64s(s)
		t.MinR, t.MaxR, t.MedianR = s[0], s[len(s)-1], s[len(s)/2]
	}
	pred, ok := TimingPredictions[config]
	t.Predicted = pred
	switch {
	case !ok:
		t.Verdict = Unexpected
	case t.Calls != TimingCalls || t.Delays != TimingCalls*TimingDelays || t.MalformedCalls != 0:
		t.Verdict = Incomplete
	case t.Class == pred:
		t.Verdict = Match
	default:
		t.Verdict = Mismatch
	}
	return t
}

// ReplayView returns the replay-comparable part of a report: per decision
// scenario, the outcome tuples only (no finals of waited calls, no timing,
// no timestamps). Its canonical JSON must be byte-identical across a full
// rerun (plan, "Replay rule").
func (r Report) ReplayView() []DecisionResult {
	out := make([]DecisionResult, 0, len(r.Decision))
	for _, d := range r.Decision {
		d.Finals = nil
		out = append(out, d)
	}
	return out
}

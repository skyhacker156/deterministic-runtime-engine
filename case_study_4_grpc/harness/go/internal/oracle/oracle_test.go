package oracle

// Oracle self-test (plan, "Controls"): synthetic logs, one per verdict class
// in both tracks, plus boundary values and the C1 wire rule. Run with
//   go test -v ./internal/oracle
// before any scored run. No gRPC code is involved.

import (
	"encoding/json"
	"fmt"
	"math/rand/v2"
	"testing"

	"cs4harness/internal/cs4"
)

const ms = int64(1_000_000)

// call describes one synthetic call: attempt arrival times (server side),
// final status and client elapsed time.
type call struct {
	arrivals []int64
	final    string
	elapsed  int64
}

func build(config, scenario string, calls []call) ([]cs4.ServerRecord, []cs4.ClientRecord) {
	var srv []cs4.ServerRecord
	var cli []cs4.ClientRecord
	for i, c := range calls {
		id := fmt.Sprintf("%s-%s-%03d", config, scenario, i)
		for k, t := range c.arrivals {
			srv = append(srv, cs4.ServerRecord{TNanos: t, CallID: id, Scenario: scenario, Client: config, Attempt: k + 1})
		}
		cli = append(cli, cs4.ClientRecord{Client: config, Scenario: scenario, CallID: id, FinalCode: c.final, ElapsedNs: c.elapsed})
	}
	return srv, cli
}

func repeat(n int, c call) []call {
	out := make([]call, n)
	for i := range out {
		out[i] = c
	}
	return out
}

func one(t *testing.T, config, scenario string, calls []call) DecisionResult {
	t.Helper()
	srv, cli := build(config, scenario, calls)
	rep := Analyze(srv, cli)
	if len(rep.Decision) != 1 {
		t.Fatalf("want 1 decision result, got %d", len(rep.Decision))
	}
	return rep.Decision[0]
}

func TestDecisionVerdicts(t *testing.T) {
	oneAttemptOK := call{arrivals: []int64{0}, final: "OK", elapsed: 5 * ms}
	twoAttemptsOK := call{arrivals: []int64{0, 12 * ms}, final: "OK", elapsed: 20 * ms}
	cases := []struct {
		name, config, scenario string
		calls                  []call
		want                   string
	}{
		{"go184 X5 no retry", "go184", "X5", repeat(20, oneAttemptOK), Match},
		{"java X5 retried", "java", "X5", repeat(20, twoAttemptsOK), Match},
		{"java X5 not retried (falsification shape)", "java", "X5", repeat(20, oneAttemptOK), Mismatch},
		{"java X5 mixed", "java", "X5", append(repeat(10, oneAttemptOK), repeat(10, twoAttemptsOK)...), Nondeterministic},
		{"go184 S short", "go184", "S", repeat(19, twoAttemptsOK), Incomplete},
		{"go184 X4P recorded", "go184", "X4P", repeat(20, twoAttemptsOK), Recorded},
		{"unknown config", "foo", "S", repeat(20, twoAttemptsOK), Unexpected},
		{"goMX5 detected", "goMX5", "X5", repeat(20, twoAttemptsOK), Match},
		{"goMX5 not detected", "goMX5", "X5", repeat(20, oneAttemptOK), Mismatch},
		{"goMX1 detected", "goMX1", "X1", repeat(20, twoAttemptsOK), Match},
		{"go184 X1 fatal", "go184", "X1", repeat(20, call{arrivals: []int64{0}, final: "INVALID_ARGUMENT", elapsed: 3 * ms}), Match},
		{"go184 X2HI waited", "go184", "X2HI", repeat(20, call{arrivals: []int64{0}, final: "DEADLINE_EXCEEDED", elapsed: 2000 * ms}), Match},
		{"java X2HI immediate", "java", "X2HI", repeat(20, call{arrivals: []int64{0}, final: "UNAVAILABLE", elapsed: 10 * ms}), Match},
		{"java X2HI waited", "java", "X2HI", repeat(20, call{arrivals: []int64{0}, final: "DEADLINE_EXCEEDED", elapsed: 2000 * ms}), Mismatch},
		{"java X2HI other", "java", "X2HI", repeat(20, call{arrivals: []int64{0}, final: "UNAVAILABLE", elapsed: 1000 * ms}), Mismatch},
		{"java X2HI immediate wrong status", "java", "X2HI", repeat(20, call{arrivals: []int64{0}, final: "INTERNAL", elapsed: 10 * ms}), Mismatch},
		{"java X2MAX waited any status", "java", "X2MAX", repeat(20, call{arrivals: []int64{0}, final: "CANCELLED", elapsed: 1900 * ms}), Match},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := one(t, c.config, c.scenario, c.calls)
			if got.Verdict != c.want {
				t.Fatalf("verdict %s, want %s (tuples %v, predicted %q)", got.Verdict, c.want, got.Tuples, got.Predicted)
			}
		})
	}
}

func TestElapsedBoundaries(t *testing.T) {
	cases := map[int64]string{
		0: "immediate", ImmediateBelowNs - 1: "immediate", ImmediateBelowNs: "other",
		WaitedAtLeastNs - 1: "other", WaitedAtLeastNs: "waited", 5000 * ms: "waited",
	}
	for ns, want := range cases {
		if got := ElapsedClass(ns); got != want {
			t.Errorf("ElapsedClass(%d) = %s, want %s", ns, got, want)
		}
	}
}

func TestOrphansAndLabels(t *testing.T) {
	srv, cli := build("go184", "S", repeat(20, call{arrivals: []int64{0, 15 * ms}, final: "OK"}))
	srv = append(srv, cs4.ServerRecord{CallID: "stray", Attempt: 1, Client: "go184", Scenario: "S"})
	srv[0].Scenario = "X5"
	rep := Analyze(srv, cli)
	if rep.OrphanAttempts != 1 || rep.MislabeledCalls != 1 {
		t.Fatalf("orphans %d mislabeled %d, want 1 and 1", rep.OrphanAttempts, rep.MislabeledCalls)
	}
}

// timingCalls builds n calls of 5 attempts whose gaps are factor()*200ms + overhead.
func timingCalls(n int, factor func() float64, overhead int64) []call {
	out := make([]call, n)
	for i := range out {
		t := int64(0)
		arr := []int64{0}
		for k := 0; k < TimingDelays; k++ {
			t += int64(factor()*float64(cs4.BackoffNanos)) + overhead
			arr = append(arr, t)
		}
		out[i] = call{arrivals: arr, final: "UNAVAILABLE"}
	}
	return out
}

func timing(t *testing.T, config string, calls []call) TimingResult {
	t.Helper()
	srv, cli := build(config, "T", calls)
	rep := Analyze(srv, cli)
	if len(rep.Timing) != 1 {
		t.Fatalf("want 1 timing result, got %d", len(rep.Timing))
	}
	return rep.Timing[0]
}

func TestTimingVerdicts(t *testing.T) {
	r := rand.New(rand.NewPCG(4, 2026))
	a6 := func() float64 { return 0.8 + 0.4*r.Float64() }
	old := func() float64 { return r.Float64() }
	const overhead = 2 * ms

	if got := timing(t, "go184", timingCalls(50, a6, overhead)); got.Class != ClassA6 || got.Verdict != Match {
		t.Errorf("A6 sample: class %s verdict %s", got.Class, got.Verdict)
	}
	if got := timing(t, "java", timingCalls(50, a6, overhead)); got.Verdict != Match {
		t.Errorf("java A6 sample: verdict %s", got.Verdict)
	}
	if got := timing(t, "go168", timingCalls(50, old, overhead)); got.Class != ClassOld || got.Verdict != Match {
		t.Errorf("old sample (control): class %s verdict %s", got.Class, got.Verdict)
	}
	if got := timing(t, "javaNoJitter", timingCalls(50, old, overhead)); got.Verdict != Match {
		t.Errorf("javaNoJitter old sample: verdict %s", got.Verdict)
	}
	if got := timing(t, "go184", timingCalls(50, old, overhead)); got.Verdict != Mismatch {
		t.Errorf("go184 with old sample: verdict %s, want MISMATCH", got.Verdict)
	}
	if got := timing(t, "go168", timingCalls(50, a6, overhead)); got.Verdict != Mismatch {
		t.Errorf("go168 with A6 sample (invalid timing oracle): verdict %s, want MISMATCH", got.Verdict)
	}
	half := 0
	neither := func() float64 {
		half++
		if half%2 == 0 {
			return 0.5
		}
		return 1.0
	}
	if got := timing(t, "go184", timingCalls(50, neither, 0)); got.Class != ClassNeither {
		t.Errorf("half-and-half sample: class %s, want NEITHER", got.Class)
	}
	if got := timing(t, "go184", timingCalls(49, a6, overhead)); got.Verdict != Incomplete {
		t.Errorf("49 calls: verdict %s, want INCOMPLETE", got.Verdict)
	}
	short := timingCalls(50, a6, overhead)
	short[7].arrivals = short[7].arrivals[:3]
	if got := timing(t, "go184", short); got.Verdict != Incomplete || got.MalformedCalls != 1 {
		t.Errorf("one short call: verdict %s malformed %d", got.Verdict, got.MalformedCalls)
	}
}

func TestTimingBoundaries(t *testing.T) {
	fill := func(n int, v float64) []float64 {
		s := make([]float64, n)
		for i := range s {
			s[i] = v
		}
		return s
	}
	if c, _, _ := ClassifyTiming(fill(200, RLow)); c != ClassA6 {
		t.Errorf("all r = 0.80: %s, want A6 (0.80 is not below 0.80)", c)
	}
	if c, _, _ := ClassifyTiming(append(fill(199, 1.0), 0.7999)); c != ClassNeither {
		t.Errorf("one r below 0.80: %s, want NEITHER", c)
	}
	if c, _, _ := ClassifyTiming(append(fill(190, RHigh), fill(10, 2.0)...)); c != ClassA6 {
		t.Errorf("exactly 95%% at most RHigh: %s, want A6", c)
	}
	if c, _, _ := ClassifyTiming(append(fill(189, 1.0), fill(11, 1.41)...)); c != ClassNeither {
		t.Errorf("94.5%% at most 1.40: %s, want NEITHER", c)
	}
	// Amendment 2: r = 1.35 is within the A6 upper bound (it was not under the
	// pre-registered 1.30). Fails if RHigh reverts to 1.30.
	if c, _, _ := ClassifyTiming(append(fill(180, 1.0), fill(20, 1.35)...)); c != ClassA6 {
		t.Errorf("10%% of r at 1.35: %s, want A6 under amendment 2", c)
	}
	if RHigh != 1.40 {
		t.Errorf("RHigh = %v, want 1.40 (CS4_AMENDMENT_2.md)", RHigh)
	}
	if c, _, _ := ClassifyTiming(append(fill(140, 0.5), fill(60, 1.0)...)); c != ClassOld {
		t.Errorf("exactly 70%% below 0.80: %s, want OLD", c)
	}
	if c, _, _ := ClassifyTiming(append(fill(139, 0.5), fill(61, 1.0)...)); c != ClassNeither {
		t.Errorf("69.5%% below 0.80: %s, want NEITHER", c)
	}
}

func TestReplayViewIgnoresWaitedStatusAndTiming(t *testing.T) {
	a := []call{{arrivals: []int64{0}, final: "DEADLINE_EXCEEDED", elapsed: 2001 * ms}}
	b := []call{{arrivals: []int64{0}, final: "CANCELLED", elapsed: 2300 * ms}}
	sa, ca := build("java", "X2MAX", repeat(20, a[0]))
	sb, cb := build("java", "X2MAX", repeat(20, b[0]))
	ja, _ := json.Marshal(Analyze(sa, ca).ReplayView())
	jb, _ := json.Marshal(Analyze(sb, cb).ReplayView())
	if string(ja) != string(jb) {
		t.Fatalf("replay views differ:\n%s\n%s", ja, jb)
	}
	sc, cc := build("java", "X2MAX", repeat(20, call{arrivals: []int64{0}, final: "UNAVAILABLE", elapsed: 10 * ms}))
	jc, _ := json.Marshal(Analyze(sc, cc).ReplayView())
	if string(ja) == string(jc) {
		t.Fatal("replay view failed to distinguish waited from immediate")
	}
}

func c1Frames(mod func(*Frame)) []Frame {
	h := Frame{Dir: "s2c", Type: "HEADERS", Stream: 1, EndStream: true, EndHdrs: true,
		Headers: [][2]string{{":status", "200"}, {"content-type", "application/grpc"}, {"grpc-status", "0"}, {"grpc-message", ""}, {"grpc-retry-pushback-ms", "10"}}}
	if mod != nil {
		mod(&h)
	}
	return []Frame{
		{Dir: "s2c", Type: "SETTINGS", Stream: 0},
		{Dir: "c2s", Type: "HEADERS", Stream: 1, EndHdrs: true},
		{Dir: "c2s", Type: "DATA", Stream: 1, EndStream: true, Length: 60},
		h,
	}
}

func TestC1(t *testing.T) {
	if r := CheckC1(c1Frames(nil)); !r.Pass {
		t.Errorf("trailers-only frame set failed: %v", r.Reasons)
	}
	withWU := append(c1Frames(nil), Frame{Dir: "s2c", Type: "WINDOW_UPDATE", Stream: 1})
	if r := CheckC1(withWU); !r.Pass || len(r.Other) != 1 {
		t.Errorf("WINDOW_UPDATE should be listed, not failed: pass %v other %v reasons %v", r.Pass, r.Other, r.Reasons)
	}
	fails := map[string][]Frame{
		"no END_STREAM":  c1Frames(func(f *Frame) { f.EndStream = false }),
		"no END_HEADERS": c1Frames(func(f *Frame) { f.EndHdrs = false }),
		"no pushback":    c1Frames(func(f *Frame) { f.Headers = f.Headers[:4] }),
		"status 14":      c1Frames(func(f *Frame) { f.Headers[2][1] = "14" }),
		"status 500":     c1Frames(func(f *Frame) { f.Headers[0][1] = "500" }),
		"pushback 11":    c1Frames(func(f *Frame) { f.Headers[4][1] = "11" }),
		"second stream":  append(c1Frames(nil), Frame{Dir: "s2c", Type: "HEADERS", Stream: 3, EndStream: true, EndHdrs: true}),
		"normal response": {
			{Dir: "s2c", Type: "HEADERS", Stream: 1, EndHdrs: true, Headers: [][2]string{{":status", "200"}}},
			{Dir: "s2c", Type: "DATA", Stream: 1, Length: 5},
			{Dir: "s2c", Type: "HEADERS", Stream: 1, EndStream: true, EndHdrs: true, Headers: [][2]string{{"grpc-status", "0"}, {"grpc-retry-pushback-ms", "10"}}},
		},
		"no frames": nil,
	}
	for name, fs := range fails {
		if r := CheckC1(fs); r.Pass {
			t.Errorf("%s: passed, want fail", name)
		}
	}
}

// TestScenarioTable pins the server behaviour to the plan's table.
func TestScenarioTable(t *testing.T) {
	r := func(code, pushback string) cs4.Response { return cs4.Response{Code: code, Pushback: pushback} }
	want := map[string][2]cs4.Response{
		"S":     {r("UNAVAILABLE", "10"), r("OK", "")},
		"X5":    {r("OK", "10"), r("OK", "")},
		"X1":    {r("INVALID_ARGUMENT", "10"), r("OK", "")},
		"X2HI":  {r("UNAVAILABLE", "2147483648"), r("UNAVAILABLE", "2147483648")},
		"X2MAX": {r("UNAVAILABLE", "2147483647"), r("UNAVAILABLE", "2147483647")},
		"X2NEG": {r("UNAVAILABLE", "-1"), r("UNAVAILABLE", "-1")},
		"X4P":   {r("UNAVAILABLE", "+5"), r("OK", "")},
		"X4Z":   {r("UNAVAILABLE", "007"), r("OK", "")},
		"T":     {r("UNAVAILABLE", ""), r("UNAVAILABLE", "")},
	}
	if len(want) != len(cs4.Scenarios) {
		t.Fatalf("scenario count %d, want %d", len(cs4.Scenarios), len(want))
	}
	for name, w := range want {
		s, ok := cs4.Scenarios[name]
		if !ok {
			t.Fatalf("missing scenario %s", name)
		}
		if s.ResponseFor(1) != w[0] || s.ResponseFor(2) != w[1] || s.ResponseFor(5) != w[1] {
			t.Errorf("%s: got %v/%v", name, s.ResponseFor(1), s.ResponseFor(2))
		}
		wantDeadline := 10000
		if isX2(name) {
			wantDeadline = 2000
		}
		if s.Deadline != wantDeadline {
			t.Errorf("%s: deadline %d, want %d", name, s.Deadline, wantDeadline)
		}
		if s.Timing != (name == "T") {
			t.Errorf("%s: timing flag %v", name, s.Timing)
		}
	}
	var sc map[string]any
	if err := json.Unmarshal([]byte(cs4.ServiceConfig(false)), &sc); err != nil {
		t.Fatal(err)
	}
	rp := sc["methodConfig"].([]any)[0].(map[string]any)["retryPolicy"].(map[string]any)
	if rp["maxAttempts"].(float64) != 3 || rp["initialBackoff"] != "0.2s" || rp["maxBackoff"] != "0.2s" || rp["backoffMultiplier"].(float64) != 1 {
		t.Errorf("decision policy wrong: %v", rp)
	}
	if _, ok := sc["retryThrottling"]; ok {
		t.Error("retryThrottling must not be configured")
	}
	json.Unmarshal([]byte(cs4.ServiceConfig(true)), &sc)
	rp = sc["methodConfig"].([]any)[0].(map[string]any)["retryPolicy"].(map[string]any)
	if rp["maxAttempts"].(float64) != 5 {
		t.Errorf("timing policy maxAttempts %v, want 5", rp["maxAttempts"])
	}
}

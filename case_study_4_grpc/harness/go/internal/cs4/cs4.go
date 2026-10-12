// Package cs4 holds what the Case Study 4 server, clients and checker share:
// the wire codec, the scenario table (what the server sends on attempt k),
// the retry policies, and the log record formats.
//
// Source of every value here: case_study_4_grpc/CS4_PLAN.md (pre-registration,
// commit ca4ccaa) as amended by CS4_AMENDMENT_1.md (commit ae942d8).
package cs4

import (
	"encoding/json"
	"fmt"
)

// Service and method. One server-streaming method; the handler never sends a
// message, so every response is trailers-only unless headers are forced.
const (
	ServiceName = "cs4.Probe"
	MethodName  = "Run"
	FullMethod  = "/cs4.Probe/Run"
)

// PushbackKey is the A6 server pushback trailer.
const PushbackKey = "grpc-retry-pushback-ms"

// RawCodec passes []byte through unchanged. It implements the
// encoding.Codec (v1) interface of grpc-go v1.68.2 and v1.84.0 without
// importing grpc, so this package builds against either version.
type RawCodec struct{}

func (RawCodec) Name() string { return "cs4raw" }

func (RawCodec) Marshal(v any) ([]byte, error) {
	switch b := v.(type) {
	case []byte:
		return b, nil
	case *[]byte:
		return *b, nil
	}
	return nil, fmt.Errorf("cs4raw: cannot marshal %T", v)
}

func (RawCodec) Unmarshal(data []byte, v any) error {
	p, ok := v.(*[]byte)
	if !ok {
		return fmt.Errorf("cs4raw: cannot unmarshal into %T", v)
	}
	*p = append((*p)[:0], data...)
	return nil
}

// Request is the JSON body of every call. The server keys attempts on CallID.
type Request struct {
	CallID   string `json:"call_id"`
	Scenario string `json:"scenario"`
	Client   string `json:"client"`
}

// Response is what the server sends for one attempt: a status code name and
// an optional pushback value ("" means no pushback trailer).
type Response struct {
	Code     string
	Pushback string
}

// Scenario describes the server's behaviour for one scenario.
type Scenario struct {
	Name     string
	First    Response // attempt 1
	Later    Response // attempts 2 and up
	Timing   bool     // uses the timing policy (maxAttempts 5)
	Deadline int      // per-call deadline, milliseconds
}

// Scenarios, from the plan's "Scenarios and predictions" and "Timing track".
var Scenarios = map[string]Scenario{
	"S":     {Name: "S", First: Response{"UNAVAILABLE", "10"}, Later: Response{"OK", ""}, Deadline: 10000},
	"X5":    {Name: "X5", First: Response{"OK", "10"}, Later: Response{"OK", ""}, Deadline: 10000},
	"X1":    {Name: "X1", First: Response{"INVALID_ARGUMENT", "10"}, Later: Response{"OK", ""}, Deadline: 10000},
	"X2HI":  {Name: "X2HI", First: Response{"UNAVAILABLE", "2147483648"}, Later: Response{"UNAVAILABLE", "2147483648"}, Deadline: 2000},
	"X2MAX": {Name: "X2MAX", First: Response{"UNAVAILABLE", "2147483647"}, Later: Response{"UNAVAILABLE", "2147483647"}, Deadline: 2000},
	"X2NEG": {Name: "X2NEG", First: Response{"UNAVAILABLE", "-1"}, Later: Response{"UNAVAILABLE", "-1"}, Deadline: 2000},
	"X4P":   {Name: "X4P", First: Response{"UNAVAILABLE", "+5"}, Later: Response{"OK", ""}, Deadline: 10000},
	"X4Z":   {Name: "X4Z", First: Response{"UNAVAILABLE", "007"}, Later: Response{"OK", ""}, Deadline: 10000},
	"T":     {Name: "T", First: Response{"UNAVAILABLE", ""}, Later: Response{"UNAVAILABLE", ""}, Timing: true, Deadline: 10000},
}

// ResponseFor returns what the server sends on attempt k (1-based).
func (s Scenario) ResponseFor(k int) Response {
	if k <= 1 {
		return s.First
	}
	return s.Later
}

// ServiceConfig returns the client default service config: retry policy for
// cs4.Probe, no retryThrottling. maxAttempts 3, or 5 for the timing scenario.
func ServiceConfig(timing bool) string {
	maxAttempts := 3
	if timing {
		maxAttempts = 5
	}
	cfg := map[string]any{
		"methodConfig": []any{map[string]any{
			"name": []any{map[string]any{"service": ServiceName}},
			"retryPolicy": map[string]any{
				"maxAttempts":          maxAttempts,
				"initialBackoff":       "0.2s",
				"maxBackoff":           "0.2s",
				"backoffMultiplier":    1,
				"retryableStatusCodes": []string{"UNAVAILABLE"},
			},
		}},
	}
	b, err := json.Marshal(cfg)
	if err != nil {
		panic(err)
	}
	return string(b)
}

// BackoffNanos is the configured initialBackoff = maxBackoff (200 ms).
const BackoffNanos int64 = 200_000_000

// ServerRecord is one line of the server's attempt log.
type ServerRecord struct {
	TNanos       int64  `json:"t_ns"` // monotonic, since server start
	CallID       string `json:"call_id"`
	Scenario     string `json:"scenario"`
	Client       string `json:"client"`
	Attempt      int    `json:"attempt"`
	SentCode     string `json:"sent_code"`
	SentPushback string `json:"sent_pushback"`
	PrevAttempts string `json:"prev_attempts_hdr"` // grpc-previous-rpc-attempts, informational only
}

// ClientRecord is one line of a client's call log.
type ClientRecord struct {
	Client    string `json:"client"`
	Scenario  string `json:"scenario"`
	CallID    string `json:"call_id"`
	FinalCode string `json:"final_code"`
	ElapsedNs int64  `json:"elapsed_ns"`
	Message   string `json:"message"`
}

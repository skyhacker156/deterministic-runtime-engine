package oracle

import (
	"fmt"
	"sort"
)

// Frame is one HTTP/2 frame seen by the C1 frame proxy.
type Frame struct {
	Dir       string      `json:"dir"` // "s2c" (server to client) or "c2s"
	Type      string      `json:"type"`
	Stream    uint32      `json:"stream"`
	EndStream bool        `json:"end_stream"`
	EndHdrs   bool        `json:"end_headers"`
	Length    uint32      `json:"length"`
	Headers   [][2]string `json:"headers,omitempty"`
}

// C1Result is the outcome of gate C1 (plan, "Gates").
type C1Result struct {
	Pass    bool     `json:"pass"`
	Stream  uint32   `json:"stream"`
	Reasons []string `json:"reasons"`
	Other   []string `json:"other_frames_on_stream"`
}

// CheckC1 applies the C1 rule to the server-to-client frames of a single
// X5 attempt-1 call made with retries disabled: on the call's stream, exactly
// one HEADERS frame with END_STREAM and END_HEADERS, carrying :status 200,
// grpc-status 0 and grpc-retry-pushback-ms 10, and no DATA frame. Other frame
// types on the stream (for example WINDOW_UPDATE) are listed, not failed.
func CheckC1(frames []Frame) C1Result {
	var res C1Result
	streams := map[uint32][]Frame{}
	for _, f := range frames {
		if f.Dir == "s2c" && f.Stream != 0 {
			streams[f.Stream] = append(streams[f.Stream], f)
		}
	}
	if len(streams) != 1 {
		ids := make([]int, 0, len(streams))
		for id := range streams {
			ids = append(ids, int(id))
		}
		sort.Ints(ids)
		res.Reasons = append(res.Reasons, fmt.Sprintf("expected server frames on exactly 1 stream, got %d %v", len(streams), ids))
		return res
	}
	for id, fs := range streams {
		res.Stream = id
		var headers []Frame
		for _, f := range fs {
			switch f.Type {
			case "HEADERS":
				headers = append(headers, f)
			case "DATA":
				res.Reasons = append(res.Reasons, fmt.Sprintf("DATA frame on stream %d (length %d)", id, f.Length))
			case "CONTINUATION":
				res.Reasons = append(res.Reasons, "CONTINUATION frame: headers not in a single frame")
			default:
				res.Other = append(res.Other, f.Type)
			}
		}
		if len(headers) != 1 {
			res.Reasons = append(res.Reasons, fmt.Sprintf("expected exactly 1 HEADERS frame, got %d", len(headers)))
			break
		}
		h := headers[0]
		if !h.EndStream {
			res.Reasons = append(res.Reasons, "HEADERS frame lacks END_STREAM")
		}
		if !h.EndHdrs {
			res.Reasons = append(res.Reasons, "HEADERS frame lacks END_HEADERS")
		}
		want := [][2]string{{":status", "200"}, {"grpc-status", "0"}, {"grpc-retry-pushback-ms", "10"}}
		for _, w := range want {
			n := 0
			for _, kv := range h.Headers {
				if kv[0] == w[0] {
					n++
					if kv[1] != w[1] {
						res.Reasons = append(res.Reasons, fmt.Sprintf("%s = %q, want %q", w[0], kv[1], w[1]))
					}
				}
			}
			if n != 1 {
				res.Reasons = append(res.Reasons, fmt.Sprintf("%s present %d times, want 1", w[0], n))
			}
		}
	}
	res.Pass = len(res.Reasons) == 0
	return res
}

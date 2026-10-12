// Command client is the CS4 Go client. The same source is built against
// grpc-go v1.84.0 (go.mod: go184), v1.68.2 (go168.mod: go168), and the
// planted copies of v1.84.0 (gomx1.mod, gomx5.mod: goMX1, goMX5).
//
// It refuses to run if its -client label does not match the grpc module it
// was built with, as reported by the Go build info.
//
// For each of -n calls, in sequence on one connection, it logs one JSON line:
// call ID, final status code name, and elapsed time from stream creation to
// the call's end.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"runtime/debug"
	"strings"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"

	"cs4harness/internal/cs4"
)

// want describes the grpc module each label must be built with.
var want = map[string]struct {
	version string
	replace string // suffix of the replacement directory, "" for none
}{
	"go184": {"v1.84.0", ""},
	"go168": {"v1.68.2", ""},
	"goMX1": {"v1.84.0", "mx1"},
	"goMX5": {"v1.84.0", "mx5"},
}

func grpcModule() (version, replace string) {
	bi, ok := debug.ReadBuildInfo()
	if !ok {
		return "", ""
	}
	for _, d := range bi.Deps {
		if d.Path == "google.golang.org/grpc" {
			if d.Replace != nil {
				return d.Version, d.Replace.Path
			}
			return d.Version, ""
		}
	}
	return "", ""
}

func checkLabel(label string) error {
	w, ok := want[label]
	if !ok {
		return fmt.Errorf("unknown -client %q", label)
	}
	v, r := grpcModule()
	if v != w.version {
		return fmt.Errorf("-client %s needs grpc %s, built with %q", label, w.version, v)
	}
	r = strings.TrimRight(strings.ReplaceAll(r, `\`, "/"), "/")
	switch {
	case w.replace == "" && r != "":
		return fmt.Errorf("-client %s must use unmodified grpc, built with replacement %q", label, r)
	case w.replace != "" && !strings.HasSuffix(r, "/"+w.replace):
		return fmt.Errorf("-client %s needs grpc replaced by .../%s, got %q", label, w.replace, r)
	}
	return nil
}

func main() {
	addr := flag.String("addr", "127.0.0.1:50051", "server address")
	label := flag.String("client", "", "configuration label: go184, go168, goMX1, goMX5")
	scen := flag.String("scenario", "", "scenario name")
	n := flag.Int("n", 0, "number of calls")
	run := flag.String("run", "", "run tag, makes call IDs unique (for example r1)")
	out := flag.String("out", "", "client log (JSON lines); must not already exist")
	noRetry := flag.Bool("noretry", false, "disable retries (gate C1 only)")
	flag.Parse()

	fail := func(err error) {
		fmt.Fprintln(os.Stderr, "FATAL:", err)
		os.Exit(2)
	}
	if *label == "" || *scen == "" || *n <= 0 || *run == "" || *out == "" {
		fail(errors.New("usage: client -client L -scenario S -n N -run TAG -out FILE [-addr A] [-noretry]"))
	}
	if err := checkLabel(*label); err != nil {
		fail(err)
	}
	sc, ok := cs4.Scenarios[*scen]
	if !ok {
		fail(fmt.Errorf("unknown scenario %q", *scen))
	}
	f, err := os.OpenFile(*out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
	if err != nil {
		fail(err)
	}
	defer f.Close()
	enc := json.NewEncoder(f)

	v, r := grpcModule()
	fmt.Printf("CLIENT %s grpc %s replace=%q scenario=%s n=%d noretry=%v\n", *label, v, r, *scen, *n, *noRetry)

	opts := []grpc.DialOption{
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultServiceConfig(cs4.ServiceConfig(sc.Timing)),
		grpc.WithDefaultCallOptions(grpc.ForceCodec(cs4.RawCodec{})),
	}
	if *noRetry {
		opts = append(opts, grpc.WithDisableRetry())
	}
	conn, err := grpc.NewClient("passthrough:///"+*addr, opts...)
	if err != nil {
		fail(err)
	}
	defer conn.Close()

	desc := &grpc.StreamDesc{StreamName: cs4.MethodName, ServerStreams: true}
	tally := map[string]int{}
	for i := 0; i < *n; i++ {
		id := fmt.Sprintf("%s.%s.%s.%03d", *run, *label, *scen, i)
		body, _ := json.Marshal(cs4.Request{CallID: id, Scenario: *scen, Client: *label})
		code, msg, elapsed := call(conn, desc, body, time.Duration(sc.Deadline)*time.Millisecond)
		tally[code]++
		if err := enc.Encode(cs4.ClientRecord{Client: *label, Scenario: *scen, CallID: id,
			FinalCode: code, ElapsedNs: elapsed.Nanoseconds(), Message: msg}); err != nil {
			fail(err)
		}
	}
	fmt.Printf("CLIENT done: %d calls, final codes %v, log %s\n", *n, tally, *out)
}

// call makes one server-streaming call and returns the final status code
// name, the status message, and the elapsed time.
func call(conn *grpc.ClientConn, desc *grpc.StreamDesc, body []byte, deadline time.Duration) (string, string, time.Duration) {
	ctx, cancel := context.WithTimeout(context.Background(), deadline)
	defer cancel()
	t0 := time.Now()
	finish := func(err error, extra string) (string, string, time.Duration) {
		elapsed := time.Since(t0)
		if errors.Is(err, io.EOF) {
			return "OK", extra, elapsed
		}
		st := status.Convert(err)
		return cs4.CodeName(uint32(st.Code())), strings.TrimSpace(st.Message() + " " + extra), elapsed
	}
	st, err := conn.NewStream(ctx, desc, cs4.FullMethod)
	if err != nil {
		return finish(err, "")
	}
	if err := st.SendMsg(body); err != nil && !errors.Is(err, io.EOF) {
		return finish(err, "send")
	}
	if err := st.CloseSend(); err != nil {
		return finish(err, "closesend")
	}
	msgs := 0
	for {
		var b []byte
		if err := st.RecvMsg(&b); err != nil {
			extra := ""
			if msgs > 0 {
				extra = fmt.Sprintf("(received %d unexpected messages)", msgs)
			}
			return finish(err, extra)
		}
		msgs++
	}
}

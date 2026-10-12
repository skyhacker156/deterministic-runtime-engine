// Command server is the CS4 test server: grpc-go v1.84.0, native transport
// (Server.Serve), plaintext h2c on 127.0.0.1. One server-streaming method,
// cs4.Probe/Run. The handler never sends a message or header, and sets the
// pushback with SetTrailer only, so every response goes out trailers-only
// (http2_server.go writeStatus, 1089-1111 at v1.84.0).
//
// It logs one JSON line per attempt: arrival time (monotonic, since start),
// call ID, attempt number for that call, and what it sent back.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"

	"cs4harness/internal/cs4"
)

type server struct {
	start time.Time
	mu    sync.Mutex
	count map[string]int
	log   *os.File
	enc   *json.Encoder
}

func (s *server) handle(_ any, stream grpc.ServerStream) error {
	arrival := time.Since(s.start).Nanoseconds()

	var body []byte
	if err := stream.RecvMsg(&body); err != nil {
		return err
	}
	var req cs4.Request
	if err := json.Unmarshal(body, &req); err != nil || req.CallID == "" {
		return status.Errorf(codes.Internal, "cs4: bad request %q", body)
	}
	sc, ok := cs4.Scenarios[req.Scenario]
	if !ok {
		return status.Errorf(codes.Internal, "cs4: unknown scenario %q", req.Scenario)
	}

	prev := ""
	if md, ok := metadata.FromIncomingContext(stream.Context()); ok {
		if v := md.Get("grpc-previous-rpc-attempts"); len(v) > 0 {
			prev = v[0]
		}
	}

	s.mu.Lock()
	s.count[req.CallID]++
	k := s.count[req.CallID]
	resp := sc.ResponseFor(k)
	rec := cs4.ServerRecord{
		TNanos: arrival, CallID: req.CallID, Scenario: req.Scenario, Client: req.Client,
		Attempt: k, SentCode: resp.Code, SentPushback: resp.Pushback, PrevAttempts: prev,
	}
	err := s.enc.Encode(rec)
	s.mu.Unlock()
	if err != nil {
		fmt.Fprintln(os.Stderr, "FATAL: attempt log write failed:", err)
		os.Exit(2)
	}

	if resp.Pushback != "" {
		stream.SetTrailer(metadata.Pairs(cs4.PushbackKey, resp.Pushback))
	}
	if resp.Code == "OK" {
		return nil
	}
	n := cs4.CodeNumber(resp.Code)
	if n < 0 {
		return status.Errorf(codes.Internal, "cs4: bad code %q in scenario table", resp.Code)
	}
	return status.Errorf(codes.Code(n), "cs4 %s attempt %d", req.Scenario, k)
}

func main() {
	addr := flag.String("addr", "127.0.0.1:50051", "listen address")
	logPath := flag.String("log", "", "attempt log (JSON lines); must not already exist")
	flag.Parse()
	if *logPath == "" {
		fmt.Fprintln(os.Stderr, "usage: server -log FILE [-addr HOST:PORT]")
		os.Exit(2)
	}
	f, err := os.OpenFile(*logPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
	if err != nil {
		fmt.Fprintln(os.Stderr, "FATAL:", err)
		os.Exit(2)
	}
	s := &server{start: time.Now(), count: map[string]int{}, log: f, enc: json.NewEncoder(f)}

	gs := grpc.NewServer(grpc.ForceServerCodec(cs4.RawCodec{}))
	gs.RegisterService(&grpc.ServiceDesc{
		ServiceName: cs4.ServiceName,
		HandlerType: (*any)(nil),
		Streams: []grpc.StreamDesc{{
			StreamName:    cs4.MethodName,
			Handler:       s.handle,
			ServerStreams: true,
		}},
		Metadata: "cs4",
	}, s)

	lis, err := net.Listen("tcp", *addr)
	if err != nil {
		fmt.Fprintln(os.Stderr, "FATAL:", err)
		os.Exit(2)
	}
	fmt.Printf("SERVER grpc-go %s listening on %s, log %s\n", grpc.Version, lis.Addr(), *logPath)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)
	go func() {
		<-sig
		gs.GracefulStop()
	}()
	if err := gs.Serve(lis); err != nil {
		fmt.Fprintln(os.Stderr, "serve:", err)
	}
	s.mu.Lock()
	f.Sync()
	f.Close()
	s.mu.Unlock()
	fmt.Println("SERVER stopped")
}

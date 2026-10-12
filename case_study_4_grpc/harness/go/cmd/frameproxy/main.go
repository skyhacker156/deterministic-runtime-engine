// Command frameproxy is the gate C1 tool (CS4_PLAN.md, "Gates"). It sits
// between a client and the CS4 server, forwards bytes in both directions
// unchanged, and logs every HTTP/2 frame it sees as one JSON line: direction,
// type, stream, END_STREAM / END_HEADERS flags, length, and decoded header
// fields for HEADERS and CONTINUATION frames. It is used for the C1 check only,
// never for scored runs.
//
//	frameproxy -listen 127.0.0.1:50052 -target 127.0.0.1:50051 -out frames.jsonl
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"sync"

	"golang.org/x/net/http2"
	"golang.org/x/net/http2/hpack"

	"cs4harness/internal/oracle"
)

const clientPreface = "PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"

type logger struct {
	mu  sync.Mutex
	enc *json.Encoder
}

func (l *logger) write(f oracle.Frame) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if err := l.enc.Encode(f); err != nil {
		fmt.Fprintln(os.Stderr, "FATAL: frame log write:", err)
		os.Exit(2)
	}
}

// parse decodes frames from r until it ends; then it drains r so that the
// forwarding side never blocks on the tee.
func parse(dir string, r io.Reader, log *logger) {
	defer io.Copy(io.Discard, r)
	br := bufio.NewReader(r)
	if dir == "c2s" {
		p := make([]byte, len(clientPreface))
		if _, err := io.ReadFull(br, p); err != nil || string(p) != clientPreface {
			fmt.Fprintf(os.Stderr, "%s: no client preface (%v)\n", dir, err)
			return
		}
	}
	fr := http2.NewFramer(io.Discard, br)
	fr.SetMaxReadFrameSize(1 << 24)
	var fields [][2]string
	dec := hpack.NewDecoder(4096, func(hf hpack.HeaderField) {
		fields = append(fields, [2]string{hf.Name, hf.Value})
	})
	for {
		f, err := fr.ReadFrame()
		if err != nil {
			if err != io.EOF {
				fmt.Fprintf(os.Stderr, "%s: read frame: %v\n", dir, err)
			}
			return
		}
		h := f.Header()
		rec := oracle.Frame{Dir: dir, Type: h.Type.String(), Stream: h.StreamID, Length: h.Length}
		switch ff := f.(type) {
		case *http2.HeadersFrame:
			fields = nil
			if _, err := dec.Write(ff.HeaderBlockFragment()); err != nil {
				fmt.Fprintf(os.Stderr, "%s: hpack: %v\n", dir, err)
			}
			rec.EndStream, rec.EndHdrs, rec.Headers = ff.StreamEnded(), ff.HeadersEnded(), fields
		case *http2.ContinuationFrame:
			fields = nil
			if _, err := dec.Write(ff.HeaderBlockFragment()); err != nil {
				fmt.Fprintf(os.Stderr, "%s: hpack: %v\n", dir, err)
			}
			rec.EndHdrs, rec.Headers = ff.HeadersEnded(), fields
		case *http2.DataFrame:
			rec.EndStream = ff.StreamEnded()
		}
		log.write(rec)
	}
}

func handle(client net.Conn, target string, log *logger) {
	defer client.Close()
	server, err := net.Dial("tcp", target)
	if err != nil {
		fmt.Fprintln(os.Stderr, "dial target:", err)
		return
	}
	defer server.Close()
	var wg sync.WaitGroup
	pipe := func(dir string, from, to net.Conn) {
		defer wg.Done()
		pr, pw := io.Pipe()
		done := make(chan struct{})
		go func() { parse(dir, pr, log); close(done) }()
		io.Copy(to, io.TeeReader(from, pw))
		pw.Close()
		<-done
		if tc, ok := to.(*net.TCPConn); ok {
			tc.CloseWrite()
		}
	}
	wg.Add(2)
	go pipe("c2s", client, server)
	go pipe("s2c", server, client)
	wg.Wait()
}

func main() {
	listen := flag.String("listen", "127.0.0.1:50052", "listen address")
	target := flag.String("target", "127.0.0.1:50051", "CS4 server address")
	out := flag.String("out", "", "frame log (JSON lines); must not already exist")
	flag.Parse()
	if *out == "" {
		fmt.Fprintln(os.Stderr, "usage: frameproxy -out FILE [-listen A] [-target B]")
		os.Exit(2)
	}
	f, err := os.OpenFile(*out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
	if err != nil {
		fmt.Fprintln(os.Stderr, "FATAL:", err)
		os.Exit(2)
	}
	defer f.Close()
	log := &logger{enc: json.NewEncoder(f)}
	lis, err := net.Listen("tcp", *listen)
	if err != nil {
		fmt.Fprintln(os.Stderr, "FATAL:", err)
		os.Exit(2)
	}
	fmt.Printf("FRAMEPROXY %s -> %s, log %s\n", lis.Addr(), *target, *out)
	for {
		c, err := lis.Accept()
		if err != nil {
			fmt.Fprintln(os.Stderr, "accept:", err)
			return
		}
		go handle(c, *target, log)
	}
}

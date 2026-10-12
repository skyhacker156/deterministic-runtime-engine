package main

import (
	"bufio"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

const usage = `cs3 harness (raft %s, %s)

  selftest [-p1a-history FILE]          oracle and encoding self-test; run before every arm
  gen  -arm P1b|P2|P3 -from N -to M -out DIR
                                         pre-generate schedules (P1b and P2 identical)
  run  -arm A -schedules DIR -from N -to M -out DIR
                                         run an arm; verifies each schedule against DIR/schedule_hashes.txt
  p1a  -from N -to M -out DIR            directed #392 scenario; jitter 0 is canonical
  diverge -a DIR -b DIR -from N -to M    first tick at which two builds' message traces differ
`

func die(f string, a ...any) { fmt.Fprintf(os.Stderr, f+"\n", a...); os.Exit(1) }

func writeFile(p string, b []byte) {
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		die("%v", err)
	}
	if err := os.WriteFile(p, b, 0o644); err != nil {
		die("%v", err)
	}
}

func main() {
	if len(os.Args) < 2 {
		fmt.Printf(usage, raftVersion, runtime.Version())
		os.Exit(2)
	}
	cmd, args := os.Args[1], os.Args[2:]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	arm := fs.String("arm", "", "arm name")
	from := fs.Uint64("from", 1, "first seed")
	to := fs.Uint64("to", 1, "last seed")
	out := fs.String("out", "", "output directory")
	schedDir := fs.String("schedules", "", "schedule directory")
	p1aHist := fs.String("p1a-history", "", "recorded P1a history from the v3.6.0 build")
	dirA := fs.String("a", "", "results directory, build A")
	dirB := fs.String("b", "", "results directory, build B")
	fs.Parse(args)

	switch cmd {
	case "selftest":
		var ops []OpRecord
		if *p1aHist != "" {
			ops = readHistory(*p1aHist)
		}
		if err := SelfTest(ops); err != nil {
			die("SELFTEST FAILED: %v", err)
		}
		fmt.Printf("selftest passed (raft %s, %s, P1a case included: %v)\n", raftVersion, runtime.Version(), ops != nil)

	case "gen":
		if *arm == "" || *out == "" {
			die("gen needs -arm and -out")
		}
		var lines []string
		for seed := *from; seed <= *to; seed++ {
			sch := GenSchedule(seed, *arm == "P3")
			b, _ := json.Marshal(sch)
			writeFile(filepath.Join(*out, fmt.Sprintf("%d.json", seed)), b)
			lines = append(lines, fmt.Sprintf("%d %s", seed, sch.Hash()))
		}
		writeFile(filepath.Join(*out, "schedule_hashes.txt"), []byte(strings.Join(lines, "\n")+"\n"))
		fmt.Printf("wrote %d schedules to %s\n", len(lines), *out)

	case "run":
		runArm(*arm, *schedDir, *from, *to, *out)

	case "p1a":
		if *out == "" {
			die("p1a needs -out")
		}
		var rows []string
		for j := *from; j <= *to; j++ {
			r1 := RunP1a(j)
			r2 := RunP1a(j)
			h1, h2 := sha(HistoryBytes(r1.Ops)), sha(HistoryBytes(r2.Ops))
			b, _ := json.MarshalIndent(r1, "", " ")
			writeFile(filepath.Join(*out, fmt.Sprintf("p1a_%d.json", j)), b)
			writeFile(filepath.Join(*out, fmt.Sprintf("p1a_%d_history.jsonl", j)), HistoryBytes(r1.Ops))
			success := r1.Aborted == "" && r1.Verdict == "Illegal" && r1.Shape392 && len(r1.Conformance) == 0 && h1 == h2
			row := fmt.Sprintf("jitter=%d version=%s verdict=%s shape392=%v conformance=%d replay_match=%v aborted=%q success=%v",
				j, raftVersion, r1.Verdict, r1.Shape392, len(r1.Conformance), h1 == h2, r1.Aborted, success)
			fmt.Println(row)
			rows = append(rows, row)
		}
		writeFile(filepath.Join(*out, "p1a_summary.txt"), []byte(strings.Join(rows, "\n")+"\n"))

	case "diverge":
		for seed := *from; seed <= *to; seed++ {
			a := readTicks(filepath.Join(*dirA, "ticks", fmt.Sprintf("%d.bin", seed)))
			b := readTicks(filepath.Join(*dirB, "ticks", fmt.Sprintf("%d.bin", seed)))
			first := -1
			for i := 0; i < len(a) || i < len(b); i++ {
				if i >= len(a) || i >= len(b) || a[i] != b[i] {
					first = i
					break
				}
			}
			fmt.Printf("%d %d\n", seed, first)
		}

	default:
		fmt.Printf(usage, raftVersion, runtime.Version())
		os.Exit(2)
	}
}

func readHistory(p string) []OpRecord {
	b, err := os.ReadFile(p)
	if err != nil {
		die("%v", err)
	}
	var ops []OpRecord
	sc := bufio.NewScanner(bytes.NewReader(b))
	sc.Buffer(make([]byte, 1<<20), 1<<26)
	for sc.Scan() {
		var o OpRecord
		if err := json.Unmarshal(sc.Bytes(), &o); err != nil {
			die("%v", err)
		}
		ops = append(ops, o)
	}
	return ops
}

func readTicks(p string) []uint32 {
	b, err := os.ReadFile(p)
	if err != nil {
		die("%v", err)
	}
	out := make([]uint32, len(b)/4)
	for i := range out {
		out[i] = binary.LittleEndian.Uint32(b[i*4:])
	}
	return out
}

func loadHashes(dir string) map[uint64]string {
	b, err := os.ReadFile(filepath.Join(dir, "schedule_hashes.txt"))
	if err != nil {
		die("%v", err)
	}
	m := map[uint64]string{}
	for _, ln := range strings.Split(strings.TrimSpace(string(b)), "\n") {
		var s uint64
		var h string
		if _, err := fmt.Sscan(ln, &s, &h); err == nil {
			m[s] = h
		}
	}
	return m
}

func runArm(arm, schedDir string, from, to uint64, out string) {
	if arm == "" || schedDir == "" || out == "" {
		die("run needs -arm, -schedules and -out")
	}
	if err := checkCryptoRandOverride(); err != nil {
		die("%v", err)
	}
	hashes := loadHashes(schedDir)
	resf, err := os.OpenFile(filepath.Join(out, "results.jsonl"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		if err := os.MkdirAll(out, 0o755); err != nil {
			die("%v", err)
		}
		resf, err = os.OpenFile(filepath.Join(out, "results.jsonl"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
		if err != nil {
			die("%v", err)
		}
	}
	defer resf.Close()
	for seed := from; seed <= to; seed++ {
		b, err := os.ReadFile(filepath.Join(schedDir, fmt.Sprintf("%d.json", seed)))
		if err != nil {
			die("%v", err)
		}
		var sch Schedule
		if err := json.Unmarshal(b, &sch); err != nil {
			die("%v", err)
		}
		if want, ok := hashes[seed]; !ok || sch.Hash() != want {
			die("seed %d: schedule hash does not match schedule_hashes.txt; halting", seed)
		}
		r, hist, ticks, err := RunTrial(arm, &sch)
		if err != nil {
			die("seed %d: %v", seed, err)
		}
		// Replay every violation, every unknown, and every seed divisible by 50 (2 per cent).
		if r.Verdict != "Ok" || seed%50 == 0 {
			r2, hist2, _, err := RunTrial(arm, &sch)
			if err != nil {
				die("seed %d replay: %v", seed, err)
			}
			match := sha(hist2) == r.HistoryHash && r2.Verdict == r.Verdict
			r.Replayed, r.ReplayMatch = true, &match
			if !match {
				line, _ := json.Marshal(r)
				resf.Write(append(line, '\n'))
				die("seed %d: replay produced a different history; arm halted", seed)
			}
		}
		writeFile(filepath.Join(out, "histories", fmt.Sprintf("%d.jsonl", seed)), hist)
		writeFile(filepath.Join(out, "ticks", fmt.Sprintf("%d.bin", seed)), ticks)
		line, _ := json.Marshal(r)
		resf.Write(append(line, '\n'))
		fmt.Printf("%s seed %d %s reads %d/%d multi-sub %d flags c%d/l%d shape %d\n", arm, seed, r.Verdict,
			r.ReadsComplete, r.Reads, r.ReadsMultiSub, r.FlagClient, r.FlagLibrary, r.Shape392)
	}
}

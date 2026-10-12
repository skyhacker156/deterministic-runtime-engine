// Command checker applies the CS4 pre-registered rules (internal/oracle) to
// run logs. It never runs gRPC.
//
//	checker analyze -server S.jsonl -client A.jsonl[,B.jsonl...] -report R.json -replay P.json
//	checker c1 -frames F.jsonl
//
// analyze writes the full report and, separately, the replay view (decision
// tuples only). Two full reruns of the decision track reproduce the plan's
// replay rule only if their replay files are byte-identical.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sort"
	"strings"

	"cs4harness/internal/cs4"
	"cs4harness/internal/oracle"
)

func fail(err error) {
	fmt.Fprintln(os.Stderr, "FATAL:", err)
	os.Exit(2)
}

func readLines[T any](path string) []T {
	f, err := os.Open(path)
	if err != nil {
		fail(err)
	}
	defer f.Close()
	var out []T
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for line := 1; sc.Scan(); line++ {
		if strings.TrimSpace(sc.Text()) == "" {
			continue
		}
		var v T
		if err := json.Unmarshal(sc.Bytes(), &v); err != nil {
			fail(fmt.Errorf("%s line %d: %w", path, line, err))
		}
		out = append(out, v)
	}
	if err := sc.Err(); err != nil {
		fail(err)
	}
	return out
}

func writeJSON(path string, v any) {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		fail(err)
	}
	if err := os.WriteFile(path, append(b, '\n'), 0o644); err != nil {
		fail(err)
	}
}

func analyze(args []string) {
	fs := flag.NewFlagSet("analyze", flag.ExitOnError)
	srvPath := fs.String("server", "", "server attempt log")
	cliPaths := fs.String("client", "", "comma-separated client logs")
	repPath := fs.String("report", "", "full report output (JSON)")
	replayPath := fs.String("replay", "", "replay view output (JSON)")
	fs.Parse(args)
	if *srvPath == "" || *cliPaths == "" || *repPath == "" || *replayPath == "" {
		fail(fmt.Errorf("usage: checker analyze -server S -client A[,B] -report R -replay P"))
	}
	srv := readLines[cs4.ServerRecord](*srvPath)
	var cli []cs4.ClientRecord
	for _, p := range strings.Split(*cliPaths, ",") {
		cli = append(cli, readLines[cs4.ClientRecord](strings.TrimSpace(p))...)
	}
	rep := oracle.Analyze(srv, cli)
	writeJSON(*repPath, rep)
	writeJSON(*replayPath, rep.ReplayView())

	fmt.Printf("%-13s %-6s %5s  %-22s %-24s %s\n", "CONFIG", "SCEN", "CALLS", "PREDICTED", "OBSERVED", "VERDICT")
	for _, d := range rep.Decision {
		obs := make([]string, 0, len(d.Tuples))
		for t, n := range d.Tuples {
			obs = append(obs, fmt.Sprintf("%s x%d", t, n))
		}
		sort.Strings(obs)
		fmt.Printf("%-13s %-6s %5d  %-22s %-24s %s\n", d.Config, d.Scenario, d.Calls, d.Predicted, strings.Join(obs, "; "), d.Verdict)
	}
	for _, t := range rep.Timing {
		fmt.Printf("%-13s %-6s %5d  %-22s %-24s %s  (delays %d, below0.80 %.3f, atmost1.40 %.3f, r min %.3f med %.3f max %.3f, malformed %d)\n",
			t.Config, "T", t.Calls, t.Predicted, t.Class, t.Verdict, t.Delays, t.FracBelowLow, t.FracAtMostHigh, t.MinR, t.MedianR, t.MaxR, t.MalformedCalls)
	}
	fmt.Printf("orphan server attempts: %d, mislabeled server attempts: %d\n", rep.OrphanAttempts, rep.MislabeledCalls)
}

func c1(args []string) {
	fs := flag.NewFlagSet("c1", flag.ExitOnError)
	path := fs.String("frames", "", "frame log from frameproxy")
	fs.Parse(args)
	if *path == "" {
		fail(fmt.Errorf("usage: checker c1 -frames F"))
	}
	res := oracle.CheckC1(readLines[oracle.Frame](*path))
	b, _ := json.MarshalIndent(res, "", "  ")
	fmt.Println(string(b))
	if res.Pass {
		fmt.Println("C1 PASS")
		return
	}
	fmt.Println("C1 FAIL")
	os.Exit(1)
}

func main() {
	if len(os.Args) < 2 {
		fail(fmt.Errorf("usage: checker analyze|c1 ..."))
	}
	switch os.Args[1] {
	case "analyze":
		analyze(os.Args[2:])
	case "c1":
		c1(os.Args[2:])
	default:
		fail(fmt.Errorf("unknown subcommand %q", os.Args[1]))
	}
}

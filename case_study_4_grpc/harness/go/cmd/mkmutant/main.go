// Command mkmutant builds the planted-defect copies of grpc-go v1.84.0 named
// in CS4_PLAN.md, "Controls": goMX1 and goMX5. It copies the module tree
// verbatim and changes stream.go only, by exact single-occurrence
// replacement, checking the SHA-256 of stream.go before and after.
//
//	mkmutant -src <module dir of google.golang.org/grpc@v1.84.0> -dst mx/mx1 -variant mx1
//
// The source directory comes from: go mod download -json google.golang.org/grpc@v1.84.0
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// SHA-256 of stream.go: unmodified v1.84.0, and the two planted variants.
const (
	origHash = "68AA9293B8023D550C730D391482DC08B2572526B8629904F1DDE457BF042C4D"
	mx1Hash  = "39275DA00C9ADA4830464829EF09DBF3FBB94E37A0DB89186CBD46C5DFEC4095"
	mx5Hash  = "1E1E44818BF1C739BD063BCCF40B2547D64BDD155183918AB669FE6A16F74D44"
)

type edit struct{ old, new string }

// Plan, "Controls": goMX1 changes line 857; goMX5 changes line 857 and 964.
var (
	edit857 = edit{
		old: "if rp == nil || !rp.RetryableStatusCodes[code] {",
		new: "if rp == nil || (!rp.RetryableStatusCodes[code] && !hasPushback) {",
	}
	edit964 = edit{
		old: "if err == nil || (err == io.EOF && a.transportStream.Status().Code() == codes.OK) {",
		new: `if err == nil || (err == io.EOF && a.transportStream.Status().Code() == codes.OK && len(a.transportStream.Trailer()["grpc-retry-pushback-ms"]) == 0) {`,
	}
	variants = map[string]struct {
		edits []edit
		hash  string
	}{
		"mx1": {[]edit{edit857}, mx1Hash},
		"mx5": {[]edit{edit857, edit964}, mx5Hash},
	}
)

func sum(b []byte) string {
	h := sha256.Sum256(b)
	return strings.ToUpper(hex.EncodeToString(h[:]))
}

func fail(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "FATAL: "+format+"\n", a...)
	os.Exit(2)
}

func main() {
	src := flag.String("src", "", "module directory of google.golang.org/grpc@v1.84.0")
	dst := flag.String("dst", "", "output directory (must not exist)")
	variant := flag.String("variant", "", "mx1 or mx5")
	flag.Parse()
	v, ok := variants[*variant]
	if *src == "" || *dst == "" || !ok {
		fail("usage: mkmutant -src DIR -dst DIR -variant mx1|mx5")
	}
	if _, err := os.Stat(*dst); err == nil {
		fail("%s already exists; remove it first", *dst)
	}

	orig, err := os.ReadFile(filepath.Join(*src, "stream.go"))
	if err != nil {
		fail("%v", err)
	}
	if got := sum(orig); got != origHash {
		fail("source stream.go is %s, want v1.84.0 %s", got, origHash)
	}
	patched := orig
	for _, e := range v.edits {
		if n := bytes.Count(patched, []byte(e.old)); n != 1 {
			fail("edit target found %d times, want 1: %s", n, e.old)
		}
		patched = bytes.Replace(patched, []byte(e.old), []byte(e.new), 1)
	}
	if got := sum(patched); got != v.hash {
		fail("patched stream.go is %s, want %s", got, v.hash)
	}

	files := 0
	err = filepath.WalkDir(*src, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(*src, p)
		out := filepath.Join(*dst, rel)
		if d.IsDir() {
			return os.MkdirAll(out, 0o755)
		}
		if !d.Type().IsRegular() {
			return fmt.Errorf("unexpected non-regular file %s", rel)
		}
		files++
		if rel == "stream.go" {
			return os.WriteFile(out, patched, 0o644)
		}
		in, err := os.Open(p)
		if err != nil {
			return err
		}
		defer in.Close()
		o, err := os.OpenFile(out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
		if err != nil {
			return err
		}
		if _, err := io.Copy(o, in); err != nil {
			o.Close()
			return err
		}
		return o.Close()
	})
	if err != nil {
		os.RemoveAll(*dst)
		fail("copy: %v (partial output removed)", err)
	}
	fmt.Printf("MUTANT %s: %d files copied to %s\n  stream.go before %s\n  stream.go after  %s\n", *variant, files, *dst, origHash, v.hash)
}

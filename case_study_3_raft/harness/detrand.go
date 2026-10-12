package main

import (
	crand "crypto/rand"
	"encoding/binary"
	"fmt"
	"math/big"
)

// Both raft releases draw their randomized election timeout from
// crypto/rand.Reader (raft.go, lockedRand.Intn). That would make a seed
// unable to reproduce a run. The harness replaces crypto/rand.Reader with a
// seeded stream before each trial. This changes no library code; it changes
// the randomness source the library reads at call time.

type detReader struct{ s uint64 }

func (r *detReader) next() uint64 {
	// splitmix64
	r.s += 0x9e3779b97f4a7c15
	z := r.s
	z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9
	z = (z ^ (z >> 27)) * 0x94d049bb133111eb
	return z ^ (z >> 31)
}

func (r *detReader) Read(p []byte) (int, error) {
	var b [8]byte
	for i := 0; i < len(p); i += 8 {
		binary.LittleEndian.PutUint64(b[:], r.next())
		copy(p[i:], b[:])
	}
	return len(p), nil
}

func seedCryptoRand(seed uint64) {
	crand.Reader = &detReader{s: seed ^ 0x5eed5eed5eed5eed}
}

// checkCryptoRandOverride confirms that crypto/rand.Int honours a replaced
// Reader on this Go toolchain. If it does not, election timing is not
// reproducible and the harness refuses to run.
func checkCryptoRandOverride() error {
	draw := func() []int64 {
		seedCryptoRand(12345)
		out := make([]int64, 8)
		for i := range out {
			v, err := crand.Int(crand.Reader, big.NewInt(1_000_000))
			if err != nil {
				panic(err)
			}
			out[i] = v.Int64()
		}
		return out
	}
	a, b := draw(), draw()
	for i := range a {
		if a[i] != b[i] {
			return fmt.Errorf("crypto/rand.Int ignores a replaced Reader on this toolchain; runs are not reproducible")
		}
	}
	return nil
}

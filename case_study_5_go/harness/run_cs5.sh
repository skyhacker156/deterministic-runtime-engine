#!/bin/bash
# CS5 runs (CS5_PLAN.md, commit 762c841). Sandbox, Linux. Order: G1a, G1b (replay),
# K, G2, G3, G4, B1, B2. Each run: fresh `git archive` of tag go1.27.0, minimal
# environment as gorebuild (cleared list set empty, GOTOOLCHAIN=local), fresh
# GOCACHE per run (gorebuild uses the default cache; recorded as a deviation),
# ./make.bash -distpack, then sha256sum of the distpack archive.
set -u
SRC=/home/claude/tools/go127          # git repo containing tag go1.27.0
TAG=go1.27.0
BOOT_A=/usr/local/go                  # official go1.24.7
BOOT_B=/home/claude/tools/go127       # sandbox-built go1.27.0
WORK=${WORK:?set WORK}
OUT=${OUT:?set OUT}
EXP_WIN=f0c0a0d33ba94f4d2c5dbc887334ce678b21813504ddb3aafcb06e60a5a667c4
EXP_LIN=675c26c449cbb18fc24b74650de1eabbae6e16f64326fd85a283fb3b58280685
mkdir -p "$WORK" "$OUT"
RESULTS="$OUT/results.tsv"
[ -e "$RESULTS" ] || printf 'run\tgoos\tgoarch\tbootstrap\tvariation\tarchive\tsha256\texpected\tverdict\tstart_utc\tend_utc\tmake_exit\n' > "$RESULTS"

run() {  # run <name> <goos> <goarch> <bootstrap> <variation> <exportdir> [extra env...]
  local name=$1 goos=$2 goarch=$3 boot=$4 var=$5 dir=$6; shift 6
  if [ -e "$dir" ]; then echo "FATAL: $dir exists"; exit 2; fi
  mkdir -p "$dir"
  git -C "$SRC" archive "$TAG" | tar -x -C "$dir"
  if [ "$name" = K ]; then
    python3 -I - "$dir/src/fmt/print.go" <<'PY'
import sys
p=sys.argv[1]; s=open(p,'rb').read()
o=b'// Copyright 2009 The Go Authors.'; n=b'// Copyright 2008 The Go Authors.'
assert s.count(o)==1, s.count(o)
open(p,'wb').write(s.replace(o,n))
PY
  fi
  local ext=zip; [ "$goos" = windows ] || ext=tar.gz
  local exp=$EXP_LIN; [ "$goos" = windows ] && exp=$EXP_WIN
  local start; start=$(date -u +%FT%TZ)
  ( cd "$dir/src" && env -i \
      PATH="$dir/bin:/usr/bin:/bin" HOME="$WORK/home-$name" GOCACHE="$WORK/cache-$name" \
      GOROOT="$dir" GOROOT_BOOTSTRAP="$boot" GOTOOLCHAIN=local GOOS="$goos" GOARCH="$goarch" \
      CC= CC_FOR_TARGET= CGO_ENABLED= CXX= CXX_FOR_TARGET= GO386= GOAMD64= GOARM= GOBIN= \
      GOEXPERIMENT= GOMIPS64= GOMIPS= GOPATH= GOPPC64= GOROOT_FINAL= GO_EXTLINK_ENABLED= \
      GO_GCFLAGS= GO_LDFLAGS= GO_LDSO= PKG_CONFIG= PWD="$dir/src" \
      "$@" ./make.bash -distpack ) > "$OUT/make_$name.log" 2>&1
  local rc=$?
  local end; end=$(date -u +%FT%TZ)
  local arc="$dir/pkg/distpack/$TAG.$goos-$goarch.$ext" sum=MISSING verdict=NO_ARCHIVE
  if [ -f "$arc" ]; then
    sum=$(sha256sum "$arc" | cut -d' ' -f1)
    if [ "$sum" = "$exp" ]; then verdict=IDENTICAL; else verdict=DIFFERS; fi
    cp "$arc" "$OUT/${name}_$TAG.$goos-$goarch.$ext"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$goos" "$goarch" "$boot" "$var" \
    "$(basename "$arc")" "$sum" "$exp" "$verdict" "$start" "$end" "$rc" >> "$RESULTS"
  echo "$name $goos/$goarch rc=$rc $verdict $sum"
}

"$BOOT_A/bin/go" version > "$OUT/bootstrap_A.txt"
"$BOOT_B/bin/go" version > "$OUT/bootstrap_B.txt"
git -C "$SRC" rev-parse "$TAG^{commit}" > "$OUT/source_commit.txt"
git -C "$SRC" show "$TAG:VERSION" > "$OUT/source_VERSION.txt"

run G1a windows amd64 "$BOOT_A" none                 "$WORK/g1a/go"
run G1b windows amd64 "$BOOT_A" "replay of G1a"      "$WORK/g1b/go"
run K   windows amd64 "$BOOT_A" "one byte in src/fmt/print.go comment" "$WORK/k/go"
run G2  windows amd64 "$BOOT_B" "bootstrap B"        "$WORK/g2/go"
run G3  linux   amd64 "$BOOT_A" none                 "$WORK/g3/go"
run G4  windows amd64 "$BOOT_A" "longer path with a space" "$WORK/g4/a much longer path with a space/second level/go"
run B1  windows amd64 "$BOOT_A" "GOAMD64=v3"         "$WORK/b1/go" GOAMD64=v3
run B2  linux   amd64 "$BOOT_A" "CGO_ENABLED=1, gcc present" "$WORK/b2/go" CGO_ENABLED=1
echo "ALL DONE $(date -u +%FT%TZ)"

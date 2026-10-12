# Case Study 3 harness: operator build and pre-run check (Windows PowerShell).
# Run from the harness folder. Needs Go 1.26 or newer (raft v3.7.0 requires it).
# Produces h360.exe and h370.exe, runs both self-tests, and records versions.
# It runs no scored trial.
#
# Arguments that start with "-" and contain "." are quoted: unquoted,
# Windows PowerShell splits -modfile=raft360.mod at the dot.

$ErrorActionPreference = "Stop"
function Run([string]$exe, [string[]]$argv) {
  & $exe @argv
  if ($LASTEXITCODE -ne 0) { throw "failed (exit $LASTEXITCODE): $exe $($argv -join ' ')" }
}

$gov = (go env GOVERSION)
if ($gov -notmatch '^go1\.(2[6-9]|[3-9]\d)') { throw "Go 1.26+ required, found $gov" }

# Resolve dependencies through the normal module proxy and checksum database.
# This writes raft360.sum and raft370.sum, which are then hashed with everything else.
Run go @("mod", "tidy", "-modfile=raft360.mod")
Run go @("mod", "tidy", "-modfile=raft370.mod")

Run go @("build", "-trimpath", "-modfile=raft360.mod", "-tags", "raftv36", "-o", "h360.exe", ".")
Run go @("build", "-trimpath", "-modfile=raft370.mod", "-tags", "raftv37", "-o", "h370.exe", ".")

# Self-tests: oracle encoding cases, and that crypto/rand.Int honours the
# seeded Reader on this toolchain (if it does not, runs are not reproducible).
Run .\h360.exe @("selftest")
Run .\h370.exe @("selftest")

# Record exactly what was built.
$info = @(
  "go: $gov"
  "raft360: " + (go list "-modfile=raft360.mod" -m go.etcd.io/raft/v3)
  "raft370: " + (go list "-modfile=raft370.mod" -m go.etcd.io/raft/v3)
  "porcupine: " + (go list "-modfile=raft360.mod" -m github.com/anishathalye/porcupine)
)
$info | Set-Content -Encoding ascii BUILD_INFO.txt
$info
Write-Host "Build OK. Next: .\prerun.ps1"

# Case Study 3: generate schedules and write HASHES_BEFORE_RUN.txt.
# Run from the harness folder after build.ps1. Runs no trial.
# Afterwards commit everything, then run the arms (see README.md).

$ErrorActionPreference = "Stop"
function Run([string]$exe, [string[]]$argv) {
  & $exe @argv
  if ($LASTEXITCODE -ne 0) { throw "failed (exit $LASTEXITCODE): $exe $($argv -join ' ')" }
}
$root = Resolve-Path ..

# P1b and P2 share the same pre-generated schedules (seeds 1-2000).
# P3 has its own, leader-targeted (seeds 2001-3000).
Run .\h360.exe @("gen", "-arm", "P1b", "-from", "1", "-to", "2000", "-out", "..\schedules\P1b_P2")
Run .\h360.exe @("gen", "-arm", "P3", "-from", "2001", "-to", "3000", "-out", "..\schedules\P3")

# Cross-check: the v3.7.0 build must generate byte-identical schedules.
$check = Join-Path $env:TEMP "cs3_check_P1b"
Run .\h370.exe @("gen", "-arm", "P1b", "-from", "1", "-to", "2000", "-out", $check)
if ((Get-FileHash ..\schedules\P1b_P2\schedule_hashes.txt).Hash -ne (Get-FileHash (Join-Path $check "schedule_hashes.txt")).Hash) {
  throw "schedules differ between builds; halting"
}

$files = @()
$files += Get-ChildItem .. -File -Filter *.md
$files += Get-ChildItem . -File | Where-Object { $_.Extension -in ".go", ".mod", ".sum", ".ps1", ".txt", ".md" }
$files += Get-Item ..\schedules\P1b_P2\schedule_hashes.txt, ..\schedules\P3\schedule_hashes.txt
$lines = $files | Sort-Object FullName | ForEach-Object {
  $rel = $_.FullName.Substring($root.Path.Length + 1)
  "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $rel
}
$lines | Set-Content -Encoding ascii ..\HASHES_BEFORE_RUN.txt
Write-Host "Wrote HASHES_BEFORE_RUN.txt with $($lines.Count) entries."
Write-Host "Commit and push now, before running any arm."

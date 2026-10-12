# CS4 scored session. CS4_PLAN.md (ca4ccaa), CS4_AMENDMENT_1.md (ae942d8),
# CS4_AMENDMENT_2.md (fb14d33). Committed and hashed in HASHES_BEFORE_RUN.txt
# before it is run. Run from a fresh Windows PowerShell 5.1 window:
#   powershell -NoProfile -ExecutionPolicy Bypass -File case_study_4_grpc\harness\run_scored.ps1
#
# Order (PREFLIGHT_AUDIT.md, section 2):
#   Pass r1, server process A:
#     1. sanity S: go184, java, goMX1, goMX5
#     2. planted controls: goMX1 X1, goMX5 X5 (before any subject run of X1, X5)
#     3. subject decision track: X5, X1, X2HI, X2MAX, X2NEG, X4P, X4Z for go184, java
#     4. timing track T: go168, go184, java, javaNoJitter (50 calls each)
#   Pass r2, fresh server process B: steps 1-3 again (replay rule).
#   Checker on r1 and r2; replay files compared byte for byte.
# Fail-stop: any client or server failure stops the session; everything written
# so far is kept, ABORTED.txt records where, and the partial results are
# committed and pushed. Nothing is ever rerun or overwritten: the results
# folder and every log file must not exist beforehand.
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\gosur\phoenix-verify'
$cs4  = Join-Path $repo 'case_study_4_grpc'
$g    = Join-Path $cs4 'harness\go'
$bin  = Join-Path $g 'bin'
$lib  = Join-Path $cs4 'harness\java\build\install\cs4client\lib'
$flag = 'GRPC_EXPERIMENTAL_XDS_RLS_LB'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd_HHmmss')
$out  = Join-Path $cs4 "results\scored_$stamp"
$DecisionN = 20
$TimingN = 50

function Check($what) { if ($LASTEXITCODE) { throw "$what failed (exit $LASTEXITCODE)" } }
function Hash($p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
function Note($line) { $l = "{0}  {1}" -f (Get-Date).ToUniversalTime().ToString('o'), $line; Add-Content -LiteralPath (Join-Path $out 'progress.txt') -Value $l -Encoding ASCII; Write-Host $l }

function Start-Server($name) {
  $p = Start-Process -FilePath (Join-Path $bin 'server.exe') -ArgumentList @('-log', (Join-Path $out "$name.jsonl"), '-addr', '127.0.0.1:50051') `
        -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $out "$name.out") -RedirectStandardError (Join-Path $out "$name.err")
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    if ($p.HasExited) { throw "$name exited early (exit $($p.ExitCode))" }
    $o = Get-Content -LiteralPath (Join-Path $out "$name.out") -ErrorAction SilentlyContinue
    if ($o -match 'listening') { Write-Host "started $name (pid $($p.Id))"; return $p }
  }
  Stop-Process -Id $p.Id -Force
  throw "$name did not report ready"
}
function Stop-Server($p, $name) {
  if ($p -isnot [System.Diagnostics.Process]) { throw "Stop-Server($name): not a process" }
  if (-not $p.HasExited) { Start-Sleep -Milliseconds 500; Stop-Process -Id $p.Id -Force; $p.WaitForExit() }
  Write-Host "stopped $name"
}

# One client invocation. Log file name: <run>_<label>_<scenario>.jsonl
# Client console output goes to Out-Host so that the function returns only the
# log file name (a returned value and printed lines would otherwise be mixed).
function Run-Client($label, $scen, $n, $run) {
  $log = "${run}_${label}_${scen}.jsonl"
  if (Test-Path (Join-Path $out $log)) { throw "$log already exists" }
  Note "BEGIN $run $label $scen n=$n"
  switch ($label) {
    'go184'  { & (Join-Path $bin 'client184.exe') -client go184 -scenario $scen -n $n -run $run -out $log | Out-Host }
    'go168'  { & (Join-Path $bin 'client168.exe') -client go168 -scenario $scen -n $n -run $run -out $log | Out-Host }
    'goMX1'  { & (Join-Path $bin 'clientmx1.exe') -client goMX1 -scenario $scen -n $n -run $run -out $log | Out-Host }
    'goMX5'  { & (Join-Path $bin 'clientmx5.exe') -client goMX5 -scenario $scen -n $n -run $run -out $log | Out-Host }
    'java'   { & java -cp "$lib\*" cs4.Client -client java -scenario $scen -n $n -run $run -out $log | Out-Host }
    'javaNoJitter' {
      $env:GRPC_EXPERIMENTAL_XDS_RLS_LB = 'false'
      try { & java -cp "$lib\*" cs4.Client -client javaNoJitter -scenario $scen -n $n -run $run -out $log | Out-Host }
      finally { Remove-Item Env:\GRPC_EXPERIMENTAL_XDS_RLS_LB }
    }
    default  { throw "unknown label $label" }
  }
  $code = $LASTEXITCODE
  Note "END   $run $label $scen exit=$code"
  if ($code) { throw "client $label $scen ($run) failed, exit $code" }
  $log
}

function Decision-Pass($run) {
  $logs = @()
  foreach ($l in 'go184', 'java', 'goMX1', 'goMX5') { $logs += Run-Client $l 'S' $DecisionN $run }
  $logs += Run-Client 'goMX1' 'X1' $DecisionN $run
  $logs += Run-Client 'goMX5' 'X5' $DecisionN $run
  foreach ($s in 'X5', 'X1', 'X2HI', 'X2MAX', 'X2NEG', 'X4P', 'X4Z') {
    foreach ($l in 'go184', 'java') { $logs += Run-Client $l $s $DecisionN $run }
  }
  $logs
}

function Write-Sums {
  $sums = Get-ChildItem -File $out | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object Name |
          ForEach-Object { "{0}  {1}" -f (Hash $_.FullName), $_.Name }
  $sums | Set-Content -Encoding ASCII -LiteralPath (Join-Path $out 'SHA256SUMS.txt')
}
function Commit-Push($msg) {
  Set-Location $repo
  git add ($out.Substring($repo.Length + 1).Replace('\', '/')); Check 'git add'
  git commit -m $msg -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01J4GZHHDoznDFoUCwuTtFNv"; Check 'git commit'
  git push origin cs4-grpc; Check 'git push'
  git log --oneline -1
  git ls-remote origin cs4-grpc main
}

# ---- Preflight (nothing scored before all of these pass) ----
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD).Trim() -ne 'cs4-grpc') { throw 'not on cs4-grpc' }
git fetch -q origin cs4-grpc; Check 'git fetch'
$head = (git rev-parse HEAD).Trim()
if ($head -ne (git rev-parse origin/cs4-grpc).Trim()) { throw 'HEAD is not the pushed origin/cs4-grpc' }
if (git status --porcelain -- case_study_4_grpc) { throw 'case_study_4_grpc has uncommitted or untracked changes' }
if ($null -ne [Environment]::GetEnvironmentVariable($flag)) { throw "$flag is set; open a fresh shell" }
$bad = 0; $count = 0
foreach ($line in Get-Content -LiteralPath (Join-Path $cs4 'HASHES_BEFORE_RUN.txt')) {
  if ($line -match '^\s*(#|$)') { continue }
  if ($line -notmatch '^([0-9A-F]{64})  (.+)$') { throw "bad line in HASHES_BEFORE_RUN.txt: $line" }
  $count++
  if ((Hash (Join-Path $repo $Matches[2])) -ne $Matches[1]) { $bad++; Write-Host "MISMATCH $($Matches[2])" }
}
if ($bad -or $count -eq 0) { throw "HASHES_BEFORE_RUN.txt: $bad of $count entries do not match; nothing run" }
if (Get-Process -Name server, frameproxy -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$bin\*" }) { throw 'a harness server or proxy is already running' }
if (Test-Path $out) { throw "$out already exists" }
New-Item -ItemType Directory $out | Out-Null
@("head $head", "started_utc $stamp", "hashes_verified $count", "go $(go version)") | Set-Content -Encoding ASCII (Join-Path $out 'session.txt')
Note "PREFLIGHT OK: HEAD $head, $count hashes verified"

# ---- Session ----
$srv = $null
try {
  Set-Location $out
  $srv = Start-Server 'server_r1'
  $r1 = @(Decision-Pass 'r1')
  foreach ($l in 'go168', 'go184', 'java', 'javaNoJitter') { $r1 += Run-Client $l 'T' $TimingN 'r1' }
  Stop-Server $srv 'server_r1'; $srv = $null

  $srv = Start-Server 'server_r2'
  $r2 = @(Decision-Pass 'r2')
  Stop-Server $srv 'server_r2'; $srv = $null

  Note 'CHECKER r1'
  $o = & (Join-Path $bin 'checker.exe') analyze -server server_r1.jsonl -client ($r1 -join ',') -report report_r1.json -replay replay_r1.json
  Check 'checker r1'; $o | Set-Content -Encoding ASCII checker_r1.txt; $o
  Note 'CHECKER r2'
  $o = & (Join-Path $bin 'checker.exe') analyze -server server_r2.jsonl -client ($r2 -join ',') -report report_r2.json -replay replay_r2.json
  Check 'checker r2'; $o | Set-Content -Encoding ASCII checker_r2.txt; $o
  $h1 = Hash (Join-Path $out 'replay_r1.json'); $h2 = Hash (Join-Path $out 'replay_r2.json')
  $rep = if ($h1 -eq $h2) { 'IDENTICAL' } else { 'DIFFERENT' }
  @("replay_r1.json $h1", "replay_r2.json $h2", "replay rule: $rep") | Set-Content -Encoding ASCII REPLAY_COMPARE.txt
  Note "REPLAY $rep"
  Write-Sums
  Commit-Push "Case Study 4: scored session $stamp, raw logs and checker output (replay $rep)"
  "DONE scored session $stamp"
}
catch {
  $err = $_.Exception.Message
  Write-Host "SESSION STOPPED: $err"
  if ($srv) { try { Stop-Server $srv 'server (abort)' } catch { Write-Host "stop failed: $($_.Exception.Message)" } }
  if (Test-Path $out) {
    @("aborted_utc $((Get-Date).ToUniversalTime().ToString('o'))", "error $err") | Set-Content -Encoding ASCII (Join-Path $out 'ABORTED.txt')
    Write-Sums
    Commit-Push "Case Study 4: scored session $stamp ABORTED, partial raw logs kept"
  }
  throw
}

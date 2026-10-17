# CS7 (C1) driver. Orchestrates one or more trials of the Curator lock ->
# external-resource write-authority experiment. Pre-registration: CS7_C1_PREREGISTRATION.md
# (cs7-c1), frozen 00a9c62. PRIMARY fault model: genuine process pause via PsSuspend.
#
# Per trial:
#   RESET resource -> start A (acquires lock) -> PsSuspend A's JVM (session expires)
#   -> start B (acquires free lock, writes its token FIRST) -> resume A -> create A_GO
#   -> A samples documented lockLost flag, then writes (or skips) -> classify.
#
# Prereqs: ZK ensemble up (nodes 1/2/3, no proxy); resource.py + C1Client.class present;
#   PsSuspend at $PsSuspend; Curator+ZK jars on $cp.
#
# Usage:  .\cs7_c1_run.ps1 -N 1 -Mode U          # pilot, unfenced (Arm U)
#         .\cs7_c1_run.ps1 -N 20 -Mode U
#         .\cs7_c1_run.ps1 -N 20 -Mode F          # fenced control (Arm F)
param(
  [int]$N = 1,
  [ValidateSet("U","F")][string]$Mode = "U",
  [int]$Session = 5000,
  [int]$SuspendSec = 9,
  [string]$ZK = "127.0.0.1:2181",
  [string]$LockPath = "/cs7/lock",
  [int]$ResourcePort = 14000
)

$H = "C:\Users\gosur\phoenix-verify\case_study_7_curator\harness"
$cp = "C:\Users\gosur\phoenix-verify\case_study_7_curator\harness;C:\zk\apache-zookeeper-3.9.6-bin\lib\*;C:\cs7lib\*"
$PsSuspend = "C:\cs7lib\PsSuspend.exe"
$resMode = if ($Mode -eq "F") { "fenced" } else { "unfenced" }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$results = Join-Path $H "CS7C1_results_$stamp.jsonl"
$tmp = $env:TEMP

function Send-Resource([string]$line) {
  try {
    $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $ResourcePort)
    $s = $c.GetStream(); $w = New-Object IO.StreamWriter($s); $w.AutoFlush = $true
    $r = New-Object IO.StreamReader($s)
    $w.WriteLine($line)
    if ($line -eq "LOG") {
      $out = @(); while (($ln = $r.ReadLine()) -ne $null) { if ($ln -eq "END") { break }; $out += $ln }
      $c.Close(); return $out
    } else { $resp = $r.ReadLine(); $c.Close(); return $resp }
  } catch { return $null }
}

function Wait-Marker([string]$file, [string]$pattern, [int]$timeoutSec) {
  $end = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $end) {
    if (Test-Path $file) {
      $m = Select-String -Path $file -Pattern $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($m) { return $m.Line }
    }
    Start-Sleep -Milliseconds 100
  }
  return $null
}

# --- Start the resource (one per run; RESET between trials) ---
Write-Host "Starting resource (mode=$resMode) on $ResourcePort ..."
Start-Process powershell -ArgumentList '-NoExit','-Command',
  "python -I `"$H\resource.py`" --mode $resMode --listen $ResourcePort" | Out-Null
Start-Sleep -Seconds 2
if (-not (Send-Resource "GET")) { Write-Error "resource not reachable on $ResourcePort"; return }

Write-Host "Results -> $results"
Write-Host "Mode=$Mode ($resMode)  N=$N  Session=$Session ms  SuspendSec=$SuspendSec`n"
$summary = @()

for ($i = 1; $i -le $N; $i++) {
  $go   = Join-Path $tmp "A_GO_$i";   Remove-Item $go   -ErrorAction SilentlyContinue
  $hold = Join-Path $tmp "B_HOLD_$i"; Remove-Item $hold -ErrorAction SilentlyContinue
  $aout = Join-Path $tmp "A_out_$i.txt"; Remove-Item $aout -ErrorAction SilentlyContinue
  $bout = Join-Path $tmp "B_out_$i.txt"; Remove-Item $bout -ErrorAction SilentlyContinue
  Send-Resource "RESET" | Out-Null

  # 1) Start A; wait until it has ACQUIRED the lock
  $procA = Start-Process java -PassThru -WindowStyle Hidden -RedirectStandardOutput $aout -ArgumentList @(
    "-cp", $cp, "C1Client", "--role","A","--id","A","--zk",$ZK,"--lockpath",$LockPath,
    "--resource","127.0.0.1:$ResourcePort","--session","$Session","--value","vA$i","--gofile",$go)
  $aAcq = Wait-Marker $aout "A_ACQUIRED" 30
  if (-not $aAcq) { Write-Warning "[$i] A never acquired"; try{Stop-Process -Id $procA.Id -Force -ErrorAction SilentlyContinue}catch{}; $summary += [pscustomobject]@{trial=$i;outcome="INVALID_TRIAL_no_A_acquire"}; continue }

  # 2) Suspend A's whole JVM -> its ZK session will expire (heartbeats frozen)
  & $PsSuspend -nobanner $procA.Id | Out-Null
  Start-Sleep -Seconds $SuspendSec     # > session timeout: ensemble expires A's session

  # 3) Start B; it should now acquire the free lock and write its (higher) token FIRST
  $procB = Start-Process java -PassThru -WindowStyle Hidden -RedirectStandardOutput $bout -ArgumentList @(
    "-cp", $cp, "C1Client", "--role","B","--id","B","--zk",$ZK,"--lockpath",$LockPath,
    "--resource","127.0.0.1:$ResourcePort","--session","$Session","--value","vB$i","--holdfile",$hold)
  $bWrote = Wait-Marker $bout "B_WROTE" 30
  if (-not $bWrote) {
    Write-Warning "[$i] B never acquired/wrote (A session may not have expired)"
    & $PsSuspend -r -nobanner $procA.Id | Out-Null
    try{Stop-Process -Id $procA.Id -Force -ErrorAction SilentlyContinue}catch{}; try{Stop-Process -Id $procB.Id -Force -ErrorAction SilentlyContinue}catch{}
    $summary += [pscustomobject]@{trial=$i;outcome="INVALID_TRIAL_no_B_acquire"}; continue
  }

  # 4) Resume A, then release it to write (A_GO) -- A races its own listener
  & $PsSuspend -r -nobanner $procA.Id | Out-Null
  New-Item -ItemType File -Path $go | Out-Null
  $aDone = Wait-Marker $aout "A_DONE" 30

  # 5) Release B, collect resource state
  New-Item -ItemType File -Path $hold | Out-Null
  Start-Sleep -Milliseconds 500
  $resGet = Send-Resource "GET"
  $resLog = Send-Resource "LOG"

  # --- parse witnesses ---
  $aPre  = (Select-String -Path $aout -Pattern "A_PREWRITE" | Select-Object -First 1).Line
  $aWrote= (Select-String -Path $aout -Pattern "A_WROTE"    | Select-Object -First 1).Line
  $aSkip = (Select-String -Path $aout -Pattern "A_SKIPPED_lockLost" | Select-Object -First 1).Line
  $tokA = if ($aAcq -match "token=(\d+)") { [long]$Matches[1] } else { -1 }
  $tokB = if ($bWrote -match "token=(\d+)") { [long]$Matches[1] } else { -1 }
  $lockLostPre = if ($aPre -match "lockLost=(\w+)") { $Matches[1] -eq "True" -or $Matches[1] -eq "true" } else { $null }
  # resource acceptance of A's write, from the LOG (JSON lines)
  $aAccepted = $null
  foreach ($jl in $resLog) { try { $o = $jl | ConvertFrom-Json } catch { continue }
    if ($o.clientId -eq "A") { $aAccepted = [bool]$o.accepted } }

  # --- predeclared classification (pre-reg s5) ---
  $outcome =
    if ($aSkip) { "LISTENER_BLOCKED" }
    elseif ($aWrote -and $aAccepted -eq $true -and $tokA -ge 0 -and $tokB -gt $tokA) { "STALE_WRITE_ACCEPTED" }
    elseif ($aWrote -and $aAccepted -eq $false) { "FENCE_REJECTED" }
    elseif (-not $aDone) { "INVALID_TRIAL_A_no_done" }
    else { "INVALID_TRIAL_other" }

  $rec = [pscustomobject]@{
    trial=$i; mode=$Mode; resMode=$resMode; session=$Session; suspendSec=$SuspendSec; outcome=$outcome
    tokenA=$tokA; tokenB=$tokB; lockLostAtPrewrite=$lockLostPre; aResourceAccepted=$aAccepted
    resourceFinal=$resGet; aPrewrite=$aPre; aWrote=$aWrote; aSkipped=[bool]$aSkip
    aAcquire=$aAcq; bWrote=$bWrote
  }
  $rec | ConvertTo-Json -Compress | Add-Content $results
  "{0,-3} {1,-26} tokA={2} tokB={3} lockLost@pre={4} Aaccepted={5} final=[{6}]" -f `
    $i,$outcome,$tokA,$tokB,$lockLostPre,$aAccepted,$resGet | Write-Host
  $summary += $rec

  try{Stop-Process -Id $procA.Id -Force -ErrorAction SilentlyContinue}catch{}; try{Stop-Process -Id $procB.Id -Force -ErrorAction SilentlyContinue}catch{}
  Remove-Item $go,$hold -ErrorAction SilentlyContinue
}

Write-Host "`n==== tally ($Mode/$resMode) ===="
$summary | Group-Object outcome | Sort-Object Count -Descending | ForEach-Object { "{0,4}  {1}" -f $_.Count, $_.Name | Write-Host }
Write-Host "`nfull per-trial JSON in $results"
Write-Host "STOP: inspect; do not interpret beyond the pre-registered classes."


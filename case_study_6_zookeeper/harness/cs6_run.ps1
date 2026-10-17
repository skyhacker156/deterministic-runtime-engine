# CS6 trial driver. Loops CS6Trial.java, one JVM per trial, gating each trial on
# cluster convergence. Run a dry run first (-N 1), inspect, then scale (-N 20).
#
# Prereqs (must be up before running):
#   - 3-node ensemble (nodes 1/2/3), leader = node 3.
#   - Proxy A on node 2's learner channel: listen 12883 -> 127.0.0.1:2883, control 13001.
#   - zoo2.cfg server.3 pointing at 127.0.0.1:12883 (persisted from last session).
# This script starts Proxy B itself (client -> node 1: listen 12181 -> 2181, control 13002).
#
# Usage:  .\cs6_run.ps1 -N 1            # dry run, 1 trial per mode
#         .\cs6_run.ps1 -N 20           # scored run
param([int]$N = 1, [string]$Modes = "T0,T1")

$ZK = "C:\zk\apache-zookeeper-3.9.6-bin"
$H  = "C:\Users\gosur\phoenix-verify\case_study_6_zookeeper\harness"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$results = Join-Path $H "CS6_results_$stamp.jsonl"

function Test-Port([int]$p) {
  try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $p); $c.Close(); return $true }
  catch { return $false }
}
function Get-Zx([int]$p) { try { Invoke-RestMethod "http://127.0.0.1:$p/commands/zabstate" -TimeoutSec 3 } catch { $null } }
function Wait-Converged([int]$timeoutSec = 30) {
  $end = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $end) {
    $z1 = Get-Zx 8081; $z2 = Get-Zx 8082; $z3 = Get-Zx 8083
    # Converged for our purposes = both followers serving and agreeing with each other.
    # The leader's last_zxid may sit ahead on an epoch marker (counter 0) right after an
    # election with no writes yet; that is not a divergence, so we don't require it to match.
    if ($z1 -and $z2 -and $z3 -and $z3.is_leader `
        -and $z1.zabstate -eq "broadcast" -and $z2.zabstate -eq "broadcast" `
        -and $z1.last_zxid -eq $z2.last_zxid) { return $true }
    Start-Sleep -Milliseconds 300
  }
  return $false
}

# Proxy B
if (-not (Test-Port 13002)) {
  Write-Host "Starting Proxy B (12181 -> 2181, control 13002)..."
  Start-Process powershell -ArgumentList "-NoExit","-Command",
    "python -I `"$H\tcp_proxy.py`" --name B --listen 12181 --target 127.0.0.1:2181 --control 13002"
  Start-Sleep -Seconds 2
}
if (-not (Test-Port 13001)) { Write-Error "Proxy A control (13001) not reachable - start Proxy A and the ensemble first."; return }

# Compile once
Push-Location $H
Write-Host "Compiling CS6Trial.java..."
& javac -cp "$ZK\lib\*" CS6Trial.java
if ($LASTEXITCODE -ne 0) { Write-Error "compile failed"; Pop-Location; return }

Write-Host "Results -> $results`n"
$summary = @()
foreach ($m in $Modes.Split(",")) {
  for ($i = 1; $i -le $N; $i++) {
    if (-not (Wait-Converged)) { Write-Warning "[$m #$i] cluster not converged; skipping"; continue }
    $raw = & java -cp ".;$ZK\lib\*" CS6Trial --mode $m --trial $i --path /x `
             --client 127.0.0.1:12181 --node2 127.0.0.1:2182 --leader 127.0.0.1:2183 `
             --ctlA 13001 --ctlB 13002 2>$null
    $line = ($raw | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
    if (-not $line) { Write-Warning "[$m #$i] no JSON emitted"; continue }
    Add-Content $results $line
    try { $o = $line | ConvertFrom-Json } catch { Write-Warning "[$m #$i] bad JSON"; continue }
    "{0,-3} #{1,-2} {2,-28} A={3} Z={4} notify={5} afterRead={6} remote={7} win={8}ms" -f `
      $o.mode, $o.trial, $o.outcome, $o.A, $o.Z, $o.lastZxidAtNotify, $o.lastAfterRead, $o.remoteRead, $o.elapsedMs | Write-Host
    $summary += $o
  }
}
Pop-Location

Write-Host "`n==== tally ===="
$summary | Group-Object outcome | Sort-Object Count -Descending | ForEach-Object { "{0,4}  {1}" -f $_.Count, $_.Name | Write-Host }
Write-Host "`nfull per-trial JSON in $results"

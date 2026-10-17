# CS6 mechanism probe. Runs one T1 trial while polling node 2's zabstate live, so
# we can see node 2's state across the ~9s the failover session is blocked.
# This disambiguates: node 2 still 'broadcast' (following) but unable to revalidate
# the global session (leader unreachable) vs. node 2 having left the quorum.
$ZK = "C:\zk\apache-zookeeper-3.9.6-bin"
$H  = "C:\Users\gosur\phoenix-verify\case_study_6_zookeeper\harness"

$trial = Start-Job -ArgumentList $ZK, $H -ScriptBlock {
  param($ZK, $H)
  Set-Location $H
  & java -cp ".;$ZK\lib\*" CS6Trial --mode T1 --trial 99 --path /x `
      --client 127.0.0.1:12181 --node2 127.0.0.1:2182 --leader 127.0.0.1:2183 `
      --ctlA 13001 --ctlB 13002 2>$null |
    Where-Object { $_ -match '^\{' } | Select-Object -Last 1
}

"=== node 2 zabstate, live, while the T1 trial runs ==="
while ($trial.State -eq 'Running') {
  $t = Get-Date -Format "HH:mm:ss.fff"
  try {
    $z = Invoke-RestMethod "http://127.0.0.1:8082/commands/zabstate" -TimeoutSec 1
    "{0}  zab={1,-12} is_leader={2,-5} zxid={3}" -f $t, $z.zabstate, $z.is_leader, $z.last_zxid | Write-Host
  } catch {
    "{0}  (admin unreachable)" -f $t | Write-Host
  }
  Start-Sleep -Milliseconds 400
}

"`n=== trial result ==="
Receive-Job $trial
Remove-Job $trial

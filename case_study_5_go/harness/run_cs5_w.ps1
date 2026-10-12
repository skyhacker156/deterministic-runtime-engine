# CS5 W1 and W2 (CS5_PLAN.md, 762c841), operator machine.
# W1: download go1.27.0.windows-amd64.zip from go.dev and SHA-256 it.
# W2: compare every file in that zip with the installed toolchain (GOROOT of the go on PATH).
# Writes to C:\Users\gosur\cs5_w (must not exist). Builds nothing; changes nothing installed.
$ErrorActionPreference = 'Stop'
$outDir = 'C:\Users\gosur\cs5_w'
$want = 'F0C0A0D33BA94F4D2C5DBC887334CE678B21813504DDB3AAFCB06E60A5A667C4'
if (Test-Path $outDir) { throw "$outDir already exists" }
New-Item -ItemType Directory $outDir | Out-Null
$zip = Join-Path $outDir 'go1.27.0.windows-amd64.zip'
$t0 = (Get-Date).ToUniversalTime().ToString('o')
Invoke-WebRequest -UseBasicParsing 'https://go.dev/dl/go1.27.0.windows-amd64.zip' -OutFile $zip
$h = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
$w1 = if ($h -eq $want) { 'MATCH' } else { 'DIFFERS' }
"W1 downloaded_utc $t0 size $((Get-Item $zip).Length) sha256 $h expected $want -> $w1"

# W2
$goroot = (& go env GOROOT).Trim()
$ver = (& go version).Trim()
"installed: $ver at $goroot"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [IO.Compression.ZipFile]::OpenRead($zip)
$sha = [Security.Cryptography.SHA256]::Create()
$rows = New-Object System.Collections.Generic.List[string]
$rows.Add("status`tpath`tzip_sha256`tinstalled_sha256")
$equal = 0; $diff = 0; $missing = 0
$zipPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
try {
  foreach ($e in $z.Entries) {
    if ($e.FullName.EndsWith('/')) { continue }
    if (-not $e.FullName.StartsWith('go/')) { throw "unexpected zip entry $($e.FullName)" }
    $rel = $e.FullName.Substring(3)
    [void]$zipPaths.Add($rel.Replace('/', '\'))
    $s = $e.Open(); try { $zh = [BitConverter]::ToString($sha.ComputeHash($s)).Replace('-', '') } finally { $s.Dispose() }
    $inst = Join-Path $goroot ($rel.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $inst)) { $missing++; $rows.Add("MISSING`t$rel`t$zh`t"); continue }
    $ih = (Get-FileHash -LiteralPath $inst -Algorithm SHA256).Hash
    if ($ih -eq $zh) { $equal++ } else { $diff++; $rows.Add("DIFFERS`t$rel`t$zh`t$ih") }
  }
} finally { $z.Dispose() }
$extra = 0
Get-ChildItem -LiteralPath $goroot -Recurse -File | ForEach-Object {
  $rel = $_.FullName.Substring($goroot.TrimEnd('\').Length + 1)
  if (-not $zipPaths.Contains($rel)) { $extra++; $rows.Add("EXTRA_INSTALLED`t$($rel.Replace('\','/'))`t`t$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)") }
}
$rows | Set-Content -Encoding ASCII (Join-Path $outDir 'w2_differences.tsv')
@("W1 $w1 $h", "installed $ver $goroot", "W2 equal $equal differs $diff missing_in_install $missing extra_in_install $extra") |
  Set-Content -Encoding ASCII (Join-Path $outDir 'summary.txt')
"W2 equal $equal, differs $diff, missing in install $missing, extra in install $extra"
"--- non-equal entries (first 25)"
$rows | Select-Object -Skip 1 -First 25
"DONE: results in $outDir"

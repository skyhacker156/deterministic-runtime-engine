# CS4 Go harness

Server, Go clients, checker and gate tools for Case Study 4
(`../../CS4_PLAN.md`, `../../CS4_AMENDMENT_1.md`). Go 1.27.0.

| Command | Purpose |
| --- | --- |
| `cmd/server` | grpc-go v1.84.0 test server; logs every attempt |
| `cmd/client` | Go client; one source, four builds (below) |
| `cmd/checker` | applies the plan's rules to the logs (`internal/oracle`) |
| `cmd/mkmutant` | builds the planted copies `mx/mx1`, `mx/mx5` |
| `cmd/frameproxy` | HTTP/2 frame logger for gate C1 |

Module files, one per client build:

| File | grpc | Client label |
| --- | --- | --- |
| `go.mod` | v1.84.0 | `go184` |
| `go168.mod` | v1.68.2 | `go168` |
| `gomx1.mod` | v1.84.0, replaced by `./mx/mx1` | `goMX1` |
| `gomx5.mod` | v1.84.0, replaced by `./mx/mx5` | `goMX5` |

Build (PowerShell, from this directory):

```powershell
go mod tidy
go build -o bin\ .\cmd\server .\cmd\checker .\cmd\mkmutant .\cmd\frameproxy
go build -o bin\client184.exe .\cmd\client
$dir = (go mod download -json google.golang.org/grpc@v1.84.0 | ConvertFrom-Json).Dir
.\bin\mkmutant.exe -src $dir -dst mx\mx1 -variant mx1
.\bin\mkmutant.exe -src $dir -dst mx\mx5 -variant mx5
foreach ($m in 'go168','gomx1','gomx5') { go mod tidy "-modfile=$m.mod" }
go build '-modfile=go168.mod' -o bin\client168.exe .\cmd\client
go build '-modfile=gomx1.mod' -o bin\clientmx1.exe .\cmd\client
go build '-modfile=gomx5.mod' -o bin\clientmx5.exe .\cmd\client
go test -count=1 -v .\internal\oracle
```

In Windows PowerShell 5.1, quote every `-modfile=...` argument: unquoted, it is
split at the `.` and Go receives `-modfile=go168`.

Run (one server per session; each log file must not already exist):

```powershell
.\bin\server.exe -log server.jsonl
.\bin\client184.exe -client go184 -scenario S -n 20 -run r1 -out go184_S.jsonl
.\bin\checker.exe analyze -server server.jsonl -client go184_S.jsonl -report report.json -replay replay.json
```

The client refuses to run if its label does not match the grpc module it
was built with.

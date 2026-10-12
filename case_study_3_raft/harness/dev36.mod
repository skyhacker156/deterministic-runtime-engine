// DEV ONLY: local build against source checked out from GitHub, because this
// sandbox cannot reach proxy.golang.org. Not used for any scored run.
module cs3harness

go 1.24

require (
	github.com/anishathalye/porcupine v1.3.1
	go.etcd.io/raft/v3 v3.6.0
)

require (
	github.com/gogo/protobuf v1.3.2 // indirect
	github.com/golang/protobuf v1.5.4 // indirect
	google.golang.org/protobuf v1.33.0 // indirect
)

replace (
	github.com/anishathalye/porcupine => ../deps/porcupine
	go.etcd.io/raft/v3 => ../deps/raft-v3.6.0
	golang.org/x/tools => ../deps/stubs/golang.org_x_tools
	google.golang.org/protobuf => ../deps/protobuf-go
	gopkg.in/yaml.v3 => ../deps/yaml.v3
)

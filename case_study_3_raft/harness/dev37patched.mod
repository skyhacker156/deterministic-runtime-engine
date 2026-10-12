// DEV ONLY: builds against a copy of raft v3.7.0 patched to compile under
// Go 1.25 (new(expression) rewritten to a helper). Used only to type-check
// the v3.7 adapter and exercise it during development. Never for scored runs;
// those use the pristine release under Go 1.26 on the operator's machine.
module cs3harness

go 1.25

require (
	github.com/anishathalye/porcupine v1.3.1
	go.etcd.io/raft/v3 v3.7.0
)

require google.golang.org/protobuf v1.36.11 // indirect

replace (
	github.com/anishathalye/porcupine => ../deps/porcupine
	go.etcd.io/raft/v3 => ../deps/raft-v3.7.0-devpatch
	google.golang.org/protobuf => ../deps/protobuf-go-1.36.11
	gopkg.in/yaml.v3 => ../deps/yaml.v3
)

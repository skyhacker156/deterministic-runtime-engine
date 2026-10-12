package cs4

// CodeNames are the canonical gRPC status code names, indexed by number.
// They match grpc-java's Status.Code.name() and the names in A6 retry
// policies, so Go and Java logs use one spelling.
var CodeNames = [...]string{
	"OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED",
	"NOT_FOUND", "ALREADY_EXISTS", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED",
	"FAILED_PRECONDITION", "ABORTED", "OUT_OF_RANGE", "UNIMPLEMENTED",
	"INTERNAL", "UNAVAILABLE", "DATA_LOSS", "UNAUTHENTICATED",
}

// CodeName returns the canonical name for code number n.
func CodeName(n uint32) string {
	if int(n) < len(CodeNames) {
		return CodeNames[n]
	}
	return "CODE_" + itoa(int(n))
}

// CodeNumber returns the number for a canonical name, or -1.
func CodeNumber(name string) int {
	for i, s := range CodeNames {
		if s == name {
			return i
		}
	}
	return -1
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b [20]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	return string(b[i:])
}

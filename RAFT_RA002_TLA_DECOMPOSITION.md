# RA-001 Closure, and RA-002 — TLA+ Trace-Validation Machinery Decomposition

## RA-001, closed at the source boundary

The apparent R-2 weakness (`restore()`'s leader-state guard) was traced
through the complete message-processing pipeline and public API surface.
It appears structurally unreachable: three independent mechanisms
(shared higher-term demotion in `Step()`, the absence of any `MsgSnap`
case in `stepLeader`'s switch, and no bypass in the public `Node`/
`RawNode` API) all point the same way. **Runtime confirmation remains
unexecuted** — the Go 1.26 toolchain this codebase requires is
unavailable in this sandbox, and bootstrapping it was judged
disproportionate to the question, per the same discipline applied to the
FoundationDB rebuild decision. This limitation is frozen explicitly, not
implied to be resolved by the strength of the source-level case alone.

---

## RA-002 — TLA+ Trace-Validation Machinery, Source Decomposition

**Status:** decomposition only, grounded in direct reading of
`state_trace.go` (339 lines, read in full) and a targeted search of the
real `tla/*.tla` specification files. No construction, no model checking
run, no divergence yet constructed.

### What the interception point actually covers

`traceReceiveMessage(r, m)` is called **unconditionally, for every
incoming message**, at the very top of `Step()` (line 1094 — confirmed
this is the true entry point, before any state-specific dispatch).
`traceSendMessage` is similarly called from within `send()` (lines 593,
599) for every outgoing message. **The interception points themselves
are comprehensive — nothing bypasses them.**

### Where the actual gap lives

Both `traceSendMessage` and `traceReceiveMessage` contain an internal
`switch` on message type that maps only a specific subset to an actual
`TracingEvent`: `MsgApp`, `MsgHeartbeat`, `MsgSnap`, `MsgAppResp`,
`MsgHeartbeatResp`, `MsgVote`, `MsgVoteResp`. **Every other message
type — confirmed directly by reading the `default: return` — is silently
dropped and produces no trace event at all**, despite passing through the
universal interception point. This includes `MsgPreVote` and
`MsgPreVoteResp`.

### Is this a real gap, or a deliberately-scoped exclusion?

**Checked directly, not assumed either way:** a case-insensitive search
for "prevote" across both real TLA+ specification files
(`etcdraft.tla`, `Traceetcdraft.tla`) returned **zero matches.** This
resolves the question precisely: PreVote is not merely untraced relative
to a model that expects it — **PreVote is entirely outside the formal
model's scope.** The trace machinery's silent exclusion is *consistent*
with the model's own boundaries, not a violation of them. This is a more
precise and more important finding than "the tracer has a bug" — it
means the formal correspondence this library's own documentation
describes simply does not extend to this real part of the protocol,
regardless of whether tracing is enabled.

### Why this is more consequential than an obscure edge case

PreVote is not a minor implementation detail. Its own doc comment in
`raft.go` (line 228) cites it directly to **"the raft thesis section
9.6"** and states its purpose plainly: **"This prevents disruption when a
node that has been partitioned away rejoins the cluster"** — precisely
the kind of real-world failure scenario (network partition and recovery)
this whole case-study series has repeatedly found to be where verification
boundaries matter most (Temporal's live-worker-recovery finding,
`TA-006`/`TA-007`, was structurally the same shape of scenario). PreVote
is opt-in (`Config.PreVote`, defaulting to `false`), but is the kind of
feature real production deployments — the library's own README lists
etcd, Kubernetes, CockroachDB, TiDB among its users — would plausibly
enable specifically because of its stated partition-recovery benefit.

### A second, smaller item noted but not fully traced

`traceReplicate` (line 831, called from `appendEntry`) only emits a trace
event for entries of type `EntryNormal`, skipping `EntryConfChange`-type
entries. Separate functions (`traceChangeConfEvent`, `traceConfChangeEvent`)
exist and appear intended to cover configuration-change tracing through a
different path. **Whether these fully compensate for what `traceReplicate`'s
filter excludes was not confirmed in this pass** — flagged as a real,
open item rather than assumed either resolved or unresolved.

### The precise question RA-002's eventual construction should target

Not "does trace validation work" (it does, for what it covers, confirmed
by the interception-point analysis above). The sharper, now well-evidenced
question: **when PreVote is enabled, does the TLA+ trace-validation
machinery provide any assurance at all about the election-safety-relevant
behavior that occurs during the PreVote phase — or does it validate a
trace that is silently incomplete, appearing to succeed while having
observed nothing about a real, safety-relevant part of the protocol's
actual execution?**

This is a direct structural analogue to this whole case study's recurring
theme: `TA-003`/`TA-005` found Temporal's replay comparison checks
Command kind and position but not content; `FOUNDATIONDB_F3_DECOMPOSITION.md`
found FoundationDB's `ConsistencyCheck` verifies replica agreement but not
independent correctness. Here: the TLA+ trace-validation bridge verifies
implementation-model correspondence, but only within a scope that,
confirmed directly, excludes a real, thesis-cited, partition-recovery-relevant
part of the actual protocol.

---

## Explicitly not done

No model checking run. No trace collected. No divergence constructed. The
`EntryConfChange`/`traceChangeConfEvent` compensation question (noted
above) not resolved. Whether PreVote's exclusion from the model is
acknowledged anywhere in the TLA+ files' own comments (as opposed to
simply being absent) was not separately checked. Per the standing
instruction, construction is a separate, deliberate next decision — not
made here.

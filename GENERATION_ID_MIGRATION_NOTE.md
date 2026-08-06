## Schema Migration Note — generation_id (v2 hash format)

This change intentionally invalidates prior record hashes. Existing
persisted logs are not expected to remain hash-compatible across
schema versions. Version identifiers distinguish the formats rather
than attempting backward hash compatibility.

**What changed:** `KernelStateEnvelope`, `ExecutionAuditRecord`, and
`DecisionRecord` each gain a `generation_id` field (16-byte UUID4,
generated once at kernel genesis and regenerated only on an
administrative reset). This directly closes the kernel-level and
audit-level halves of Gap 1b — a verifier can now distinguish
"continuity intentionally ended here because a new generation began"
from the prior state of "cannot prove continuity across this point."
`ExecutionPolicyDecision`/`decision_hash` are unchanged — threading
generation_id there would require giving the authorizer a new
dependency on kernel state, a materially larger change than adding a
field to `DecisionRecord`, which the engine already constructs with
direct access to both.

**Version bytes normalized in the same pass:** `KernelStateEnvelope`
and `ExecutionAuditRecord` previously had no explicit format-version
byte in their hash computation (unlike `DecisionRecord`,
`ModuleRegistrationAttemptRecord`, and `ExecutionPolicy`, which
already did). Both gain one now, and `DecisionRecord`'s existing
version byte bumps 1→2. This is deliberately done at the same time as
the generation_id addition — one migration instead of two, since this
is the cheapest point at which to fix the inconsistency.

**Consequence, stated plainly:** any test that constructs
`KernelStateEnvelope`, `ExecutionAuditRecord`, or `DecisionRecord`
directly, or that asserts a specific hash value, must now pass an
explicit `generation_id`. This is expected churn in test fixtures, not
architectural churn — the semantics of the records aren't changing,
only the canonical serialization that gets hashed. See the
implementation checklist for the full list of affected files.

"""
Causal History Verifier - Phase 1 (Cross-Log Invariant Check)
(causal_history_verifier.py)

Answers, from persisted logs alone -- no live runtime objects, no
in-memory state -- the question: "does the recorded history satisfy
the causal invariants Phoenix already proves in memory?"

This is explicitly Phase 1 only: a read-only verifier over now FOUR
already-proven append-only logs (module_registration_audit_log.py,
policy_decision_record_log.py, decision_record_log.py,
execution_audit_log.py). It is NOT a recovery system -- it does not
reconstruct live runtime state, does not resume execution, and does
not touch ExecutionModuleRegistry or DeterministicExecutionEngine. See
KNOWN GAPS below for what a full recovery model would still need
beyond this.

FOUR CHECKS PERFORMED (each independently, each honestly provable from
what is actually persisted today):

1. Decision ancestry: every ExecutionAuditRecord in the audit log has
   a corresponding DecisionRecord in the decision log, joined on
   (sequence_id, module_id, generation_id), with allowed=True. This is
   the disk-only re-derivation of the in-memory Invariant B already
   proven in test_decision_record_invariants.py
   (test_invariant_b_every_audit_record_has_exactly_one_preceding_allowed_decision).

   v2 (2026-08-06): generation_id added to the join key -- see
   PROVENANCE_GRAPH_MODEL.md's headline finding. Previously joined on
   (sequence_id, module_id) only, even though both record types carry
   generation_id -- the same class of gap Check 4 was deliberately
   built to avoid for a different record pair. Since sequence_id
   resets to 0 after every administrative reset and module_id commonly
   persists across a reset, a DecisionRecord from one generation and
   an ExecutionAuditRecord from a different generation could
   previously share (sequence_id, module_id) and be incorrectly
   treated as causally linked. Fixed by mirroring Check 4's join-key
   shape, including its "generation mismatch" vs. "no corresponding
   record" diagnostic distinction.

2. Per-module sequence ordering: within each module_id, sequence_ids
   appear in non-decreasing order as recorded, separately in the
   decision log and in the audit log. This checks that each log's
   append order is causally sane per module -- it does NOT attempt to
   interleave the two logs against each other by wall-clock time (see
   KNOWN GAPS: frame_timestamp_ns is explicitly data, not wall-clock,
   per ExecutionAuditRecord's own docstring, so there is no reliable
   shared clock to interleave the two files by).

3. Module identity cross-reference: every module_id appearing in
   either the decision log or the audit log has at least one
   success=True entry in the registration attempt log. This is the
   honest version of "module identities resolve" -- it checks against
   what was actually persisted (registration ATTEMPTS), not against
   live lifecycle registry state, which was never persisted anywhere
   (see KNOWN GAPS).

4. Policy decision provenance (NEW -- closes GAP 2 below, optional):
   every DecisionRecord's decision_hash traces to a real, persisted
   PolicyDecisionRecord for the SAME execution attempt -- joined on
   (sequence_id, generation_id), never on decision_hash alone (see
   PolicyDecisionRecord's own contract docstring for why decision_hash
   collides across attempts with different observed_invocation_count,
   making it an unsafe join key by itself). This is optional and
   backward-compatible: verify_causal_history() only runs this check
   when a caller supplies policy_decision_log_path. Existing callers
   that don't are completely unaffected -- see verify_causal_history()'s
   own docstring.

   This check depends ONLY on parsing PolicyDecisionRecord and
   DecisionRecord (both pure, already-proven record/persistence
   modules) plus hash/identifier comparison. It does NOT import
   ExecutionAuthorizer, DeterministicExecutionEngine, or any other
   live-runtime module -- the same disk-files-in, pure-verifier-logic,
   result-out pattern the first three checks already establish. See
   test_verifier_runtime_isolation.py's subprocess-based proof of this
   property for the whole module; Check 4 must not be the check that
   breaks it.

===========================================================================
KNOWN GAPS -- explicitly NOT checked by this module, and why
===========================================================================

GAP 1: State-hash chain verification ("every audit chain links
correctly").

    ExecutionAuditRecord.prior_state_hash is documented as a reference
    to KernelStateEnvelope.state_hash, "captured before execution."
    Verifying that one audit record's prior_state_hash genuinely
    equals the PREVIOUS record's resulting state hash requires knowing
    how KernelStateEnvelope derives and chains state_hash across
    frames -- that derivation lives in execution_kernel_state.py, which
    this module does not have visibility into. Building this check
    without that file would mean guessing at chaining logic, which is
    exactly the mistake this project has already paid for once this
    session (see the ModuleComplianceError inheritance investigation).
    This gap closes only once execution_kernel_state.py's state_hash
    derivation is available to verify against.

    (Separately, kernel_state_replay.py's sequential-replay approach
    -- Path B -- now closes the SINGLE-generation case of this same
    question via a different mechanism entirely; see
    PHOENIX_VERIFICATION_STATE.md's Execution Generation Identity
    section. That is a real, live-KernelStateMachine replay, not a
    disk-only cross-log check like this module, and remains a
    deliberately separate capability -- see that module's own
    docstring for why it is NOT folded into cold_boot_reconstruction.py
    or this verifier.)

GAP 2: Decision hash provenance ("every decision hash exists /
is valid").

    ORIGINAL TEXT, preserved: DecisionRecord.decision_hash is
    documented as a reference to ExecutionPolicyDecision.decision_hash,
    computed by the authorizer/policy layer. That source object -- the
    ExecutionPolicyDecision itself -- is never persisted anywhere in
    the current three logs. This module can confirm decision_hash is
    present and well-formed (32 bytes), but every persisted
    DecisionRecord already satisfies that by construction
    (DecisionRecord.__post_init__ enforces it) -- so re-checking it
    here would be checking a property that cannot fail for anything
    actually on disk, which is not a meaningful verification. Closing
    this gap for real requires persisting ExecutionPolicyDecision
    itself (a fourth log, not yet built) so decision_hash can be
    checked against an independent source rather than only against its
    own downstream reference.

    UPDATE: CLOSED, optionally. ExecutionPolicyDecision is now
    persisted (wrapped in PolicyDecisionRecord, which adds the
    sequence_id/generation_id join key ExecutionPolicyDecision itself
    deliberately does not carry -- see
    policy_decision_record_contract.py). Check 4 above performs exactly
    the independent verification this gap's original text describes as
    missing. "Optionally" because verify_causal_history() does not
    require every caller to supply the fourth log path -- a caller
    that omits it gets the same three-check behavior as before, with
    policy_decision_record_count left as None on the report rather than
    silently claiming a check ran that didn't. See
    PHOENIX_VERIFICATION_STATE.md for the corresponding update to this
    project's verification ledger.
===========================================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from module_registration_audit_log import read_all_records as read_all_registration_records
from decision_record_log import read_all_decision_records
from execution_audit_log import read_all_audit_records
from policy_decision_record_log import read_all_policy_decision_records


@dataclass
class CausalHistoryReport:
    """
    Result of running all checks. `passed` is True only if every check
    that actually ran produced zero failures. `failures` lists every
    individual problem found, prefixed by which check it came from, so
    a failing report is immediately actionable without re-running
    anything.

    policy_decision_record_count is None when Check 4 did not run
    (caller did not supply policy_decision_log_path to
    verify_causal_history()) -- distinguished from 0, which means the
    check DID run and the log was legitimately empty. Do not treat None
    as "Check 4 passed" -- it means Check 4 did not execute at all.
    """
    registration_record_count: int
    decision_record_count: int
    audit_record_count: int
    policy_decision_record_count: Optional[int] = None
    failures: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


def _check_decision_ancestry(decision_records, audit_records) -> List[str]:
    """
    Check 1: every audit record's (sequence_id, module_id, generation_id)
    has a matching, allowed decision record.

    v2 (2026-08-06): generation_id added to the join key. Previously
    joined on (sequence_id, module_id) only -- see this module's own
    docstring and PROVENANCE_GRAPH_MODEL.md for why that was a real
    gap, not just a theoretical one. Mirrors
    _check_policy_decision_provenance()'s existing "generation
    mismatch" vs. "no corresponding record" diagnostic distinction --
    a decision existing at the same (sequence_id, module_id) but under
    a different generation_id is a materially different failure from
    no decision existing at all, and gets its own message.
    """
    failures = []
    allowed_keys = {
        (d.sequence_id, d.module_id, d.generation_id)
        for d in decision_records if d.allowed
    }
    denied_keys = {
        (d.sequence_id, d.module_id, d.generation_id)
        for d in decision_records if not d.allowed
    }

    for audit in audit_records:
        key = (audit.sequence_id, audit.module_id, audit.generation_id)
        if key in denied_keys and key not in allowed_keys:
            failures.append(
                f"Decision ancestry: audit record (sequence_id={audit.sequence_id}, "
                f"module_id={audit.module_id!r}, generation_id={audit.generation_id.hex()}) "
                f"has a matching DECISION record but it was DENIED -- an audit record "
                f"should never exist for a denied decision."
            )
        elif key not in allowed_keys:
            same_seq_and_module_different_generation = any(
                d.sequence_id == audit.sequence_id
                and d.module_id == audit.module_id
                and d.generation_id != audit.generation_id
                for d in decision_records
            )
            if same_seq_and_module_different_generation:
                failures.append(
                    f"Decision ancestry: audit record (sequence_id={audit.sequence_id}, "
                    f"module_id={audit.module_id!r}, generation_id={audit.generation_id.hex()}) "
                    f"has a DecisionRecord at the same (sequence_id, module_id) but a "
                    f"DIFFERENT generation_id -- these are not the same execution attempt "
                    f"and were never meant to be joined. Generation mismatch, not a missing "
                    f"decision."
                )
            else:
                failures.append(
                    f"Decision ancestry: audit record (sequence_id={audit.sequence_id}, "
                    f"module_id={audit.module_id!r}) has no corresponding allowed "
                    f"DecisionRecord in the decision log at all."
                )
    return failures


def _check_sequence_ordering(records, log_name: str) -> List[str]:
    """
    Check 2: within each module_id, sequence_id is non-decreasing in
    the order records were read from the log (i.e. the order they were
    appended). Applied separately to the decision log and the audit
    log -- see module docstring for why cross-log interleaving isn't
    attempted.
    """
    failures = []
    last_seen: Dict[str, int] = {}
    for record in records:
        module_id = record.module_id
        seq = record.sequence_id
        if module_id in last_seen and seq < last_seen[module_id]:
            failures.append(
                f"Sequence ordering ({log_name}): module_id={module_id!r} has "
                f"sequence_id {seq} appearing after {last_seen[module_id]} -- "
                f"out of causal order."
            )
        last_seen[module_id] = max(last_seen.get(module_id, seq), seq)
    return failures


def _check_module_identity_cross_reference(
    registration_records, decision_records, audit_records
) -> List[str]:
    """
    Check 3: every module_id referenced in the decision or audit logs
    has at least one successful registration attempt on record. This
    checks against persisted registration ATTEMPTS, not live registry
    state -- see module docstring GAP discussion for why that
    distinction matters.
    """
    failures = []
    successfully_registered_ids = {
        r.module_id for r in registration_records if r.success
    }

    referenced_ids = {d.module_id for d in decision_records} | {
        a.module_id for a in audit_records
    }

    for module_id in sorted(referenced_ids):
        if module_id not in successfully_registered_ids:
            failures.append(
                f"Module identity: module_id={module_id!r} appears in decision "
                f"and/or audit logs but has no successful registration attempt "
                f"in the registration log."
            )
    return failures


def _check_policy_decision_provenance(
    decision_records, policy_decision_records
) -> List[str]:
    """
    Check 4: every DecisionRecord's decision_hash traces to a real
    PolicyDecisionRecord for the SAME execution attempt.

    Join key is (sequence_id, generation_id) -- never decision_hash
    alone, since ExecutionPolicyDecision._compute_decision_hash()
    deliberately excludes observed_invocation_count, so two decisions
    at genuinely different points in history can share a decision_hash
    (see PHOENIX_VERIFICATION_STATE.md Gap 1b/Gap 2). Joining on the
    hash alone could match the WRONG historical policy decision and
    still report success -- this join avoids that by construction.

    Three distinct failure shapes, each with its own message:
      - No PolicyDecisionRecord at this (sequence_id, generation_id) at
        all, but one exists at the same sequence_id with a DIFFERENT
        generation_id: reported as a generation mismatch specifically --
        proves the join is not accidentally matching across a reset
        boundary.
      - No PolicyDecisionRecord at this (sequence_id, generation_id),
        and none at this sequence_id under any generation either:
        reported as no corresponding record at all.
      - A PolicyDecisionRecord IS found at the correct
        (sequence_id, generation_id), but its policy_decision.decision_hash
        does not match this DecisionRecord's decision_hash: reported as
        a provenance mismatch. This is the case that catches two
        otherwise-individually-valid records whose CONTENT was swapped
        between two different sequence_ids -- each record parses and
        validates fine on its own; only the cross-log join catches the
        mismatch.
    """
    failures: List[str] = []

    policy_by_key: Dict[Tuple[int, bytes], List] = {}
    policy_by_sequence_id: Dict[int, List] = {}
    for p in policy_decision_records:
        key = (p.sequence_id, p.generation_id)
        policy_by_key.setdefault(key, []).append(p)
        policy_by_sequence_id.setdefault(p.sequence_id, []).append(p)

    for decision in decision_records:
        key = (decision.sequence_id, decision.generation_id)
        matches = policy_by_key.get(key, [])

        if not matches:
            same_sequence_different_generation = [
                p for p in policy_by_sequence_id.get(decision.sequence_id, [])
                if p.generation_id != decision.generation_id
            ]
            if same_sequence_different_generation:
                other_gen = same_sequence_different_generation[0].generation_id.hex()
                failures.append(
                    f"Policy decision provenance: decision record "
                    f"(sequence_id={decision.sequence_id}, module_id={decision.module_id!r}, "
                    f"generation_id={decision.generation_id.hex()}) has a PolicyDecisionRecord "
                    f"at the same sequence_id but a DIFFERENT generation_id ({other_gen}) -- "
                    f"generation mismatch. These are not the same execution attempt and were "
                    f"never meant to be joined."
                )
            else:
                failures.append(
                    f"Policy decision provenance: decision record "
                    f"(sequence_id={decision.sequence_id}, module_id={decision.module_id!r}, "
                    f"generation_id={decision.generation_id.hex()}) has no corresponding "
                    f"PolicyDecisionRecord at all -- decision_hash cannot be independently "
                    f"verified against a real policy decision."
                )
            continue

        matching_hash_found = any(
            p.policy_decision.decision_hash == decision.decision_hash for p in matches
        )
        if not matching_hash_found:
            failures.append(
                f"Policy decision provenance: decision record "
                f"(sequence_id={decision.sequence_id}, module_id={decision.module_id!r}) "
                f"has a PolicyDecisionRecord at the same (sequence_id, generation_id), but "
                f"its policy_decision.decision_hash does not match this decision record's "
                f"decision_hash -- provenance mismatch. decision_hash cannot be traced to a "
                f"real, matching policy decision."
            )

    return failures


def verify_causal_history(
    registration_log_path: str,
    decision_log_path: str,
    audit_log_path: str,
    policy_decision_log_path: Optional[str] = None,
) -> CausalHistoryReport:
    """
    Runs Checks 1-3 against the three original logs at the given paths,
    always. Reads each log in full (via the already-proven read_all_*
    functions from each log module) -- this function performs no writes
    and touches no live runtime state.

    policy_decision_log_path (optional, added for Check 4): when
    supplied, also reads the policy decision log and runs Check 4
    (policy decision provenance). When omitted (the default), behavior
    is IDENTICAL to before Check 4 existed -- every existing caller
    (test_causal_history_verifier.py, cold_boot_reconstruction.py, the
    embedded subprocess script in test_verifier_runtime_isolation.py)
    continues to work completely unchanged, and
    CausalHistoryReport.policy_decision_record_count stays None rather
    than silently claiming a check ran that didn't.

    Propagates FileNotFoundError if any log path doesn't exist, and
    the log module's own *LogCorruptionError if any log's content is
    malformed -- those are real failures this function does not
    attempt to paper over or treat as "zero records." This applies to
    policy_decision_log_path too, when supplied.
    """
    registration_records = read_all_registration_records(registration_log_path)
    decision_records = read_all_decision_records(decision_log_path)
    audit_records = read_all_audit_records(audit_log_path)

    policy_decision_records = None
    if policy_decision_log_path is not None:
        policy_decision_records = read_all_policy_decision_records(policy_decision_log_path)

    failures: List[str] = []
    failures.extend(_check_decision_ancestry(decision_records, audit_records))
    failures.extend(_check_sequence_ordering(decision_records, "decision_log"))
    failures.extend(_check_sequence_ordering(audit_records, "audit_log"))
    failures.extend(
        _check_module_identity_cross_reference(
            registration_records, decision_records, audit_records
        )
    )
    if policy_decision_records is not None:
        failures.extend(
            _check_policy_decision_provenance(decision_records, policy_decision_records)
        )

    return CausalHistoryReport(
        registration_record_count=len(registration_records),
        decision_record_count=len(decision_records),
        audit_record_count=len(audit_records),
        policy_decision_record_count=(
            len(policy_decision_records) if policy_decision_records is not None else None
        ),
        failures=failures,
    )

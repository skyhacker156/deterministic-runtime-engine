"""
Causal History Verifier - Phase 1 (Cross-Log Invariant Check)
(causal_history_verifier.py)

Answers, from persisted logs alone -- no live runtime objects, no
in-memory state -- the question: "does the recorded history satisfy
the causal invariants Phoenix already proves in memory?"

This is explicitly Phase 1 only: a read-only verifier over three
already-proven append-only logs (module_registration_audit_log.py,
decision_record_log.py, execution_audit_log.py). It is NOT a recovery
system -- it does not reconstruct live runtime state, does not resume
execution, and does not touch ExecutionModuleRegistry or
DeterministicExecutionEngine. See KNOWN GAPS below for what a full
recovery model would still need beyond this.

THREE CHECKS PERFORMED (each independently, each honestly provable
from what is actually persisted today):

1. Decision ancestry: every ExecutionAuditRecord in the audit log has
   a corresponding DecisionRecord in the decision log, joined on
   (sequence_id, module_id), with allowed=True. This is the disk-only
   re-derivation of the in-memory Invariant B already proven in
   test_decision_record_invariants.py
   (test_invariant_b_every_audit_record_has_exactly_one_preceding_allowed_decision).

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

GAP 2: Decision hash provenance ("every decision hash exists /
is valid").

    DecisionRecord.decision_hash is documented as a reference to
    ExecutionPolicyDecision.decision_hash, computed by the authorizer/
    policy layer. That source object -- the ExecutionPolicyDecision
    itself -- is never persisted anywhere in the current three logs.
    This module can confirm decision_hash is present and well-formed
    (32 bytes), but every persisted DecisionRecord already satisfies
    that by construction (DecisionRecord.__post_init__ enforces it) --
    so re-checking it here would be checking a property that cannot
    fail for anything actually on disk, which is not a meaningful
    verification. Closing this gap for real requires persisting
    ExecutionPolicyDecision itself (a fourth log, not yet built) so
    decision_hash can be checked against an independent source rather
    than only against its own downstream reference.
===========================================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List

from module_registration_audit_log import read_all_records as read_all_registration_records
from decision_record_log import read_all_decision_records
from execution_audit_log import read_all_audit_records


@dataclass
class CausalHistoryReport:
    """
    Result of running all three checks. `passed` is True only if every
    check produced zero failures. `failures` lists every individual
    problem found, prefixed by which check it came from, so a failing
    report is immediately actionable without re-running anything.
    """
    registration_record_count: int
    decision_record_count: int
    audit_record_count: int
    failures: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


def _check_decision_ancestry(decision_records, audit_records) -> List[str]:
    """
    Check 1: every audit record's (sequence_id, module_id) has a
    matching, allowed decision record.
    """
    failures = []
    allowed_keys = {
        (d.sequence_id, d.module_id) for d in decision_records if d.allowed
    }
    denied_keys = {
        (d.sequence_id, d.module_id) for d in decision_records if not d.allowed
    }

    for audit in audit_records:
        key = (audit.sequence_id, audit.module_id)
        if key in denied_keys and key not in allowed_keys:
            failures.append(
                f"Decision ancestry: audit record (sequence_id={audit.sequence_id}, "
                f"module_id={audit.module_id!r}) has a matching DECISION record but "
                f"it was DENIED -- an audit record should never exist for a denied decision."
            )
        elif key not in allowed_keys:
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


def verify_causal_history(
    registration_log_path: str,
    decision_log_path: str,
    audit_log_path: str,
) -> CausalHistoryReport:
    """
    Runs all three checks against the three logs at the given paths.
    Reads each log in full (via the already-proven read_all_* functions
    from each log module) -- this function performs no writes and
    touches no live runtime state.

    Propagates FileNotFoundError if any log path doesn't exist, and
    the log module's own *LogCorruptionError if any log's content is
    malformed -- those are real failures this function does not
    attempt to paper over or treat as "zero records."
    """
    registration_records = read_all_registration_records(registration_log_path)
    decision_records = read_all_decision_records(decision_log_path)
    audit_records = read_all_audit_records(audit_log_path)

    failures: List[str] = []
    failures.extend(_check_decision_ancestry(decision_records, audit_records))
    failures.extend(_check_sequence_ordering(decision_records, "decision_log"))
    failures.extend(_check_sequence_ordering(audit_records, "audit_log"))
    failures.extend(
        _check_module_identity_cross_reference(
            registration_records, decision_records, audit_records
        )
    )

    return CausalHistoryReport(
        registration_record_count=len(registration_records),
        decision_record_count=len(decision_records),
        audit_record_count=len(audit_records),
        failures=failures,
    )

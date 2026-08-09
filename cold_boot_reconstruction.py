"""
Cold Boot Reconstruction
(cold_boot_reconstruction.py)

Implements exactly the SHALL items of COLD_BOOT_RECONSTRUCTION_CONTRACT.md,
and nothing the contract's SHALL NOT items forbid. This is deliberately
an assembly of already-proven pieces (the three log readers,
causal_history_verifier.py) into a single documented entry point --
not new capability. Every field/method below is annotated with which
contract clause it implements.

Given three persisted log paths, with NO live runtime objects and NO
in-memory state from any prior process (the isolation boundary already
proven in test_verifier_runtime_isolation.py, which this module
inherits by construction -- it imports only the same log-reading
modules and causal_history_verifier, nothing from the runtime), this
module reconstructs:

    SHALL 1: registration history
    SHALL 2: authorization history
    SHALL 3: execution ordering (verified, not just loaded)
    SHALL 4: the two specific persisted causal relationships
    SHALL 5: hash consistency, for the three record types where this
             is proven -- NOT for KernelStateEnvelope.state_hash,
             which remains unavailable pending Gap 1

This module does NOT import KernelStateEnvelope, KernelStateMachine,
or anything from execution_kernel_state.py -- consistent with SHALL 5's
carve-out and Gap 1 remaining open. It does NOT attempt to detect or
label reset generations (SHALL NOT 2), and ColdBootReconstructionResult
carries no field that could be mistaken for one.
"""

from dataclasses import dataclass
from typing import Tuple

from module_registration_audit import ModuleRegistrationAttemptRecord
from module_registration_audit_log import read_all_records as _read_registration_log
from decision_record_contract import DecisionRecord
from decision_record_log import read_all_decision_records as _read_decision_log
from execution_audit_contract import ExecutionAuditRecord
from execution_audit_log import read_all_audit_records as _read_audit_log
from causal_history_verifier import verify_causal_history_from_records, CausalHistoryReport


@dataclass
class ColdBootReconstructionResult:
    """
    The complete result of a cold-boot reconstruction attempt.

    Every field here maps to a specific SHALL item in
    COLD_BOOT_RECONSTRUCTION_CONTRACT.md. There is deliberately no
    field for: RAM/scheduler/queue state (SHALL NOT 1), reset
    generation or epoch (SHALL NOT 2), policy invocation counters
    (SHALL NOT 3), or kernel state_hash / KernelStateEnvelope of any
    kind (SHALL 5's carve-out, contingent on Gap 1).

    reconstruction_valid does NOT mean "the runtime behaved
    correctly" -- it means "the causal relationships this schema can
    represent are internally consistent." See causal_report.failures
    for specifics when False. Histories are still populated even when
    reconstruction_valid is False -- a failed causal check is a
    finding about RELATIONSHIPS between records, not a reason to
    withhold the records themselves.
    """
    registration_history: Tuple[ModuleRegistrationAttemptRecord, ...]  # SHALL 1
    authorization_history: Tuple[DecisionRecord, ...]                  # SHALL 2
    execution_history: Tuple[ExecutionAuditRecord, ...]                # loaded here; ordering verified via causal_report (SHALL 3)
    causal_report: CausalHistoryReport                                 # SHALL 3 (ordering) + SHALL 4 (ancestry, provenance)

    @property
    def reconstruction_valid(self) -> bool:
        return self.causal_report.passed


def reconstruct_cold_boot(
    registration_log_path: str,
    decision_log_path: str,
    audit_log_path: str,
) -> ColdBootReconstructionResult:
    """
    The cold-boot reconstruction entry point. Reads all three logs
    fresh from disk (no caching, no prior state assumed) and returns
    everything COLD_BOOT_RECONSTRUCTION_CONTRACT.md's SHALL items
    permit reconstructing.

    SHALL 5 compliance note: every record returned here is constructed
    via its own record class (ModuleRegistrationAttemptRecord,
    DecisionRecord, ExecutionAuditRecord) through the existing,
    already-proven *_from_json functions -- each of which triggers
    that class's own __post_init__ hash derivation. This function does
    NOT reimplement hash computation anywhere; it has no import of
    hashlib and performs no hashing of its own. This satisfies the
    contract's implementation constraint on SHALL 5 by construction,
    not by convention -- see test_cold_boot_reconstruction.py's
    structural test for direct confirmation.

    Propagates FileNotFoundError if any log path doesn't exist, and
    the underlying *LogCorruptionError if any log's content is
    malformed at the parse level -- this function does not paper over
    either, consistent with every log reader it's built on.

    SNAPSHOT-IDENTITY FIX (2026-08-09) -- closes an Orphan/identity-of-
    evidence finding, confirmed by direct adversarial construction and
    execution: this function used to call verify_causal_history(path,
    ...), which independently RE-READ each log from disk -- a second,
    separate read from the one this function had already performed for
    registration_history/authorization_history/execution_history above.
    Nothing connected the two reads. A caller could receive a returned
    history of N records while causal_report reflected verification of
    a DIFFERENT record set, with reconstruction_valid reporting True
    and zero failures -- a silently wrong "verified" claim over data
    that was never actually checked, demonstrated concretely (3 records
    returned, 2 verified, reconstruction_valid=True, zero failures,
    before this fix).

    Fixed by calling verify_causal_history_from_records() with the
    EXACT record objects already read above, rather than re-reading via
    paths -- true identity of evidence (the same objects), not merely
    matching counts. See verify_causal_history_from_records()'s own
    docstring in causal_history_verifier.py for the full account.
    """
    registration_history = _read_registration_log(registration_log_path)
    authorization_history = _read_decision_log(decision_log_path)
    execution_history = _read_audit_log(audit_log_path)

    causal_report = verify_causal_history_from_records(
        registration_history, authorization_history, execution_history
    )

    return ColdBootReconstructionResult(
        registration_history=registration_history,
        authorization_history=authorization_history,
        execution_history=execution_history,
        causal_report=causal_report,
    )

"""
Kernel State Hash Replay - Gap 1, Path (b)
(kernel_state_replay.py)

Sequential replay through a REAL KernelStateMachine instance, verifying
that persisted ExecutionAuditRecord.prior_state_hash values match what
KernelStateMachine.get_envelope().state_hash actually derives when
replayed from genesis through a given execution history in order.

This is Path (b) from COLD_BOOT_RECONSTRUCTION_CONTRACT.md's SHALL 5
kernel-state entry: sequential replay through the original state
machine implementation, NOT a persisted-field recomputation (Path a,
not built). This module constructs a real, mutable KernelStateMachine
-- a deliberate, documented departure from the cold-boot verifier's
prior passive-record-only isolation posture. This module is kept
SEPARATE from cold_boot_reconstruction.py for exactly that reason --
folding it in would silently change what "cold boot reconstruction"
means and should be a deliberate contract decision, not an incidental
one.

SCOPE LIMITATIONS (explicit, not silent -- each is a real, separate
gap, not covered by this module):

1. SINGLE kernel/engine run only. KernelStateMachine has no
   per-module partitioning -- record_frame_execution() enforces one
   GLOBAL monotonic sequence, matching exactly one
   DeterministicExecutionEngine instance (which wraps exactly one
   module). This replay function assumes the execution_history passed
   to it belongs to ONE such engine run, in original chronological
   order. Nothing in the current schema persists an engine/session
   identifier to verify that assumption holds -- if records from
   multiple distinct engine instances were interleaved in one audit
   log, this function cannot detect that and its output would be
   meaningless.

2. GENESIS ASSUMPTION. Replay always starts from a fresh
   KernelStateMachine(initial_state=UNINITIALIZED), transitioned to
   READY -- mirroring engine.initialize() on a truly fresh engine.
   There is no way to know from the audit log alone whether the FIRST
   record in the given history was actually preceded by a prior reset
   (see Gap 1b) -- this function cannot detect that and assumes it
   was not.

3. CANNOT CONTINUE PAST A FAULT without external reset information.
   Per Gap 1b, an administrative reset is indistinguishable from a
   fresh start in the current schema. When a record with success=False
   is encountered, replay verifies up through that record and then
   STOPS -- it does not guess whether a reset occurred and attempt to
   continue, since doing so would silently assume away exactly the
   ambiguity Gap 1b proves exists. Any records after the fault are
   reported as unverified, explicitly, rather than misverified.
"""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from execution_kernel_state import KernelStateMachine, KernelState
from execution_audit_contract import ExecutionAuditRecord


@dataclass
class KernelReplayReport:
    """
    Result of replaying one execution history through a real
    KernelStateMachine. See module docstring for the three scope
    limitations this report's fields reflect.
    """
    total_records: int
    verified_count: int
    failures: List[str] = field(default_factory=list)
    stopped_at_fault_index: Optional[int] = None
    unverified_after_fault_count: int = 0

    @property
    def fully_verified(self) -> bool:
        """
        True when every record actually present in the given history
        was replayed and matched (verified_count == total_records,
        no failures), AND nothing is known to be missing afterward
        (unverified_after_fault_count == 0).

        A history that legitimately ends at a fault, with the fault
        frame itself successfully verified and nothing known to come
        after it, IS fully_verified -- a fault occurring is not itself
        disqualifying. What disqualifies verification is
        unverified_after_fault_count > 0: real evidence that records
        exist which this function could not check because it refused
        to guess past an unresolvable fault (see module docstring,
        limitation 3).
        """
        return (
            len(self.failures) == 0
            and self.unverified_after_fault_count == 0
            and self.verified_count == self.total_records
        )


def replay_and_verify_state_hashes(
    execution_history: Tuple[ExecutionAuditRecord, ...],
) -> KernelReplayReport:
    """
    Replays execution_history, IN THE GIVEN ORDER, through a fresh real
    KernelStateMachine starting from genesis. For each record, compares
    the machine's envelope hash (captured BEFORE that frame would have
    been processed, matching exactly when the original engine captured
    prior_envelope in process_frame()) against the record's persisted
    prior_state_hash.

    See module docstring for the three scope limitations. This function
    does not attempt to detect or work around any of them -- it either
    verifies what it can, or stops and reports what it cannot, per
    limitation 3.
    """
    machine = KernelStateMachine(initial_state=KernelState.UNINITIALIZED)
    machine.transition_to(KernelState.INITIALIZING)
    machine.transition_to(KernelState.READY)

    failures: List[str] = []
    verified_count = 0
    stopped_at_fault_index: Optional[int] = None

    for i, record in enumerate(execution_history):
        prior_envelope = machine.get_envelope()

        if prior_envelope.state_hash != record.prior_state_hash:
            failures.append(
                f"Record index {i} (sequence_id={record.sequence_id}): replayed "
                f"prior_state_hash {prior_envelope.state_hash.hex()} does not "
                f"match persisted prior_state_hash {record.prior_state_hash.hex()}."
            )
        else:
            verified_count += 1

        # Advance the REAL state machine exactly as the original engine
        # would have -- same transition sequence, same
        # record_frame_execution() call, using the record's own
        # sequence_id (which must be contiguous from 0, since the
        # original engine's own record_frame_execution already
        # enforced that at write time).
        if machine.current_state == KernelState.READY:
            machine.transition_to(KernelState.PROCESSING)
        machine.record_frame_execution(record.sequence_id)

        if record.success:
            machine.transition_to(KernelState.READY)
        else:
            machine.transition_to(
                KernelState.FAULTED,
                reason=record.error_message or "unspecified",
            )
            stopped_at_fault_index = i
            break

    unverified_after_fault_count = 0
    if stopped_at_fault_index is not None:
        unverified_after_fault_count = (
            len(execution_history) - stopped_at_fault_index - 1
        )

    return KernelReplayReport(
        total_records=len(execution_history),
        verified_count=verified_count,
        failures=failures,
        stopped_at_fault_index=stopped_at_fault_index,
        unverified_after_fault_count=unverified_after_fault_count,
    )


class KernelStateVerifier(ABC):
    """
    Interface for anything capable of verifying KernelStateEnvelope.
    state_hash consistency for a given execution history. Exists so
    future verification strategies (e.g. Path A -- persisted-field
    recomputation, should it ever be built once a schema change adds
    the raw inputs) can be swapped in without changing callers.

    Step 1 of this session's implementation plan: extracting the
    existing replay logic behind this interface, rather than leaving
    it as a bare free function only.
    """

    @abstractmethod
    def verify(self, execution_history: Tuple[ExecutionAuditRecord, ...]) -> KernelReplayReport:
        ...


class SequentialReplayKernelVerifier(KernelStateVerifier):
    """
    Path (B) / "Canonical Replay Verification" per
    COLD_BOOT_RECONSTRUCTION_CONTRACT.md: sequential replay through a
    real KernelStateMachine. Thin wrapper around
    replay_and_verify_state_hashes() -- the free function remains the
    actual implementation and stays available directly for callers who
    don't need the interface (e.g. existing tests in this file).
    """

    def verify(self, execution_history: Tuple[ExecutionAuditRecord, ...]) -> KernelReplayReport:
        return replay_and_verify_state_hashes(execution_history)
"""
Kernel State Hash Replay - Gap 1, Path (b)
(kernel_state_replay.py)

Sequential replay through a REAL KernelStateMachine instance, verifying
that persisted ExecutionAuditRecord.prior_state_hash values match what
KernelStateMachine.get_envelope().state_hash actually derives when
replayed from a known generation through a given execution history in
order.

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

GENERATION_ID (v2): replay now reconstructs the machine via
KernelStateMachine.from_history(), seeded with the FIRST record's own
generation_id, rather than assuming a fresh genesis. This resolves
what used to be limitation 2 below (the old "genesis assumption") --
replay no longer has to guess whether the history it's given actually
started at a true genesis; it adopts whatever generation the log
itself asserts and verifies against that.

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

2. SINGLE GENERATION only (see from_history()'s own docstring for the
   full reasoning). Replay adopts the first record's generation_id and
   verifies every subsequent record against it. The moment a record's
   generation_id differs -- i.e. the real history this log describes
   crossed an administrative reset (FAULTED -> INITIALIZING) somewhere
   in this range -- replay STOPS at that record, exactly as it already
   does for an unresolved fault (limitation 3), and reports
   generation_boundary_index rather than guessing whether records past
   that point would have matched. Replaying THROUGH a reset and
   adopting each successive generation in turn is a tracked follow-up,
   not attempted here.

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
    KernelStateMachine. See module docstring for the scope limitations
    this report's fields reflect.
    """
    total_records: int
    verified_count: int
    failures: List[str] = field(default_factory=list)
    stopped_at_fault_index: Optional[int] = None
    unverified_after_fault_count: int = 0
    generation_boundary_index: Optional[int] = None
    unverified_after_boundary_count: int = 0

    @property
    def fully_verified(self) -> bool:
        """
        True when every record actually present in the given history
        was replayed and matched (verified_count == total_records,
        no failures), AND nothing is known to be missing afterward --
        neither because of an unresolved fault
        (unverified_after_fault_count == 0) nor because replay hit a
        generation boundary it isn't scoped to cross
        (unverified_after_boundary_count == 0).

        A history that legitimately ends at a fault, with the fault
        frame itself successfully verified and nothing known to come
        after it, IS fully_verified -- a fault occurring is not itself
        disqualifying. Same principle for a generation boundary
        occurring exactly at the end of the given history with nothing
        after it: what disqualifies verification in both cases is
        records existing that this function could not check, not the
        boundary event itself.
        """
        return (
            len(self.failures) == 0
            and self.unverified_after_fault_count == 0
            and self.unverified_after_boundary_count == 0
            and self.verified_count == self.total_records
        )


def replay_and_verify_state_hashes(
    execution_history: Tuple[ExecutionAuditRecord, ...],
) -> KernelReplayReport:
    """
    Replays execution_history, IN THE GIVEN ORDER, through a real
    KernelStateMachine reconstructed via from_history() and seeded with
    the first record's own generation_id. For each record, compares the
    machine's envelope hash (captured BEFORE that frame would have been
    processed, matching exactly when the original engine captured
    prior_envelope in process_frame()) against the record's persisted
    prior_state_hash -- but only after confirming the record still
    belongs to the generation replay is currently reconstructing.

    See module docstring for the scope limitations. This function does
    not attempt to detect or work around any of them -- it either
    verifies what it can, or stops and reports what it cannot, per
    limitations 2 and 3.
    """
    if not execution_history:
        return KernelReplayReport(total_records=0, verified_count=0)

    machine = KernelStateMachine.from_history(
        generation_id=execution_history[0].generation_id,
        state=KernelState.READY,
        last_processed_seq=-1,
        total_frames_processed=0,
        fault_reason=None,
    )

    failures: List[str] = []
    verified_count = 0
    stopped_at_fault_index: Optional[int] = None
    generation_boundary_index: Optional[int] = None

    for i, record in enumerate(execution_history):
        # Generation boundary check comes FIRST, before any hash
        # comparison: a mismatched generation_id means this record
        # belongs to a different lifetime than the one this machine
        # currently represents, so comparing state_hash against it
        # would be a meaningless comparison, not a real failure.
        if record.generation_id != machine.generation_id:
            generation_boundary_index = i
            break

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
            # NOTE: this transition_to(FAULTED, ...) call runs through
            # the ordinary production transition path. It does NOT
            # touch generation_id -- only the FAULTED -> INITIALIZING
            # branch does that, and replay never drives this machine
            # into INITIALIZING. If it ever did, that call would mint
            # a genuinely new random generation_id (identical behavior
            # to production, since it's the same code path) -- which
            # is exactly the multi-generation case limitation 2 keeps
            # this function from silently mishandling.
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

    unverified_after_boundary_count = 0
    if generation_boundary_index is not None:
        # Unlike the fault case, the record AT the boundary index was
        # never verified at all (we broke before touching its hash),
        # so it counts as unverified too -- no "- 1".
        unverified_after_boundary_count = (
            len(execution_history) - generation_boundary_index
        )

    return KernelReplayReport(
        total_records=len(execution_history),
        verified_count=verified_count,
        failures=failures,
        stopped_at_fault_index=stopped_at_fault_index,
        unverified_after_fault_count=unverified_after_fault_count,
        generation_boundary_index=generation_boundary_index,
        unverified_after_boundary_count=unverified_after_boundary_count,
    )


class KernelStateVerifier(ABC):
    """
    Interface for anything capable of verifying KernelStateEnvelope.
    state_hash consistency for a given execution history. Exists so
    future verification strategies (e.g. Path A -- persisted-field
    recomputation, should it ever be built once a schema change adds
    the raw inputs) can be swapped in without changing callers.
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

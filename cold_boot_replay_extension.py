"""
Cold Boot Replay Extension
(cold_boot_replay_extension.py)

Combines the passive cold-boot verifier (cold_boot_reconstruction.py,
UNCHANGED by this file -- see COLD_BOOT_RECONSTRUCTION_CONTRACT.md's
"Canonical Replay Verification" section for why) with kernel state
hash replay (kernel_state_replay.py) -- Path (B) for Gap 1.

This is a SEPARATE entry point from reconstruct_cold_boot() on
purpose: calling reconstruct_cold_boot_with_replay() is an explicit
opt-in to a DIFFERENT isolation posture (a live, mutable
KernelStateMachine is constructed internally by the replay verifier).
reconstruct_cold_boot() itself remains strictly passive and is not
modified by this file.
"""

from dataclasses import dataclass
from typing import Optional

from cold_boot_reconstruction import reconstruct_cold_boot, ColdBootReconstructionResult
from kernel_state_replay import (
    KernelStateVerifier,
    SequentialReplayKernelVerifier,
    KernelReplayReport,
)


@dataclass
class ColdBootReplayResult:
    """
    Combines the passive reconstruction result with the (separately
    opted-into) kernel replay report. fully_verified requires BOTH the
    passive causal checks and the kernel replay to have succeeded --
    neither alone is sufficient to call the history fully verified.
    """
    passive: ColdBootReconstructionResult
    kernel_replay: KernelReplayReport

    @property
    def fully_verified(self) -> bool:
        return self.passive.reconstruction_valid and self.kernel_replay.fully_verified


def reconstruct_cold_boot_with_replay(
    registration_log_path: str,
    decision_log_path: str,
    audit_log_path: str,
    kernel_verifier: Optional[KernelStateVerifier] = None,
) -> ColdBootReplayResult:
    """
    Runs the existing, unchanged reconstruct_cold_boot() first, then
    separately runs kernel state hash replay over the resulting
    execution_history.

    kernel_verifier defaults to SequentialReplayKernelVerifier() (Path
    B) but accepts any KernelStateVerifier implementation -- this is
    the actual point of extracting the interface in
    kernel_state_replay.py: a future Path (A) implementation (if a
    schema change ever persists the raw derivation inputs) could be
    substituted here without this function changing at all.
    """
    passive = reconstruct_cold_boot(
        registration_log_path, decision_log_path, audit_log_path
    )

    verifier = kernel_verifier if kernel_verifier is not None else SequentialReplayKernelVerifier()
    kernel_replay = verifier.verify(passive.execution_history)

    return ColdBootReplayResult(passive=passive, kernel_replay=kernel_replay)
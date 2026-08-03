"""
Module: Phoenix A Execution Core (Layer 3)
ID: SENTINEL-PHOENIX-CORE-V1
Description: Stateless weight-clamping and slew-rate governor implementation.
"""

from dataclasses import dataclass
from enum import Enum
import math

W_MIN = 0.0
W_MAX = 1.0
DEFAULT_SAFE_DT = 0.01
MAX_SLEW_RATE = 0.5


class ExecutionStatus(str, Enum):
    CONVERGING = "CONVERGING"
    AT_EQUILIBRIUM = "AT_EQUILIBRIUM"
    POLICY_FALLBACK = "POLICY_FALLBACK"


@dataclass(frozen=True)
class PhoenixInputPacket:
    current_weight: float
    target_weight: float
    dt: float


@dataclass(frozen=True)
class PhoenixOutputPacket:
    next_weight: float
    delta_applied: float
    status: ExecutionStatus


class PhoenixAExecutionCore:

    @staticmethod
    def step(packet: PhoenixInputPacket) -> PhoenixOutputPacket:
        # Step 1: Policy Sanitization
        dt_is_valid = math.isfinite(packet.dt) and packet.dt > 0.0
        dt_valid = packet.dt if dt_is_valid else DEFAULT_SAFE_DT

        curr_is_valid = math.isfinite(packet.current_weight)
        tgt_is_valid = math.isfinite(packet.target_weight)

        # Fallback triggers if ANY input field is invalid/non-finite
        fallback_triggered = not (curr_is_valid and tgt_is_valid and dt_is_valid)

        curr = packet.current_weight if curr_is_valid else W_MIN
        tgt = packet.target_weight if tgt_is_valid else W_MIN

        # Step 2: Hard Geometric Clamp
        curr_clamped = max(W_MIN, min(W_MAX, curr))
        tgt_clamped = max(W_MIN, min(W_MAX, tgt))

        # Step 3: Equilibrium Check (<= 1e-9 boundary match)
        if abs(curr_clamped - tgt_clamped) <= 1e-9:
            return PhoenixOutputPacket(
                next_weight=tgt_clamped,
                delta_applied=0.0,
                status=(
                    ExecutionStatus.POLICY_FALLBACK
                    if fallback_triggered
                    else ExecutionStatus.AT_EQUILIBRIUM
                ),
            )

        # Step 4: Slew Bounding
        max_delta_step = MAX_SLEW_RATE * dt_valid
        raw_delta = tgt_clamped - curr_clamped

        if raw_delta > 0.0:
            applied_delta = min(raw_delta, max_delta_step)
            next_w = min(curr_clamped + applied_delta, tgt_clamped)
        else:
            applied_delta = max(raw_delta, -max_delta_step)
            next_w = max(curr_clamped + applied_delta, tgt_clamped)

        final_weight = max(W_MIN, min(W_MAX, next_w))

        return PhoenixOutputPacket(
            next_weight=final_weight,
            delta_applied=final_weight - curr_clamped,
            status=(
                ExecutionStatus.POLICY_FALLBACK
                if fallback_triggered
                else ExecutionStatus.CONVERGING
            ),
        )
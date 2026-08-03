"""
Phoenix A Risk Governor - Policy Verification & Circuit Breaker Harness
Module ID: SENTINEL-PHOENIX-A-GOVERNOR-V1
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from enum import Enum
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Import core schema from the verified kernel
from phoenix_a_core import PhoenixOutputPacket, ExecutionStatus, W_MIN, W_MAX


class GovernorAction(Enum):
    ALLOW = "ALLOW"
    THROTTLE = "THROTTLE"
    HALT = "HALT"


@dataclass(frozen=True)
class RiskMetrics:
    """Immutable system risk snapshot."""
    max_drawdown_pct: float  # e.g., 0.15 for 15%
    emergency_halt: bool
    portfolio_var: float      # Value at Risk metric


@dataclass(frozen=True)
class GovernorDecisionPacket:
    """Immutable output from the Risk Governor evaluation."""
    authorized_weight: float
    action: GovernorAction
    reason: str


class PhoenixARiskGovernor:
    """
    Stateless risk governance filter.
    Enforces dynamic position caps and circuit breaker overrides on Phoenix Core outputs.
    Fails closed on non-finite, missing, or corrupted risk telemetry.
    """

    MAX_ALLOWED_DRAWDOWN: float = 0.20  # 20% system drawdown ceiling
    MAX_VAR_THRESHOLD: float = 0.05    # VaR threshold limit
    SAFE_THROTTLE_CAP: float = 0.50     # Defensive weight cap during high/corrupted VaR

    @classmethod
    def evaluate(
        cls, core_output: PhoenixOutputPacket, risk: RiskMetrics
    ) -> GovernorDecisionPacket:
        """
        Evaluates a proposed weight state against dynamic system risk metrics.
        Fails closed on non-finite inputs.
        """
        # Rule 1: Emergency Hard Halt
        if risk.emergency_halt:
            return GovernorDecisionPacket(
                authorized_weight=W_MIN,
                action=GovernorAction.HALT,
                reason="EMERGENCY_HALT_TRIGGERED",
            )

        # Rule 2: Drawdown Violation Circuit Breaker (Fail Closed on NaN/Inf)
        if (
            not math.isfinite(risk.max_drawdown_pct)
            or risk.max_drawdown_pct >= cls.MAX_ALLOWED_DRAWDOWN
        ):
            return GovernorDecisionPacket(
                authorized_weight=W_MIN,
                action=GovernorAction.HALT,
                reason="DRAWDOWN_CEILING_EXCEEDED_OR_INVALID",
            )

        # Rule 3: VaR Exceeded or Corrupted/Non-Finite (Fail Closed -> Defensive Throttle)
        var_invalid = not math.isfinite(risk.portfolio_var)
        var_exceeded = var_invalid or (risk.portfolio_var > cls.MAX_VAR_THRESHOLD)

        if var_exceeded:
            throttled_w = min(core_output.next_weight, cls.SAFE_THROTTLE_CAP)
            reason_str = (
                "VAR_DATA_CORRUPTED_FAIL_CLOSED"
                if var_invalid
                else "VAR_THROTTLE_APPLIED"
            )
            return GovernorDecisionPacket(
                authorized_weight=throttled_w,
                action=GovernorAction.THROTTLE,
                reason=reason_str,
            )

        # Rule 4: Standard Clearance (All metrics verified finite and within bounds)
        return GovernorDecisionPacket(
            authorized_weight=core_output.next_weight,
            action=GovernorAction.ALLOW,
            reason="NORMAL_OPERATION",
        )


# =====================================================================
# VERIFICATION SUITE FOR RISK GOVERNOR
# =====================================================================
class TestPhoenixARiskGovernorInvariants:

    @settings(max_examples=1000)
    @given(
        weight=st.floats(min_value=W_MIN, max_value=W_MAX),
        drawdown=st.floats(allow_nan=True, allow_infinity=True),
        var=st.floats(allow_nan=True, allow_infinity=True),
        halt=st.booleans(),
    )
    def test_invariant_g1_safety_ceiling(
        self, weight: float, drawdown: float, var: float, halt: bool
    ):
        """
        INVARIANT G1: Authorized weight MUST always be bounded in [W_MIN, W_MAX]
        and never exceed core's proposed weight under any risk state.
        """
        core_packet = PhoenixOutputPacket(
            next_weight=weight, delta_applied=0.01, status=ExecutionStatus.CONVERGING
        )
        risk = RiskMetrics(max_drawdown_pct=drawdown, emergency_halt=halt, portfolio_var=var)

        decision = PhoenixARiskGovernor.evaluate(core_packet, risk)

        assert W_MIN <= decision.authorized_weight <= W_MAX
        assert decision.authorized_weight <= core_packet.next_weight + 1e-9

    @given(weight=st.floats(min_value=W_MIN, max_value=W_MAX))
    def test_invariant_g2_halt_override(self, weight: float):
        """
        INVARIANT G2: Emergency halt must force authorized weight to W_MIN immediately.
        """
        core_packet = PhoenixOutputPacket(
            next_weight=weight, delta_applied=0.0, status=ExecutionStatus.CONVERGING
        )
        risk = RiskMetrics(max_drawdown_pct=0.05, emergency_halt=True, portfolio_var=0.01)

        decision = PhoenixARiskGovernor.evaluate(core_packet, risk)

        assert decision.authorized_weight == W_MIN
        assert decision.action == GovernorAction.HALT

    @given(
        weight=st.floats(min_value=W_MIN, max_value=W_MAX),
        invalid_var=st.sampled_from([float("nan"), float("inf"), float("-inf")]),
    )
    def test_invariant_g3_fail_closed_on_invalid_var(self, weight: float, invalid_var: float):
        """
        INVARIANT G3: Non-finite VaR telemetry MUST NEVER fall through to ALLOW.
        Must result in a THROTTLE action.
        """
        core_packet = PhoenixOutputPacket(
            next_weight=weight, delta_applied=0.01, status=ExecutionStatus.CONVERGING
        )
        risk = RiskMetrics(max_drawdown_pct=0.05, emergency_halt=False, portfolio_var=invalid_var)

        decision = PhoenixARiskGovernor.evaluate(core_packet, risk)

        assert decision.action == GovernorAction.THROTTLE
        assert decision.authorized_weight <= PhoenixARiskGovernor.SAFE_THROTTLE_CAP
        assert decision.reason == "VAR_DATA_CORRUPTED_FAIL_CLOSED"

    @given(
        weight=st.floats(min_value=W_MIN, max_value=W_MAX),
        invalid_dd=st.sampled_from([float("nan"), float("inf"), float("-inf")]),
    )
    def test_invariant_g4_fail_closed_on_invalid_drawdown(self, weight: float, invalid_dd: float):
        """
        INVARIANT G4: Non-finite drawdown telemetry MUST result in immediate HALT.
        """
        core_packet = PhoenixOutputPacket(
            next_weight=weight, delta_applied=0.01, status=ExecutionStatus.CONVERGING
        )
        risk = RiskMetrics(max_drawdown_pct=invalid_dd, emergency_halt=False, portfolio_var=0.01)

        decision = PhoenixARiskGovernor.evaluate(core_packet, risk)

        assert decision.action == GovernorAction.HALT
        assert decision.authorized_weight == W_MIN


if __name__ == "__main__":
    pytest.main(["-v", __file__])
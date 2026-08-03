"""
Phoenix A Execution Pipeline - Composition & Integration Harness
Module ID: SENTINEL-PHOENIX-A-PIPELINE-V1
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List
import pytest
from hypothesis import given, strategies as st, settings

# Import components from verified core and governor modules
from phoenix_a_core import (
    PhoenixAExecutionCore,
    PhoenixInputPacket,
    PhoenixOutputPacket,
    ExecutionStatus,
    W_MIN,
    W_MAX,
)
from phoenix_a_risk_governor import (
    PhoenixARiskGovernor,
    RiskMetrics,
    GovernorDecisionPacket,
    GovernorAction,
)


@dataclass(frozen=True)
class PipelineStepResult:
    """Immutable outcome of a single pipeline step execution."""
    core_output: PhoenixOutputPacket
    governor_decision: GovernorDecisionPacket
    final_authorized_weight: float


class PhoenixAPipeline:
    """
    End-to-end execution pipeline linking Phoenix Core and Risk Governor.
    Composition: Core(Input) -> Proposed Weight -> Governor(Risk) -> Authorized Weight.
    """

    @classmethod
    def execute_step(
        cls, input_packet: PhoenixInputPacket, risk: RiskMetrics
    ) -> PipelineStepResult:
        """Executes a single step through the combined Core -> Governor pipeline."""
        core_output = PhoenixAExecutionCore.step(input_packet)
        governor_decision = PhoenixARiskGovernor.evaluate(core_output, risk)

        return PipelineStepResult(
            core_output=core_output,
            governor_decision=governor_decision,
            final_authorized_weight=governor_decision.authorized_weight,
        )

    @classmethod
    def execute_trajectory(
        cls,
        initial_weight: float,
        target_weight: float,
        dt_sequence: List[float],
        risk_sequence: List[RiskMetrics],
    ) -> List[PipelineStepResult]:
        """
        Executes a sequence of steps over time, feeding each authorized output
        weight back as the input weight for the subsequent step.
        """
        results: List[PipelineStepResult] = []
        current_w = initial_weight

        for dt, risk in zip(dt_sequence, risk_sequence):
            inp = PhoenixInputPacket(
                current_weight=current_w, target_weight=target_weight, dt=dt
            )
            step_res = cls.execute_step(inp, risk)
            results.append(step_res)
            current_w = step_res.final_authorized_weight

        return results


# =====================================================================
# INTEGRATION & INVARIANT TEST SUITE
# =====================================================================
class TestPhoenixAPipelineInvariants:

    @settings(max_examples=1000)
    @given(
        current_w=st.floats(allow_nan=True, allow_infinity=True),
        target_w=st.floats(allow_nan=True, allow_infinity=True),
        dt=st.floats(allow_nan=True, allow_infinity=True),
        drawdown=st.floats(allow_nan=True, allow_infinity=True),
        var=st.floats(allow_nan=True, allow_infinity=True),
        halt=st.booleans(),
    )
    def test_invariant_p1_end_to_end_safety_and_boundedness(
        self,
        current_w: float,
        target_w: float,
        dt: float,
        drawdown: float,
        var: float,
        halt: bool,
    ):
        """
        INVARIANT P1: End-to-End Absolute Boundedness.
        Any combination of noisy/corrupted inputs across both Core and Governor
        must yield a final authorized weight strictly within [W_MIN, W_MAX].
        """
        inp = PhoenixInputPacket(current_weight=current_w, target_weight=target_w, dt=dt)
        risk = RiskMetrics(max_drawdown_pct=drawdown, emergency_halt=halt, portfolio_var=var)

        result = PhoenixAPipeline.execute_step(inp, risk)

        assert math.isfinite(result.final_authorized_weight)
        assert W_MIN <= result.final_authorized_weight <= W_MAX

    @settings(max_examples=500)
    @given(
        initial_w=st.floats(min_value=W_MIN, max_value=W_MAX),
        target_w=st.floats(min_value=W_MIN, max_value=W_MAX),
        steps=st.integers(min_value=2, max_value=20),
    )
    def test_invariant_p2_normal_trajectory_convergence(
        self, initial_w: float, target_w: float, steps: int
    ):
        """
        INVARIANT P2: Trajectory Directional Consistency.
        Under nominal conditions (no halts/throttles), step sequence strictly
        moves toward target weight without wild oscillation or overshoot.
        """
        dt_seq = [0.1] * steps
        nominal_risk = RiskMetrics(
            max_drawdown_pct=0.05, emergency_halt=False, portfolio_var=0.01
        )
        risk_seq = [nominal_risk] * steps

        trajectory = PhoenixAPipeline.execute_trajectory(
            initial_w, target_w, dt_seq, risk_seq
        )

        prev_w = initial_w
        for step in trajectory:
            curr_w = step.final_authorized_weight
            assert step.governor_decision.action == GovernorAction.ALLOW
            if target_w >= initial_w:
                assert prev_w <= curr_w <= target_w + 1e-9
            else:
                assert target_w - 1e-9 <= curr_w <= prev_w
            prev_w = curr_w

    @given(
        initial_w=st.floats(min_value=W_MIN, max_value=W_MAX),
        target_w=st.floats(min_value=W_MIN, max_value=W_MAX),
    )
    def test_invariant_p3_mid_flight_emergency_halt_isolation(
        self, initial_w: float, target_w: float
    ):
        """
        INVARIANT P3: Mid-Flight Emergency Halt Isolation.
        Injecting an emergency halt midway through a trajectory must force
        weight to W_MIN at the halt step and pass W_MIN into the next step.
        """
        dt_seq = [0.1, 0.1, 0.1]
        risk_step1 = RiskMetrics(max_drawdown_pct=0.01, emergency_halt=False, portfolio_var=0.01)
        risk_step2 = RiskMetrics(max_drawdown_pct=0.01, emergency_halt=True, portfolio_var=0.01)  # Halt
        risk_step3 = RiskMetrics(max_drawdown_pct=0.01, emergency_halt=False, portfolio_var=0.01)

        trajectory = PhoenixAPipeline.execute_trajectory(
            initial_w, target_w, dt_seq, [risk_step1, risk_step2, risk_step3]
        )

        assert trajectory[1].governor_decision.action == GovernorAction.HALT
        assert trajectory[1].final_authorized_weight == W_MIN
        assert trajectory[2].final_authorized_weight >= W_MIN

    @given(
        initial_w=st.floats(min_value=0.60, max_value=1.0),
        invalid_var=st.sampled_from([float("nan"), float("inf"), float("-inf")]),
    )
    def test_invariant_p4_fail_closed_policy_assertion(
        self, initial_w: float, invalid_var: float
    ):
        """
        INVARIANT P4: Explicit Pipeline Policy Assertion on Corrupted Telemetry.
        Verifies that non-finite VaR telemetry forces GovernorAction.THROTTLE
        and clamps authorized weight <= SAFE_THROTTLE_CAP (0.50).
        """
        inp = PhoenixInputPacket(current_weight=initial_w, target_weight=1.0, dt=0.1)
        risk = RiskMetrics(max_drawdown_pct=0.01, emergency_halt=False, portfolio_var=invalid_var)

        result = PhoenixAPipeline.execute_step(inp, risk)

        assert result.governor_decision.action == GovernorAction.THROTTLE
        assert result.final_authorized_weight <= PhoenixARiskGovernor.SAFE_THROTTLE_CAP
        assert result.governor_decision.reason == "VAR_DATA_CORRUPTED_FAIL_CLOSED"

    def test_invariant_p5_throttle_mid_trajectory_deescalation(self):
        """
        INVARIANT P5: Throttle Mid-Trajectory De-escalation & Recovery.
        Verifies that a high VaR spike mid-flight pulls an elevated weight down
        to the throttle ceiling (0.50), overrides nominal monotonicity, and
        resumes normal ramping when risk normalizes.
        """
        initial_w = 0.80
        target_w = 1.00
        dt_seq = [0.1, 0.1, 0.1]

        risk_normal = RiskMetrics(max_drawdown_pct=0.01, emergency_halt=False, portfolio_var=0.01)
        risk_high_var = RiskMetrics(max_drawdown_pct=0.01, emergency_halt=False, portfolio_var=0.08)  # > 0.05

        trajectory = PhoenixAPipeline.execute_trajectory(
            initial_w, target_w, dt_seq, [risk_normal, risk_high_var, risk_normal]
        )

        # Step 1: Normal operation above throttle limit
        assert trajectory[0].governor_decision.action == GovernorAction.ALLOW
        assert trajectory[0].final_authorized_weight > 0.80

        # Step 2: Mid-flight VaR spike triggers Throttle and pulls weight down
        assert trajectory[1].governor_decision.action == GovernorAction.THROTTLE
        assert trajectory[1].final_authorized_weight == PhoenixARiskGovernor.SAFE_THROTTLE_CAP

        # Step 3: Risk normalizes; trajectory resumes upward ramp from throttled baseline (0.50)
        assert trajectory[2].governor_decision.action == GovernorAction.ALLOW
        assert trajectory[2].final_authorized_weight > PhoenixARiskGovernor.SAFE_THROTTLE_CAP


if __name__ == "__main__":
    pytest.main(["-v", __file__])
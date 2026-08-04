"""
Execution Policy State Test Suite
(test_execution_policy_state.py)
"""

import pytest

from execution_policy_state import ExecutionPolicyState, PolicyStateError


def test_new_state_has_zero_count_for_unseen_module():
    state = ExecutionPolicyState()
    assert state.get_count("phoenix_a_core_v1") == 0


def test_increment_returns_new_count():
    state = ExecutionPolicyState()
    assert state.increment("phoenix_a_core_v1") == 1
    assert state.increment("phoenix_a_core_v1") == 2
    assert state.increment("phoenix_a_core_v1") == 3


def test_increment_is_reflected_in_get_count():
    state = ExecutionPolicyState()
    state.increment("phoenix_a_core_v1")
    state.increment("phoenix_a_core_v1")
    assert state.get_count("phoenix_a_core_v1") == 2


def test_independent_modules_have_independent_counts():
    state = ExecutionPolicyState()
    state.increment("phoenix_a_core_v1")
    state.increment("phoenix_a_core_v1")
    state.increment("example_doubler_v1")

    assert state.get_count("phoenix_a_core_v1") == 2
    assert state.get_count("example_doubler_v1") == 1


def test_increment_deterministic_sequence():
    def run():
        state = ExecutionPolicyState()
        for _ in range(5):
            state.increment("phoenix_a_core_v1")
        state.increment("example_doubler_v1")
        return state.get_count("phoenix_a_core_v1"), state.get_count("example_doubler_v1")

    assert run() == run() == (5, 1)


def test_increment_invalid_module_id_rejected():
    state = ExecutionPolicyState()
    with pytest.raises(PolicyStateError):
        state.increment("")
    with pytest.raises(PolicyStateError):
        state.increment("   ")


def test_reset_single_module():
    state = ExecutionPolicyState()
    state.increment("phoenix_a_core_v1")
    state.increment("phoenix_a_core_v1")
    state.increment("example_doubler_v1")

    state.reset("phoenix_a_core_v1")

    assert state.get_count("phoenix_a_core_v1") == 0
    assert state.get_count("example_doubler_v1") == 1


def test_reset_all_clears_every_module():
    state = ExecutionPolicyState()
    state.increment("phoenix_a_core_v1")
    state.increment("example_doubler_v1")

    state.reset_all()

    assert state.get_count("phoenix_a_core_v1") == 0
    assert state.get_count("example_doubler_v1") == 0

"""
Execution Policy Hash Test Suite
(test_execution_policy.py)

Verifies ExecutionPolicy's deterministic hashing: identical rules produce
identical hashes, changed rules change the hash, and None-vs-zero are
correctly distinguished.
"""

import pytest

from execution_policy import ExecutionPolicy, PolicyValidationError


def test_identical_policies_produce_identical_hashes():
    policy_1 = ExecutionPolicy(max_invocations_per_module_lifetime=10)
    policy_2 = ExecutionPolicy(max_invocations_per_module_lifetime=10)

    assert policy_1.policy_hash == policy_2.policy_hash


def test_default_policy_is_deterministic():
    policy_1 = ExecutionPolicy()
    policy_2 = ExecutionPolicy()

    assert policy_1.policy_hash == policy_2.policy_hash


def test_changed_rule_value_changes_hash():
    policy_1 = ExecutionPolicy(max_invocations_per_module_lifetime=10)
    policy_2 = ExecutionPolicy(max_invocations_per_module_lifetime=11)

    assert policy_1.policy_hash != policy_2.policy_hash


def test_none_and_zero_produce_different_hashes():
    """
    None (unlimited) and 0 (never allowed) are semantically opposite
    policies and must never collide in the hash space.
    """
    unlimited = ExecutionPolicy(max_invocations_per_module_lifetime=None)
    forbidden = ExecutionPolicy(max_invocations_per_module_lifetime=0)

    assert unlimited.policy_hash != forbidden.policy_hash


def test_policy_hash_is_well_formed():
    policy = ExecutionPolicy(max_invocations_per_module_lifetime=5)
    assert isinstance(policy.policy_hash, bytes)
    assert len(policy.policy_hash) == 32


def test_negative_invocation_limit_rejected():
    with pytest.raises(PolicyValidationError, match="non-negative"):
        ExecutionPolicy(max_invocations_per_module_lifetime=-1)


def test_non_int_invocation_limit_rejected():
    with pytest.raises(PolicyValidationError, match="must be an int"):
        ExecutionPolicy(max_invocations_per_module_lifetime=3.5)


def test_canonical_bytes_is_stable_across_calls():
    """canonical_bytes() must be a pure function of the policy's own
    state — calling it repeatedly must never produce different output."""
    policy = ExecutionPolicy(max_invocations_per_module_lifetime=7)

    first = policy.canonical_bytes()
    second = policy.canonical_bytes()

    assert first == second


def test_canonical_bytes_includes_format_version():
    """
    The leading format-version byte must be present and stable, so future
    policy field additions can change format without breaking the ability
    to identify which format produced an older stored hash.
    """
    policy = ExecutionPolicy()
    assert policy.canonical_bytes()[0] == 1
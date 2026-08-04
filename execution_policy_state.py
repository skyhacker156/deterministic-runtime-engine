"""
Execution Policy State - Sentinel Framework
(execution_policy_state.py)

Step 2 of the execution authorization layer: mutable runtime counters,
kept entirely separate from ExecutionPolicy's immutable rules.

ExecutionPolicyState has no opinion about what the counters MEAN (that is
ExecutionAuthorizer's job) — it only tracks them correctly and
deterministically.
"""

from dataclasses import dataclass, field
from typing import Dict


class PolicyStateError(Exception):
    """Raised on invalid ExecutionPolicyState operations."""
    pass


@dataclass
class ExecutionPolicyState:
    """
    Mutable, per-module invocation counters. NOT frozen — this is runtime
    state, not a rule. Has no hash of its own by design: unlike
    ExecutionPolicy (whose identity IS its rules, and therefore IS its
    hash), this object's meaning is inherently a moving target.
    """
    invocation_counts: Dict[str, int] = field(default_factory=dict)

    def get_count(self, module_id: str) -> int:
        """Returns the current invocation count for module_id, 0 if never seen."""
        return self.invocation_counts.get(module_id, 0)

    def increment(self, module_id: str) -> int:
        """Increments and returns the new count for module_id."""
        if not isinstance(module_id, str) or not module_id.strip():
            raise PolicyStateError(f"Invalid module_id: {module_id!r}")

        new_count = self.invocation_counts.get(module_id, 0) + 1
        self.invocation_counts[module_id] = new_count
        return new_count

    def reset(self, module_id: str) -> None:
        """Explicitly resets a single module's counter to 0."""
        self.invocation_counts[module_id] = 0

    def reset_all(self) -> None:
        """Explicitly clears all counters."""
        self.invocation_counts.clear()

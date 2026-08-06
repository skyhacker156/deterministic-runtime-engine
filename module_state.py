"""
Module State Enum - Sentinel Framework
(module_state.py)

Extracted from module_lifecycle.py (2026-08-06) -- see
execution_policy_decision_contract.py's own docstring (KNOWN GAP note,
now resolved) for why: that module needs ModuleState as the real type
of ExecutionPolicyDecision.observed_lifecycle_state, but
module_lifecycle.py also contains ModuleLifecycleManager, the live,
mutable lifecycle orchestration class -- and
test_verifier_runtime_isolation.py's FORBIDDEN_MODULES list treats
module_lifecycle as forbidden specifically because of that manager
class (see its own docstring: "the lifecycle manager"). Importing
ModuleState alone from module_lifecycle.py still pulled the whole
module in, since Python has no way to import "just one name" without
executing the entire module it lives in.

This module contains ONLY the enum itself -- zero imports beyond
Python's stdlib enum module. Confirmed on inspection: module_lifecycle.py
never had any forbidden transitive imports of its OWN either -- the
problem was never heaviness, only categorization. module_lifecycle.py
bundled a genuinely pure data type with a genuinely live orchestration
class in one file, the exact same pattern execution_authorizer.py had
with ExecutionPolicyDecision and ExecutionAuthorizer, fixed the same
way.

module_lifecycle.py now imports ModuleState from here rather than
defining it -- ModuleLifecycleManager's behavior is completely
unchanged; only the enum's location moved. Every existing
`from module_lifecycle import ModuleState` import continues to work
unchanged, since module_lifecycle.py re-exports it via its own import
statement. Only a caller that needs ModuleState WITHOUT
module_lifecycle.py's other contents (i.e.,
execution_policy_decision_contract.py, and therefore the pure verifier
chain that depends on it) should import directly from this module
instead.
"""

from enum import Enum, auto


class ModuleState(Enum):
    DISCOVERED = auto()
    VALIDATED = auto()
    REGISTERED = auto()
    ACTIVE = auto()
    FAULTED = auto()
    RETIRED = auto()

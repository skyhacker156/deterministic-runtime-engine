"""
Policy Decision Record - Append-Only Log
(policy_decision_record_log.py)

Direct structural mirror of decision_record_log.py and
execution_audit_log.py, retargeted at PolicyDecisionRecord. Same scope
discipline: many records, one file, in order, corrupt lines rejected
loudly with a locatable line number. Nothing here attempts crash
safety, atomic writes, or concurrent-writer coordination -- those
remain separate, harder questions, same as the other three logs.

Builds on policy_decision_record_persistence.py's already-proven
policy_decision_record_to_json/policy_decision_record_from_json, which
itself already handles the two-layer hash distinction (decision_hash
inside the embedded ExecutionPolicyDecision, entry_hash derived one
layer up) -- this file adds nothing new on that front, only ordering
and multi-record file handling.

sequence_id here matches the same join key already used across
decision_record_log.py and execution_audit_log.py -- reading all three
logs and matching on (sequence_id, generation_id) is how a verifier
correlates a PolicyDecisionRecord with its corresponding DecisionRecord
and ExecutionAuditRecord for the same execution attempt. That
correlation logic does not live here -- this module is purely append/
read for one log, same narrow scope as the other three.
"""

import os
from typing import List

from policy_decision_record_contract import PolicyDecisionRecord
from policy_decision_record_persistence import (
    policy_decision_record_to_json,
    policy_decision_record_from_json,
)


class PolicyDecisionLogCorruptionError(Exception):
    """
    Raised when a line in a policy decision record log fails to parse
    or reconstruct as a valid PolicyDecisionRecord. Carries the
    1-indexed line number so the specific corrupted entry can be
    located directly.
    """
    pass


def append_policy_decision_record(path: str, record: PolicyDecisionRecord) -> None:
    """
    Appends a single PolicyDecisionRecord to the log at `path` as one
    JSON line. True append via "a" mode -- never reads or rewrites any
    existing content.
    """
    line = policy_decision_record_to_json(record)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_all_policy_decision_records(path: str) -> List[PolicyDecisionRecord]:
    """
    Reads every PolicyDecisionRecord from the log at `path`, in append
    order. Raises FileNotFoundError if the path doesn't exist (standard
    open() behavior). Blank lines are skipped. Any non-blank line that
    fails to parse or reconstruct raises PolicyDecisionLogCorruptionError
    immediately, naming the 1-indexed line number -- reading stops at
    the first corruption rather than silently returning a partial list.
    """
    records: List[PolicyDecisionRecord] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(policy_decision_record_from_json(line))
            except Exception as e:
                raise PolicyDecisionLogCorruptionError(
                    f"Line {line_number} of '{path}' failed to parse as a valid "
                    f"PolicyDecisionRecord: {e}"
                ) from e
    return records


def log_exists(path: str) -> bool:
    """Distinguishes 'no log yet' from 'log exists but is empty'."""
    return os.path.isfile(path)

"""
Decision Record - Append-Only Log
(decision_record_log.py)

Direct structural mirror of module_registration_audit_log.py, retargeted
at DecisionRecord. Same scope discipline: many records, one file, in
order, corrupt lines rejected loudly with a locatable line number.
Nothing here attempts crash safety, atomic writes, or concurrent-writer
coordination -- those remain separate, harder questions.

Builds on decision_record_persistence.py's already-proven
decision_record_to_json/decision_record_from_json, which itself already
handles the two-hash distinction (decision_hash opaque, record_hash
derived) -- this file adds nothing new on that front, only ordering and
multi-record file handling.
"""

import os
from typing import List

from decision_record_contract import DecisionRecord
from decision_record_persistence import decision_record_to_json, decision_record_from_json


class DecisionLogCorruptionError(Exception):
    """
    Raised when a line in a decision record log fails to parse or
    reconstruct as a valid DecisionRecord. Carries the 1-indexed line
    number so the specific corrupted entry can be located directly.
    """
    pass


def append_decision_record(path: str, record: DecisionRecord) -> None:
    """
    Appends a single DecisionRecord to the log at `path` as one JSON
    line. True append via "a" mode -- never reads or rewrites any
    existing content.
    """
    line = decision_record_to_json(record)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_all_decision_records(path: str) -> List[DecisionRecord]:
    """
    Reads every DecisionRecord from the log at `path`, in append order.
    Raises FileNotFoundError if the path doesn't exist (standard open()
    behavior). Blank lines are skipped. Any non-blank line that fails
    to parse or reconstruct raises DecisionLogCorruptionError
    immediately, naming the 1-indexed line number -- reading stops at
    the first corruption rather than silently returning a partial list.
    """
    records: List[DecisionRecord] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(decision_record_from_json(line))
            except Exception as e:
                raise DecisionLogCorruptionError(
                    f"Line {line_number} of '{path}' failed to parse as a valid "
                    f"DecisionRecord: {e}"
                ) from e
    return records


def log_exists(path: str) -> bool:
    """Distinguishes 'no log yet' from 'log exists but is empty'."""
    return os.path.isfile(path)

"""
Execution Audit Record - Append-Only Log
(execution_audit_log.py)

Direct structural mirror of module_registration_audit_log.py and
decision_record_log.py, retargeted at ExecutionAuditRecord. Same scope
discipline: many records, one file, in order, corrupt lines rejected
loudly with a locatable line number. No crash safety, no atomic writes,
no concurrent-writer coordination.

Builds on execution_audit_persistence.py's already-proven
audit_record_to_json/audit_record_from_json, which already handles
ExecutionAuditRecord's three opaque hashes plus the derived audit_hash
and the success/error_message consistency rule. This file adds nothing
new there, only ordering and multi-record file handling.
"""

import os
from typing import List

from execution_audit_contract import ExecutionAuditRecord
from execution_audit_persistence import audit_record_to_json, audit_record_from_json


class AuditLogCorruptionError(Exception):
    """
    Raised when a line in an execution audit log fails to parse or
    reconstruct as a valid ExecutionAuditRecord. Carries the 1-indexed
    line number so the specific corrupted entry can be located directly.
    """
    pass


def append_audit_record(path: str, record: ExecutionAuditRecord) -> None:
    """
    Appends a single ExecutionAuditRecord to the log at `path` as one
    JSON line. True append via "a" mode -- never reads or rewrites any
    existing content.
    """
    line = audit_record_to_json(record)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_all_audit_records(path: str) -> List[ExecutionAuditRecord]:
    """
    Reads every ExecutionAuditRecord from the log at `path`, in append
    order. Raises FileNotFoundError if the path doesn't exist. Blank
    lines are skipped. Any non-blank line that fails to parse or
    reconstruct raises AuditLogCorruptionError immediately, naming the
    1-indexed line number.
    """
    records: List[ExecutionAuditRecord] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(audit_record_from_json(line))
            except Exception as e:
                raise AuditLogCorruptionError(
                    f"Line {line_number} of '{path}' failed to parse as a valid "
                    f"ExecutionAuditRecord: {e}"
                ) from e
    return records


def log_exists(path: str) -> bool:
    """Distinguishes 'no log yet' from 'log exists but is empty'."""
    return os.path.isfile(path)

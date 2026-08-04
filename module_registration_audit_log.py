"""
Module Registration Audit - Append-Only Log
(module_registration_audit_log.py)

Builds directly on module_registration_audit_persistence.py's already-
proven record_to_json/record_from_json -- this file adds exactly one
new capability: many records, one file, in order. Nothing here attempts
crash safety, atomic writes, concurrent-writer coordination, or
corruption recovery. Those are separate, harder questions; this answers
only "if I append N records sequentially, do I read back the same N
records in the same order with every hash intact."

Format: JSON Lines (one record_to_json() output per line). Chosen over
a single JSON array specifically because it supports true append --
writing record N+1 never requires re-reading or re-writing records
1..N, which a JSON array would.

Corruption philosophy matches the rest of this codebase (see
test_malformed_json_raises across the three persistence test files):
a corrupt line is REJECTED with enough information to locate it, never
silently skipped and never guessed-around. A log with one bad line
fails loudly on read, in full, rather than silently returning a
partial or reinterpreted history.
"""

import os
from typing import List

from module_registration_audit import ModuleRegistrationAttemptRecord
from module_registration_audit_persistence import record_to_json, record_from_json


class RegistrationLogCorruptionError(Exception):
    """
    Raised when a line in a registration attempt log fails to parse or
    reconstruct as a valid ModuleRegistrationAttemptRecord. Carries the
    1-indexed line number so the specific corrupted entry can be
    located without re-scanning the whole file by hand.
    """
    pass


def append_record(path: str, record: ModuleRegistrationAttemptRecord) -> None:
    """
    Appends a single record to the log at `path` as one JSON line.
    Creates the file (and, if needed, does NOT create parent
    directories -- that's the caller's responsibility) if it doesn't
    already exist. Uses "a" mode, so this never reads or rewrites any
    existing content in the file -- true append, not read-modify-write.
    """
    line = record_to_json(record)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_all_records(path: str) -> List[ModuleRegistrationAttemptRecord]:
    """
    Reads every record from the log at `path`, in the order they were
    appended. Raises FileNotFoundError if the path doesn't exist at
    all (standard open() behavior -- not treated specially, since "no
    log file yet" and "log file that should exist but doesn't" are
    different situations the caller needs to be able to tell apart).

    Blank lines are skipped (a trailing newline at end-of-file does not
    produce a phantom empty record). Any non-blank line that fails to
    parse or reconstruct raises RegistrationLogCorruptionError
    immediately, identifying the 1-indexed line number -- reading stops
    at the first corruption rather than returning a partial list that
    silently omits the bad entry and everything after it.
    """
    records: List[ModuleRegistrationAttemptRecord] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(record_from_json(line))
            except Exception as e:
                raise RegistrationLogCorruptionError(
                    f"Line {line_number} of '{path}' failed to parse as a valid "
                    f"ModuleRegistrationAttemptRecord: {e}"
                ) from e
    return records


def log_exists(path: str) -> bool:
    """Convenience check so callers can distinguish 'no log yet' from
    'log exists but is empty' without catching FileNotFoundError."""
    return os.path.isfile(path)

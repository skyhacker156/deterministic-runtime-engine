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

v2 (2026-08-06): implements Option A from
VERIFICATION_INTEGRATION_CONTRACT.md. read_all_decision_records()'s
signature, return type, exception type, and stop-on-first-failure
behavior are ALL unchanged -- the only change is that the message
raised on a parse failure now includes classification detail (from
historical_schema_recognition.py) distinguishing "this is a recognized
older schema, not corruption" from "this genuinely doesn't parse."
Uses classify_decision_record_payload(), never
historical_verification.py's verify_decision_record_line() -- by the
time this code runs, real construction has already been attempted (by
decision_record_from_json() above) and has already failed, so
re-verifying would be redundant; only recognition adds new information
at this point. See VERIFICATION_INTEGRATION_CONTRACT.md for the full
algorithm and the reasoning behind every choice here.
"""

import json
import os
from typing import List

from decision_record_contract import DecisionRecord
from decision_record_persistence import decision_record_to_json, decision_record_from_json
from historical_schema_recognition import classify_decision_record_payload


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

    As of v2, the raised message ALSO includes classification detail
    when the failing line can be classified: recognized as the known
    pre-generation_id historical schema, or genuinely unrecognized. A
    line that isn't valid JSON at all (no dict to classify) gets no
    such detail appended -- the message is then identical to before
    this change. See VERIFICATION_INTEGRATION_CONTRACT.md.
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
                classification_note = ""
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        classification = classify_decision_record_payload(payload)
                        classification_note = " " + classification.explanation()
                except Exception:
                    pass  # line isn't valid JSON at all -- nothing to classify
                raise DecisionLogCorruptionError(
                    f"Line {line_number} of '{path}' failed to parse as a valid "
                    f"DecisionRecord: {e}.{classification_note}"
                ) from e
    return records


def log_exists(path: str) -> bool:
    """Distinguishes 'no log yet' from 'log exists but is empty'."""
    return os.path.isfile(path)

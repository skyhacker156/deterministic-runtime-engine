"""
Cold Boot Reconstruction - Tests
(test_cold_boot_reconstruction.py)

Every test in this file maps to exactly one clause of
COLD_BOOT_RECONSTRUCTION_CONTRACT.md. Tests are grouped and labeled by
which SHALL or SHALL NOT item they prove.
"""

import hashlib
import inspect
import os
import tempfile

import pytest

from module_registration_audit import ModuleRegistrationAttemptRecord
from module_registration_audit_log import append_record as append_registration_record
from decision_record_contract import DecisionRecord
from decision_record_log import append_decision_record
from execution_audit_contract import ExecutionAuditRecord
from execution_audit_log import append_audit_record
from cold_boot_reconstruction import reconstruct_cold_boot, ColdBootReconstructionResult


def _hash32(seed: bytes) -> bytes:
    return hashlib.sha256(seed).digest()


# Fixed placeholder generation_id for records built directly in this
# file. These tests are about cold-boot reconstruction logic (loading,
# ordering, provenance cross-referencing), not generation identity, so
# a single fixed constant shared across every record in every test is
# fine here.
_GEN_ID = b"\x22" * 16


@pytest.fixture
def three_log_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield {
            "registration": os.path.join(tmpdir, "registration.jsonl"),
            "decision": os.path.join(tmpdir, "decision.jsonl"),
            "audit": os.path.join(tmpdir, "audit.jsonl"),
        }


def _build_clean_scenario(paths):
    """
    A coherent, valid three-log scenario: one successful registration,
    two allowed+executed frames, one denied frame with no audit record.
    """
    append_registration_record(
        paths["registration"],
        ModuleRegistrationAttemptRecord(
            module_id="phoenix_a_core_v1", attempted_at_ns=1000,
            success=True, reason=None,
        ),
    )
    append_decision_record(
        paths["decision"],
        DecisionRecord(sequence_id=1, module_id="phoenix_a_core_v1",
                        allowed=True, decision_hash=_hash32(b"d1"),
                        generation_id=_GEN_ID),
    )
    append_audit_record(
        paths["audit"],
        ExecutionAuditRecord(
            sequence_id=1, input_hash=_hash32(b"in1"),
            prior_state_hash=_hash32(b"p1"), output_hash=_hash32(b"o1"),
            module_id="phoenix_a_core_v1", success=True,
            frame_timestamp_ns=1000, error_message=None,
            generation_id=_GEN_ID,
        ),
    )
    append_decision_record(
        paths["decision"],
        DecisionRecord(sequence_id=2, module_id="phoenix_a_core_v1",
                        allowed=True, decision_hash=_hash32(b"d2"),
                        generation_id=_GEN_ID),
    )
    append_audit_record(
        paths["audit"],
        ExecutionAuditRecord(
            sequence_id=2, input_hash=_hash32(b"in2"),
            prior_state_hash=_hash32(b"p2"), output_hash=_hash32(b"o2"),
            module_id="phoenix_a_core_v1", success=True,
            frame_timestamp_ns=2000, error_message=None,
            generation_id=_GEN_ID,
        ),
    )
    append_decision_record(
        paths["decision"],
        DecisionRecord(sequence_id=3, module_id="phoenix_a_core_v1",
                        allowed=False, decision_hash=_hash32(b"d3"),
                        generation_id=_GEN_ID),
    )


# ---------------------------------------------------------------------
# SHALL 1: registration history
# ---------------------------------------------------------------------

def test_shall_1_registration_history_reconstructed(three_log_paths):
    _build_clean_scenario(three_log_paths)

    result = reconstruct_cold_boot(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert len(result.registration_history) == 1
    assert isinstance(result.registration_history[0], ModuleRegistrationAttemptRecord)
    assert result.registration_history[0].module_id == "phoenix_a_core_v1"
    assert result.registration_history[0].success is True


# ---------------------------------------------------------------------
# SHALL 2: authorization history
# ---------------------------------------------------------------------

def test_shall_2_authorization_history_reconstructed(three_log_paths):
    _build_clean_scenario(three_log_paths)

    result = reconstruct_cold_boot(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert len(result.authorization_history) == 3
    assert all(isinstance(d, DecisionRecord) for d in result.authorization_history)
    assert [d.allowed for d in result.authorization_history] == [True, True, False]


# ---------------------------------------------------------------------
# SHALL 3: execution ordering, reconstructed AND verified
# ---------------------------------------------------------------------

def test_shall_3_ordering_verified_not_just_loaded(three_log_paths):
    """
    Deliberately writes decisions out of order for the same module and
    confirms reconstruction still LOADS them (per SHALL 1/2 -- loading
    doesn't refuse malformed-but-parseable data) but the causal_report
    correctly flags the ordering violation -- proving SHALL 3 is a
    verification, not just a passive read.
    """
    append_registration_record(
        three_log_paths["registration"],
        ModuleRegistrationAttemptRecord(
            module_id="phoenix_a_core_v1", attempted_at_ns=1000,
            success=True, reason=None,
        ),
    )
    append_decision_record(
        three_log_paths["decision"],
        DecisionRecord(sequence_id=5, module_id="phoenix_a_core_v1",
                        allowed=True, decision_hash=_hash32(b"d5"),
                        generation_id=_GEN_ID),
    )
    append_decision_record(
        three_log_paths["decision"],
        DecisionRecord(sequence_id=2, module_id="phoenix_a_core_v1",
                        allowed=True, decision_hash=_hash32(b"d2"),
                        generation_id=_GEN_ID),
    )
    open(three_log_paths["audit"], "w", encoding="utf-8").close()

    result = reconstruct_cold_boot(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert len(result.authorization_history) == 2  # loaded despite the violation
    assert result.reconstruction_valid is False
    assert any("out of causal order" in f for f in result.causal_report.failures)


# ---------------------------------------------------------------------
# SHALL 4: the two specific causal relationships
# ---------------------------------------------------------------------

def test_shall_4_decision_ancestry_and_registration_provenance_checked(three_log_paths):
    """
    Uses a ghost module_id (no registration record) with an allowed
    decision and matching audit record -- valid ancestry, but fails
    the registration-provenance check. Confirms reconstruction surfaces
    BOTH the raw records and the specific causal failure.
    """
    open(three_log_paths["registration"], "w", encoding="utf-8").close()
    append_decision_record(
        three_log_paths["decision"],
        DecisionRecord(sequence_id=1, module_id="ghost_module",
                        allowed=True, decision_hash=_hash32(b"d"),
                        generation_id=_GEN_ID),
    )
    append_audit_record(
        three_log_paths["audit"],
        ExecutionAuditRecord(
            sequence_id=1, input_hash=_hash32(b"in"),
            prior_state_hash=_hash32(b"p"), output_hash=_hash32(b"o"),
            module_id="ghost_module", success=True,
            frame_timestamp_ns=1000, error_message=None,
            generation_id=_GEN_ID,
        ),
    )

    result = reconstruct_cold_boot(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert len(result.execution_history) == 1  # record still reconstructed
    assert result.reconstruction_valid is False
    assert any("no successful registration attempt" in f for f in result.causal_report.failures)


# ---------------------------------------------------------------------
# SHALL 5: hash consistency via actual record classes (implementation
# constraint), NOT available for state_hash
# ---------------------------------------------------------------------

def test_shall_5_records_are_real_class_instances_not_dicts(three_log_paths):
    _build_clean_scenario(three_log_paths)

    result = reconstruct_cold_boot(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    # Every returned record is a genuine instance of its record class,
    # meaning its hash was derived by that class's own __post_init__,
    # not by any logic in cold_boot_reconstruction.py itself.
    for r in result.registration_history:
        assert isinstance(r, ModuleRegistrationAttemptRecord)
        assert len(r.attempt_hash) == 32
    for d in result.authorization_history:
        assert isinstance(d, DecisionRecord)
        assert len(d.record_hash) == 32
    for a in result.execution_history:
        assert isinstance(a, ExecutionAuditRecord)
        assert len(a.audit_hash) == 32


def test_shall_5_module_never_reimplements_hash_computation():
    """
    Structural proof of the contract's implementation constraint on
    SHALL 5: cold_boot_reconstruction.py must never compute a hash
    itself -- only ever construct real record classes and let their
    own __post_init__ derive hashes.

    Uses AST-based import inspection rather than a raw source-text
    substring search -- a substring search would false-positive on
    this module's own docstrings, which explicitly (and correctly)
    describe hashlib as NOT imported, and would therefore contain the
    word "hashlib" in prose despite there being no actual import.
    Checking the parsed import statements directly avoids that trap.
    """
    import ast
    import cold_boot_reconstruction

    tree = ast.parse(inspect.getsource(cold_boot_reconstruction))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)

    assert "hashlib" not in imported_names, (
        f"cold_boot_reconstruction.py actually imports hashlib -- this "
        f"violates SHALL 5's implementation constraint. Imports found: "
        f"{imported_names}"
    )


def test_shall_5_state_hash_is_unavailable_kernel_state_never_imported():
    """
    Confirms the SHALL 5 carve-out: KernelStateEnvelope / state_hash
    consistency is NOT claimed anywhere in this module, because Gap 1
    remains open. Uses the same AST-based import check as the hashlib
    test above, for the same reason -- this module's docstrings
    correctly mention execution_kernel_state and KernelStateEnvelope
    BY NAME while explaining they are not imported, so a raw text
    search would false-positive on its own explanatory prose.
    """
    import ast
    import cold_boot_reconstruction

    tree = ast.parse(inspect.getsource(cold_boot_reconstruction))
    imported_names = set()
    imported_members = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)
            imported_members.update(alias.name for alias in node.names)

    assert "execution_kernel_state" not in imported_names, (
        f"cold_boot_reconstruction.py actually imports execution_kernel_state -- "
        f"this claims a capability Gap 1 says isn't available yet. "
        f"Imports found: {imported_names}"
    )
    assert "KernelStateEnvelope" not in imported_members
    assert "KernelStateMachine" not in imported_members


# ---------------------------------------------------------------------
# SHALL NOT 1, 2, 3: no field for RAM/scheduler/queue state, reset
# generation, or policy counters
# ---------------------------------------------------------------------

def test_shall_not_result_has_no_forbidden_fields():
    from dataclasses import fields

    result_field_names = {f.name for f in fields(ColdBootReconstructionResult)}

    forbidden_substrings = [
        "ram", "scheduler", "queue",           # SHALL NOT 1
        "reset_generation", "epoch", "boot_id", # SHALL NOT 2
        "invocation_count", "policy_state",     # SHALL NOT 3
        "state_hash", "kernel",                 # SHALL 5 carve-out
    ]

    for field_name in result_field_names:
        lowered = field_name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, (
                f"ColdBootReconstructionResult has field '{field_name}', which "
                f"matches forbidden substring '{forbidden}' -- this would imply "
                f"a claim the contract's SHALL NOT items explicitly disallow."
            )


# ---------------------------------------------------------------------
# SHALL NOT 4: no claim of original-runtime correctness
# ---------------------------------------------------------------------

def test_reconstruction_valid_docstring_does_not_overclaim():
    """
    Documentation-level check: reconstruction_valid's own docstring
    must explicitly disclaim runtime-correctness, per SHALL NOT 4.
    Brittle by nature (checks doc text), but catches the specific
    failure mode of someone later strengthening the property's
    apparent meaning without updating what it actually proves.

    Whitespace (including line-wrap newlines within a sentence) is
    normalized to single spaces before comparison -- the original
    version of this test compared against raw docstring text and
    failed on a line-wrap artifact ("behaved\\ncorrectly" instead of
    "behaved correctly" on one line), which was a test bug, not a
    missing disclaimer.
    """
    docstring = " ".join(ColdBootReconstructionResult.__doc__.split())
    assert "does NOT mean" in docstring
    assert "behaved correctly" in docstring


# ---------------------------------------------------------------------
# Full happy-path integration
# ---------------------------------------------------------------------

def test_full_clean_reconstruction_is_valid(three_log_paths):
    _build_clean_scenario(three_log_paths)

    result = reconstruct_cold_boot(
        three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
    )

    assert result.reconstruction_valid is True
    assert result.causal_report.failures == []
    assert len(result.registration_history) == 1
    assert len(result.authorization_history) == 3
    assert len(result.execution_history) == 2

# ---------------------------------------------------------------------
# Snapshot identity: returned and verified histories cannot diverge
# ---------------------------------------------------------------------

def test_snapshot_identity_returned_and_verified_histories_cannot_diverge(
    monkeypatch, three_log_paths
):
    """
    Regression test for the Orphan/identity-of-evidence finding
    (2026-08-09): before the fix, reconstruct_cold_boot() read each log
    twice -- once directly, once inside verify_causal_history()'s own
    independent re-read -- with nothing connecting the two reads. A
    caller could receive a returned history of N records while
    causal_report reflected verification of a DIFFERENT record set,
    with reconstruction_valid=True and zero failures. Confirmed
    concretely before this fix: 3 decision records returned, only 2
    verified, reconstruction_valid reported True regardless.

    This test confirms the fix structurally, not just behaviorally:
    monkeypatching causal_history_verifier's own read_all_* functions
    to return data DIFFERENT from what reconstruct_cold_boot() itself
    reads has NO EFFECT on the result, because
    verify_causal_history_from_records() -- what reconstruct_cold_boot()
    now calls -- never invokes those functions at all. There is no
    second read left to divert.
    """
    import causal_history_verifier as chv

    append_registration_record(
        three_log_paths["registration"],
        ModuleRegistrationAttemptRecord(
            module_id="phoenix_a_core_v1", attempted_at_ns=1000,
            success=True, reason=None,
        ),
    )
    append_decision_record(
        three_log_paths["decision"],
        DecisionRecord(sequence_id=1, module_id="phoenix_a_core_v1",
                        allowed=False, decision_hash=_hash32(b"d1"),
                        generation_id=_GEN_ID),
    )
    # three_log_paths only yields path strings -- it does not create the
    # files. registration/decision were created above via append ("a"
    # mode). audit is deliberately left with zero records for this test,
    # but the file must still exist for _read_audit_log() to open it.
    open(three_log_paths["audit"], "w").close()

    # Attempt to divert the (now-nonexistent) second read to return
    # empty data, genuinely different from what reconstruct_cold_boot()
    # itself read above.
    monkeypatch.setattr(chv, "read_all_registration_records", lambda path: [])
    monkeypatch.setattr(chv, "read_all_decision_records", lambda path: [])
    monkeypatch.setattr(chv, "read_all_audit_records", lambda path: [])

    result = reconstruct_cold_boot(
        three_log_paths["registration"],
        three_log_paths["decision"],
        three_log_paths["audit"],
    )

    # If a second, divertable read still existed, these counts would
    # show 0 (from the monkeypatched functions) while the returned
    # histories still showed 1 each -- a silent, undetected mismatch.
    # With the fix, the monkeypatch has no effect at all: the counts
    # must match the real, returned histories exactly, every time.
    assert len(result.registration_history) == 1
    assert result.causal_report.registration_record_count == 1
    assert len(result.authorization_history) == 1
    assert result.causal_report.decision_record_count == 1
    assert len(result.execution_history) == 0
    assert result.causal_report.audit_record_count == 0
# ---------------------------------------------------------------------
# Missing logs propagate as real errors
# ---------------------------------------------------------------------

def test_missing_log_raises_file_not_found(three_log_paths):
    with pytest.raises(FileNotFoundError):
        reconstruct_cold_boot(
            three_log_paths["registration"], three_log_paths["decision"], three_log_paths["audit"]
        )

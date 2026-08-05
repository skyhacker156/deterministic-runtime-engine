"""
Causal History Verifier - Runtime Isolation Boundary Test
(test_verifier_runtime_isolation.py)

Proves, by actual runtime behavior rather than static text inspection,
that causal_history_verifier.py has zero dependency on any live-runtime
module. A static import scan (grep for forbidden module names in
source text) only proves the SOURCE TEXT doesn't mention them -- it
would not catch a local/lazy import buried inside a function body, a
transitive import pulled in by something that itself imports the
runtime, or a forbidden module imported under an alias. Only running
the verifier in a subprocess and inspecting what actually got loaded
into sys.modules proves the real property this boundary exists for.

Per causal_history_verifier.py's own docstring: "It is NOT a recovery
system -- it does not reconstruct live runtime state, does not resume
execution, and does not touch ExecutionModuleRegistry or
DeterministicExecutionEngine." This test is what makes that sentence a
tested claim instead of an assertion trusted on the strength of the
docstring alone.

FORBIDDEN MODULES: every module that constitutes "live runtime state"
in this codebase -- the execution engine, the kernel state machine, the
module registry, the lifecycle manager, and the authorizer. If any of
these appear in sys.modules after running the verifier end-to-end in a
clean subprocess, the isolation boundary has been violated somewhere,
even if the violation isn't visible by reading causal_history_verifier.py
directly (e.g. it could be introduced transitively through a future
change to module_registration_audit_log.py, decision_record_log.py, or
execution_audit_log.py -- this test would catch that too, since it
checks actual runtime behavior, not just causal_history_verifier.py's
own import list).
"""

import subprocess
import sys
import textwrap


FORBIDDEN_MODULES = [
    "deterministic_execution_engine",
    "execution_kernel_state",
    "execution_module_registry",
    "module_lifecycle",
    "execution_authorizer",
    "execution_policy",
    "execution_policy_state",
]


def _run_isolated_verification_script(repo_root: str) -> subprocess.CompletedProcess:
    """
    Builds and runs a small script, in a fresh subprocess, that:
      1. Creates a tiny set of real log files (registration, decision,
         audit) using the actual record types and append functions --
         not mocks, so this exercises the real serialization path too.
      2. Imports and calls verify_causal_history() against those files.
      3. Prints, as its only output, the sorted list of FORBIDDEN_MODULES
         names that ended up in sys.modules after step 2.

    A fresh subprocess is essential here -- running this in-process
    would inherit whatever this test file's own test session has
    already imported (e.g. via pytest's collection of OTHER test files
    in the same run, several of which legitimately DO import the
    runtime modules), which would produce false positives having
    nothing to do with causal_history_verifier.py's own behavior.

    generation_id: the inline DecisionRecord/ExecutionAuditRecord
    construction below uses a fixed 16-byte placeholder (gen_id) --
    this script tests import isolation, not generation identity, so a
    single fixed value is fine. Deliberately built with a plain byte
    literal rather than reusing h(), since h() produces a 32-byte
    SHA-256 digest and generation_id must be exactly 16 bytes.
    """
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {repo_root!r})

        import tempfile, os, hashlib

        from module_registration_audit import ModuleRegistrationAttemptRecord
        from module_registration_audit_log import append_record as append_reg
        from decision_record_contract import DecisionRecord
        from decision_record_log import append_decision_record
        from execution_audit_contract import ExecutionAuditRecord
        from execution_audit_log import append_audit_record

        def h(seed):
            return hashlib.sha256(seed).digest()

        gen_id = b"\\x99" * 16

        with tempfile.TemporaryDirectory() as tmpdir:
            reg_path = os.path.join(tmpdir, "registration.jsonl")
            dec_path = os.path.join(tmpdir, "decision.jsonl")
            aud_path = os.path.join(tmpdir, "audit.jsonl")

            append_reg(reg_path, ModuleRegistrationAttemptRecord(
                module_id="phoenix_a_core_v1", attempted_at_ns=1000,
                success=True, reason=None,
            ))
            append_decision_record(dec_path, DecisionRecord(
                sequence_id=1, module_id="phoenix_a_core_v1",
                allowed=True, decision_hash=h(b"d"),
                generation_id=gen_id,
            ))
            append_audit_record(aud_path, ExecutionAuditRecord(
                sequence_id=1, input_hash=h(b"in"),
                prior_state_hash=h(b"prior"), output_hash=h(b"out"),
                module_id="phoenix_a_core_v1", success=True,
                frame_timestamp_ns=1000, error_message=None,
                generation_id=gen_id,
            ))

            from causal_history_verifier import verify_causal_history
            report = verify_causal_history(reg_path, dec_path, aud_path)
            assert report.passed, f"Unexpected verification failure: {{report.failures}}"

        forbidden = {FORBIDDEN_MODULES!r}
        loaded_forbidden = sorted(name for name in forbidden if name in sys.modules)
        print("LOADED_FORBIDDEN:" + ",".join(loaded_forbidden))
        print("REPORT_PASSED:" + str(report.passed))
    """)

    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_verifier_never_imports_runtime_modules_in_a_fresh_process(pytestconfig):
    """
    The actual test: run the verifier end-to-end in a clean subprocess
    that has NEVER imported anything from this test session, and
    confirm none of FORBIDDEN_MODULES ended up loaded.
    """
    repo_root = str(pytestconfig.rootpath)

    result = _run_isolated_verification_script(repo_root)

    assert result.returncode == 0, (
        f"Isolated verification subprocess failed.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    stdout_lines = result.stdout.strip().splitlines()
    loaded_line = next((l for l in stdout_lines if l.startswith("LOADED_FORBIDDEN:")), None)
    passed_line = next((l for l in stdout_lines if l.startswith("REPORT_PASSED:")), None)

    assert loaded_line is not None, f"Subprocess did not report loaded modules. stdout: {result.stdout}"
    assert passed_line is not None, f"Subprocess did not report verification result. stdout: {result.stdout}"

    loaded_forbidden = loaded_line.split(":", 1)[1]
    assert loaded_forbidden == "", (
        f"Verifier subprocess loaded forbidden runtime module(s): {loaded_forbidden!r}. "
        f"The verifier is supposed to depend only on the three log-reading modules and "
        f"the record/contract classes -- if this fails, something now creates a real "
        f"dependency on live runtime state, even if causal_history_verifier.py's own "
        f"source doesn't obviously show it."
    )

    assert passed_line.split(":", 1)[1] == "True", (
        "Verification itself failed inside the isolated subprocess -- this test needs "
        "the verification to succeed on clean data as a precondition for the isolation "
        "check to mean anything."
    )


def test_forbidden_module_list_is_not_accidentally_empty():
    """
    Guards against a trivial way this test file could silently stop
    testing anything: if FORBIDDEN_MODULES were ever emptied out, the
    isolation test above would vacuously pass no matter what the
    verifier actually imports.
    """
    assert len(FORBIDDEN_MODULES) >= 5

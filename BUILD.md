# BUILD.md

Instructions to get from a fresh `git clone` to a passing `pytest -v` run.

**Confirmed working as of:** a clean clone into a sibling directory
(`phoenix-clean-test`), Rust build run manually, full suite at 327/327,
zero regressions, zero hidden local state found. See
`PHOENIX_VERIFICATION_STATE.md` for the full record of that result.

---

## Prerequisites

- **Python 3.14** (or whatever version this environment was last
  confirmed against — see the `pytest -v` header line, e.g.
  `platform win32 -- Python 3.14.0`).
- **A Rust toolchain** (`cargo`, `rustc`) — required to build
  `phoenix_core_rs`, the Rust component `test_differential_parity.py`
  checks for bit-exact parity against the Python implementation. If
  you don't have Rust installed: https://rustup.rs

## Python dependencies

**Known, from test file imports across the suite:**
- `pytest`
- `hypothesis`
- `numpy`

**Not yet pinned to exact versions anywhere in this repo.** There is
currently no `requirements.txt` or `pyproject.toml` committed. Until
one exists, if you hit an `ImportError` on a fresh environment, install
the three packages above via pip and re-run.

**TODO before this file can be considered complete:** run
`pip freeze > requirements.txt` in a known-working environment (e.g.
the one that produced the 327/327 clean-clone result) and commit that
file, so dependency versions are pinned rather than implicit. This is
a known, named gap — see `PHOENIX_VERIFICATION_STATE.md`'s "Explicitly
Out of Scope" section once updated.

## Build steps

1. Clone the repository:
   ```
   git clone https://github.com/skyhacker156/deterministic-runtime-engine.git
   cd deterministic-runtime-engine
   ```

2. Build the Rust component (required — without this step,
   `test_differential_parity.py` fails at COLLECTION time with
   `FileNotFoundError: Could not find module '...phoenix_core_rs.dll'`,
   which blocks pytest from collecting ANY test, not just that file):
   ```
   cd phoenix_core_rs
   cargo build --release
   cd ..
   ```
   This produces `phoenix_core_rs/target/release/phoenix_core_rs.dll`
   (Windows) or the equivalent `.so`/`.dylib` on other platforms. This
   build artifact is intentionally NOT committed to git (build outputs
   shouldn't be version-controlled) — it must be produced locally by
   this step, every time you work from a fresh clone.

3. Install Python dependencies (see note above on the missing
   `requirements.txt`):
   ```
   pip install pytest hypothesis numpy
   ```

4. Run the full test suite:
   ```
   pytest -v
   ```
   Expected result as of the last confirmed clean-clone run: **327
   passed**, 0 failed, 1 warning (a benign hypothesis-plugin warning
   about `.hypothesis` directory collection — not an error).

## If `test_differential_parity.py` fails to collect

This means step 2 (the Rust build) either wasn't run, or failed
silently. Re-run `cargo build --release` from inside `phoenix_core_rs/`
and check its output directly for compile errors before re-running
pytest — the pytest error message alone (`FileNotFoundError`) doesn't
distinguish "never built" from "build failed," so check the cargo
output itself.

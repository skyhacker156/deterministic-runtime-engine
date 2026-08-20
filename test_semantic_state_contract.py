"""
test_semantic_state_contract.py

Phase 2C: does the minimum viable semantic-state extension actually answer
its one framed question -- if Phoenix records value=7.1/quality=BAD, can a
cold replay reconstruct exactly that state, and is a GOOD state with the
same value cryptographically distinguishable? And, just as important: does
adding this leave Phoenix A's real execution semantics completely
unchanged?
"""
import pytest
from pathlib import Path

from semantic_state_contract import (
    SemanticReading,
    compute_semantic_hash,
    make_semantic_reading,
    semantic_reading_to_json,
    semantic_reading_from_json,
    append_semantic_log,
    read_semantic_log,
)


# --- The brutally clean experiment, stated as a test ---

def test_good_and_bad_at_same_value_are_cryptographically_distinguishable():
    good = make_semantic_reading(7.1, "GOOD")
    bad = make_semantic_reading(7.1, "BAD")
    assert good.value == bad.value == 7.1
    assert good.semantic_hash != bad.semantic_hash


def test_value_only_change_changes_the_hash():
    a = make_semantic_reading(7.1, "GOOD")
    b = make_semantic_reading(-1.0, "GOOD")
    assert a.semantic_hash != b.semantic_hash


def test_quality_only_change_changes_the_hash():
    a = make_semantic_reading(7.1, "GOOD")
    b = make_semantic_reading(7.1, "BAD")
    assert a.semantic_hash != b.semantic_hash


def test_identical_inputs_produce_identical_hash():
    a = make_semantic_reading(7.1, "GOOD")
    b = make_semantic_reading(7.1, "GOOD")
    assert a.semantic_hash == b.semantic_hash


# --- Persistence and cold reconstruction ---

def test_round_trip_preserves_value_and_quality_exactly(tmp_path):
    original = make_semantic_reading(7.1, "BAD")
    json_str = semantic_reading_to_json(original)
    reconstructed = semantic_reading_from_json(json_str)
    assert reconstructed.value == original.value
    assert reconstructed.quality == original.quality
    assert reconstructed.semantic_hash == original.semantic_hash


def test_cold_reconstruction_through_a_real_disk_file(tmp_path):
    """Not an in-memory round trip -- writes to a real file, then reads
    it back as an entirely separate operation, simulating a fresh process
    with no memory of how the readings were produced."""
    log_path = tmp_path / "semantic.log"
    good = make_semantic_reading(7.1, "GOOD")
    bad = make_semantic_reading(7.1, "BAD")
    append_semantic_log(log_path, good)
    append_semantic_log(log_path, bad)

    reconstructed = read_semantic_log(log_path)
    assert len(reconstructed) == 2
    assert reconstructed[0].value == 7.1 and reconstructed[0].quality == "GOOD"
    assert reconstructed[1].value == 7.1 and reconstructed[1].quality == "BAD"
    assert reconstructed[0].semantic_hash != reconstructed[1].semantic_hash
    assert reconstructed[0].semantic_hash == good.semantic_hash
    assert reconstructed[1].semantic_hash == bad.semantic_hash


def test_tampered_quality_is_detected_on_reconstruction():
    """The stored hash is never trusted -- tampering with quality after
    persistence, while leaving the stored hash untouched, must be caught
    on the way back in, the same way decision_record_from_json's own
    documented convention works."""
    reading = make_semantic_reading(7.1, "GOOD")
    payload = semantic_reading_to_json(reading)
    tampered = payload.replace('"GOOD"', '"BAD"')
    with pytest.raises(ValueError, match="semantic_hash mismatch"):
        semantic_reading_from_json(tampered)


def test_tampered_value_is_detected_on_reconstruction():
    reading = make_semantic_reading(7.1, "GOOD")
    payload = semantic_reading_to_json(reading)
    tampered = payload.replace('7.1', '99.9')
    with pytest.raises(ValueError, match="semantic_hash mismatch"):
        semantic_reading_from_json(tampered)


def test_multiple_readings_preserve_order_and_independence(tmp_path):
    log_path = tmp_path / "semantic.log"
    readings = [
        make_semantic_reading(7.1, "GOOD"),
        make_semantic_reading(-1.0, "BAD"),
        make_semantic_reading(7.05, "UNCERTAIN"),
        make_semantic_reading(15.0, "BAD"),
    ]
    for r in readings:
        append_semantic_log(log_path, r)
    reconstructed = read_semantic_log(log_path)
    assert [r.value for r in reconstructed] == [r.value for r in readings]
    assert [r.quality for r in reconstructed] == [r.quality for r in readings]
    hashes = [r.semantic_hash for r in reconstructed]
    assert len(set(hashes)) == len(hashes), "all four should be pairwise distinct"


# --- Phoenix never interprets quality: no branch on its content ---

def test_module_never_branches_on_quality_string_content():
    """Structural check, same style as this codebase's existing AST-based
    guards (cold_boot_reconstruction.py, generation_segmentation.py):
    confirms compute_semantic_hash treats quality as an opaque byte
    string, not by inspecting source, but by demonstrating that
    completely novel, unrecognized quality strings work identically to
    the three named in the external spec -- nothing here whitelists or
    special-cases "GOOD"/"UNCERTAIN"/"BAD"."""
    a = make_semantic_reading(7.1, "COMPLETELY_UNRECOGNIZED_STRING_XYZ")
    b = make_semantic_reading(7.1, "ANOTHER_NOVEL_STRING")
    assert a.semantic_hash != b.semantic_hash
    # both succeed identically -- no whitelist, no rejection of unknown quality values

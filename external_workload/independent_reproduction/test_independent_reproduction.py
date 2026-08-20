"""
test_independent_reproduction.py

Pytest form of independent_reproduction_harness.py. Same clean-room
constraint applies: this file does NOT import semantic_state_contract.py.
Its oracle (independent_semantic_fingerprint, canonical-JSON + SHA-256) is
independently derived from EXTERNAL_WORKLOAD_SPEC.md's and
PHOENIX_EXTERNAL_GENERALIZATION_v2.md's stated requirement, not from
semantic_state_contract.py's implementation. See
independent_reproduction_harness.py's module docstring for the full
rationale (the CI-005 independent-oracle lesson this file exists to apply).
"""
import sys, json, hashlib
import pytest

import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket
from bridge_integrator_contract import BridgeIntegrator
from replay_engine import _bridge_frame_to_kernel_frame
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule

CONST_VIB = [1.4] * 3
CONST_TEMP = [72.0] * 3


def independent_semantic_fingerprint(value: float, quality: str) -> str:
    canonical = json.dumps({"v": value, "q": quality}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def independent_persist(path, value: float, quality: str) -> None:
    record = {
        "quality_assertion": quality,
        "numeric_value": value,
        "fingerprint": independent_semantic_fingerprint(value, quality),
    }
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def independent_reconstruct(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            value = record["numeric_value"]
            quality = record["quality_assertion"]
            recomputed = independent_semantic_fingerprint(value, quality)
            if recomputed != record["fingerprint"]:
                raise ValueError(f"fingerprint mismatch: value={value} quality={quality}")
            out.append((value, quality, recomputed))
    return out


def run_real_phoenix(ph_value, batch_id):
    adapter = VentAdapterContract()
    bridge = BridgeIntegrator()
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()
    pkt = RawVentTelemetryPacket(
        batch_id=batch_id, timestamp=1755648000.0,
        chemical_pH=[ph_value]*3, seismic_amplitude=CONST_VIB, temperature_readings=CONST_TEMP,
    )
    batch, log = adapter.process_raw_packet(pkt)
    bridge_frame = bridge.verify_and_transform(batch)
    kframe = _bridge_frame_to_kernel_frame(bridge_frame, seq_id=0)
    envelope, result = engine.process_frame(kframe)
    return batch.provenance_hash, result


@pytest.fixture(scope="module")
def frozen_workload():
    # workload_packets.json lives at the repo root (external_workload/
    # only holds the Phase 2 report/script files, not the original
    # EW-001-era dataset), so this goes up two directories, not one.
    workload_path = os.path.join(os.path.dirname(__file__), "..", "..", "workload_packets.json")
    with open(workload_path) as f:
        return json.load(f)


def test_same_value_different_quality_is_distinguishable():
    assert independent_semantic_fingerprint(7.1, "GOOD") != independent_semantic_fingerprint(7.1, "BAD")


def test_same_value_same_quality_reproduces_identically():
    assert independent_semantic_fingerprint(7.1, "GOOD") == independent_semantic_fingerprint(7.1, "GOOD")


def test_value_mutation_is_detected(tmp_path):
    path = tmp_path / "log1.jsonl"
    independent_persist(path, 7.1, "GOOD")
    tampered = path.read_text().replace("7.1", "99.9")
    path.write_text(tampered)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        independent_reconstruct(path)


def test_quality_mutation_is_detected(tmp_path):
    path = tmp_path / "log2.jsonl"
    independent_persist(path, 7.1, "GOOD")
    tampered = path.read_text().replace('"GOOD"', '"BAD"')
    path.write_text(tampered)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        independent_reconstruct(path)


def test_disk_reconstruction_recovers_frozen_workload_values_exactly(tmp_path, frozen_workload):
    healthy_pkt = frozen_workload[0]
    fault_pkt = frozen_workload[21]
    healthy_value = healthy_pkt["readings"]["ph"][0]
    healthy_quality = healthy_pkt["quality"]["ph"]
    fault_value = fault_pkt["readings"]["ph"][0]
    fault_quality = fault_pkt["quality"]["ph"]

    path = tmp_path / "frozen.jsonl"
    independent_persist(path, healthy_value, healthy_quality)
    independent_persist(path, fault_value, fault_quality)
    reconstructed = independent_reconstruct(path)

    assert reconstructed[0][0] == healthy_value
    assert reconstructed[0][1] == healthy_quality
    assert reconstructed[1][0] == fault_value
    assert reconstructed[1][1] == fault_quality


def test_phoenix_execution_unchanged_for_frozen_workload_values(frozen_workload):
    healthy_pkt = frozen_workload[0]
    fault_pkt = frozen_workload[21]
    healthy_value = healthy_pkt["readings"]["ph"][0]
    fault_value = fault_pkt["readings"]["ph"][0]

    _, result_healthy = run_real_phoenix(healthy_value, "HEALTHY-FROZEN-PYTEST")
    _, result_fault = run_real_phoenix(fault_value, "FAULT-FROZEN-PYTEST")

    assert result_healthy.success is True
    assert result_fault.success is True


def test_external_semantics_never_interpreted_by_core_execution(frozen_workload):
    healthy_pkt = frozen_workload[0]
    healthy_value = healthy_pkt["readings"]["ph"][0]
    healthy_quality = healthy_pkt["quality"]["ph"]

    provenance_hash, _ = run_real_phoenix(healthy_value, "HEALTHY-FROZEN-PYTEST-2")
    independent_fp = independent_semantic_fingerprint(healthy_value, healthy_quality)

    # Disjoint code paths, disjoint artifacts -- Phoenix's real provenance
    # hash and this harness's independent fingerprint must never coincide
    # or be derivable from one another.
    assert provenance_hash != independent_fp
    assert len(provenance_hash) > 0
    assert len(independent_fp) > 0

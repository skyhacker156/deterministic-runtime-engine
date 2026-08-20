"""
Phase 2A -- Information-Preservation Experiment.

Question: what information must cross the ingestion boundary for Phoenix A
to preserve the semantics an independent external system actually provides?

Not "should quality affect execution" -- just "can the distinction be
represented at all." Baseline uses ONLY real, unmodified Phoenix A code.
Candidate A is a standalone harness function (this file), never touching
any real Phoenix source file, used purely to test whether the missing
information COULD be carried if something chose to.
"""
import sys, json, hashlib, struct
sys.path.insert(0, '../')
from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket
from bridge_integrator_contract import BridgeIntegrator
from replay_engine import _bridge_frame_to_kernel_frame
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule

CONST_VIB = [1.4] * 3
CONST_TEMP = [72.0] * 3


def run_baseline(ph_value, seq_id):
    """external reading -> numeric normalization -> Phoenix tensor.
    Quality, if any, is never passed in -- there is nowhere to put it."""
    adapter = VentAdapterContract()
    bridge = BridgeIntegrator()
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()

    pkt = RawVentTelemetryPacket(
        batch_id=f"baseline-{seq_id}", timestamp=1755648000.0 + seq_id,
        chemical_pH=[ph_value]*3, seismic_amplitude=CONST_VIB, temperature_readings=CONST_TEMP,
    )
    batch, log = adapter.process_raw_packet(pkt)
    bridge_frame = bridge.verify_and_transform(batch)
    kframe = _bridge_frame_to_kernel_frame(bridge_frame, seq_id=0)
    envelope, result = engine.process_frame(kframe)
    return {
        "provenance_hash": batch.provenance_hash,
        "kernel_provenance_hash": kframe.provenance_hash.hex(),
        "envelope_state_hash": envelope.state_hash.hex() if hasattr(envelope, 'state_hash') else None,
        "output_payload_first5": [round(x, 8) for x in result.output_payload[:5].tolist()],
        "module_hash": result.module_hash.hex(),
        "metrics": {k: round(v, 8) for k, v in result.metrics.items() if k != 'execution_latency_us'},
    }


def run_candidate_a(ph_value, quality, seq_id):
    """external reading + quality -> (numeric value, explicit quality state)
    -> Phoenix. STANDALONE harness, not a modification of any real Phoenix
    file. Runs the real, unmodified Phoenix pipeline for the numeric side
    exactly as baseline does, then separately computes a candidate combined
    representation that a real integration WOULD need to produce if quality
    were to be carried forward -- e.g. as an additional hash input alongside
    the real provenance hash, analogous to how batch_id/timestamp already
    participate in compute_canonical_hash."""
    baseline = run_baseline(ph_value, seq_id)

    # Candidate encoding: value hash (the real Phoenix one) + quality,
    # combined the same structural way Phoenix already combines
    # batch_id/timestamp/tensor -- by hashing them together.
    hasher = hashlib.sha256()
    hasher.update(bytes.fromhex(baseline["provenance_hash"]))
    hasher.update(quality.encode('utf-8'))
    candidate_combined_hash = hasher.hexdigest()

    return {
        **baseline,
        "quality": quality,
        "candidate_combined_hash": candidate_combined_hash,
    }


print("="*100)
print("TEST SET 1: healthy pH (7.1, GOOD) vs failed pH (-1.0, BAD) -- value AND quality both differ")
print("="*100)
base_healthy = run_baseline(7.1, 0)
base_failed = run_baseline(-1.0, 0)
cand_healthy = run_candidate_a(7.1, "GOOD", 0)
cand_failed = run_candidate_a(-1.0, "BAD", 0)

print("\n--- BASELINE (real Phoenix, unmodified) ---")
print(json.dumps({"healthy": base_healthy, "failed": base_failed}, indent=2))
print(f"\nQ1 Can downstream reconstruct which was BAD from Phoenix's own artifacts alone? "
      f"provenance_hash differs: {base_healthy['provenance_hash'] != base_failed['provenance_hash']} "
      f"-- but nothing marks WHICH direction of difference means 'fault'. Answer: NO, not as a category.")
print(f"Q2 Represented in execution state (envelope)? "
      f"envelope_state_hash differs: {base_healthy['envelope_state_hash'] != base_failed['envelope_state_hash']} "
      f"-- differs only because payload differs, same caveat as Q1. Answer: NO explicit representation.")
print(f"Q3 Included in provenance? provenance_hash inputs are batch_id/timestamp/tensor only (source-confirmed). Answer: NO.")
print(f"Q4 Does replay reproduce it? Replay reproduces the NUMBER faithfully (Phoenix's real guarantee) "
      f"-- but there was never a quality tag to reproduce. Answer: replay is faithful to what WAS recorded (the number), not to quality (never recorded).")

print("\n--- CANDIDATE A (standalone harness, quality threaded alongside) ---")
print(json.dumps({"healthy": cand_healthy, "failed": cand_failed}, indent=2))
print(f"\ncandidate_combined_hash differs: {cand_healthy['candidate_combined_hash'] != cand_failed['candidate_combined_hash']}")
print("-> Under Candidate A, quality is now hash-visible and reconstructible as its own explicit field (not just inferred from a numeric shift).")

print()
print("="*100)
print("TEST SET 2 (the sharp test): SAME numeric value (7.1), quality alone differs (GOOD vs BAD)")
print("="*100)
base_same_a = run_baseline(7.1, 0)
base_same_b = run_baseline(7.1, 0)
cand_same_a = run_candidate_a(7.1, "GOOD", 0)
cand_same_b = run_candidate_a(7.1, "BAD", 0)

print(f"\nQ5 (baseline) Does changing ONLY quality produce a deterministically different Phoenix state?")
print(f"  provenance_hash equal:    {base_same_a['provenance_hash'] == base_same_b['provenance_hash']}")
print(f"  kernel_provenance equal:  {base_same_a['kernel_provenance_hash'] == base_same_b['kernel_provenance_hash']}")
print(f"  module_hash equal:        {base_same_a['module_hash'] == base_same_b['module_hash']}")
print(f"  output_payload equal:     {base_same_a['output_payload_first5'] == base_same_b['output_payload_first5']}")
print(f"  -> ALL IDENTICAL: quality-only change is completely invisible to baseline Phoenix. Answer: NO.")

print(f"\nQ5 (candidate A) Same test, candidate representation:")
print(f"  candidate_combined_hash equal: {cand_same_a['candidate_combined_hash'] == cand_same_b['candidate_combined_hash']}")
print(f"  -> Candidate A's combined hash DIFFERS even though the numeric value and Phoenix's own real hash are identical.")

print(f"\nQ6 Can the system distinguish 'value changed' from 'trust changed'?")
print(f"  Baseline: value-change and trust-change are BOTH invisible-as-categories; only value-change produces ANY numeric signal at all -- trust-change alone produces NOTHING. So baseline cannot distinguish them, because it can only see one of the two in the first place.")
print(f"  Candidate A: value-change alone changes provenance_hash (inherited from baseline) but leaves quality-only encoding component fixed; quality-change alone changes candidate_combined_hash while provenance_hash stays fixed. -> Candidate A CAN distinguish 'value changed' from 'trust changed', because the two are hashed from genuinely independent inputs.")

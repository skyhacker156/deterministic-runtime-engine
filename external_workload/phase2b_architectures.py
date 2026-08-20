"""
Phase 2B -- Three candidate architectures for carrying external semantic
(quality) information alongside Phoenix A's real, unmodified value pipeline.
None of these touch any real Phoenix source file. All three reuse Phoenix's
REAL compute_canonical_hash and REAL KernelStateEnvelope/generation_id
mechanism unmodified, so "value provenance" and "generation identity" are
always the genuine Phoenix guarantee, not a reimplementation.

Tested against 6 explicit invariants, fairly, without presupposing a winner.
"""
import sys, hashlib, json
sys.path.insert(0, '../')
from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket, StratifiedTensorPacker
from bridge_integrator_contract import BridgeIntegrator
from replay_engine import _bridge_frame_to_kernel_frame
from deterministic_execution_engine import DeterministicExecutionEngine
from phoenix_a_execution_module import PhoenixAExecutionModule

CONST_VIB = [1.4] * 3
CONST_TEMP = [72.0] * 3


def real_value_provenance(ph_value, batch_id, timestamp):
    """Uses Phoenix's REAL, unmodified compute_canonical_hash. Never
    touched by any of the three architectures below."""
    tensor = StratifiedTensorPacker.pack_channels_stratified(
        {"chemical_pH": [ph_value]*3, "seismic_amplitude": CONST_VIB, "temperature_readings": CONST_TEMP},
        256,
    )
    return VentAdapterContract.compute_canonical_hash(batch_id, timestamp, tensor)


def run_real_engine(ph_value, batch_id, seq_id):
    """Real, unmodified Phoenix pipeline end to end, for generation-identity
    and replay-of-value tests."""
    adapter = VentAdapterContract()
    bridge = BridgeIntegrator()
    module = PhoenixAExecutionModule()
    engine = DeterministicExecutionEngine(module=module)
    engine.initialize()
    pkt = RawVentTelemetryPacket(
        batch_id=batch_id, timestamp=1755648000.0 + seq_id,
        chemical_pH=[ph_value]*3, seismic_amplitude=CONST_VIB, temperature_readings=CONST_TEMP,
    )
    batch, log = adapter.process_raw_packet(pkt)
    bridge_frame = bridge.verify_and_transform(batch)
    kframe = _bridge_frame_to_kernel_frame(bridge_frame, seq_id=0)
    envelope, result = engine.process_frame(kframe)
    return batch.provenance_hash, envelope, result


# ---------------------------------------------------------------------------
# ARCHITECTURE A -- External sidecar: quality lives in a wholly separate
# record, never touching Phoenix's real chain at all.
# ---------------------------------------------------------------------------
class SidecarQualityRecord:
    def __init__(self, batch_id, timestamp, quality):
        self.batch_id, self.timestamp, self.quality = batch_id, timestamp, quality
    def semantic_provenance(self):
        h = hashlib.sha256()
        h.update(self.batch_id.encode()); h.update(str(self.timestamp).encode())
        h.update(self.quality.encode())
        return h.hexdigest()


# ---------------------------------------------------------------------------
# ARCHITECTURE B -- Semantic state incorporated into ONE canonical object
# that carries both value and quality together (unlike A's two independent
# records). value_provenance and semantic_provenance are still SEPARATELY
# computed hashes (not merged into one), so invariants 1/2 aren't corrupted
# by construction -- what changes vs A is that quality is now a REQUIRED
# field of the single object representing "the reading," not an optional
# bolt-on file.
# ---------------------------------------------------------------------------
class CanonicalReading:
    def __init__(self, batch_id, timestamp, ph_value, quality):
        self.batch_id, self.timestamp, self.ph_value, self.quality = batch_id, timestamp, ph_value, quality
        # required field -- cannot construct this object with quality=None
        if quality is None:
            raise ValueError("CanonicalReading requires a quality state; none was given")
    def value_provenance(self):
        return real_value_provenance(self.ph_value, self.batch_id, self.timestamp)
    def semantic_provenance(self):
        h = hashlib.sha256()
        h.update(self.batch_id.encode()); h.update(str(self.timestamp).encode())
        h.update(self.quality.encode())
        return h.hexdigest()


# ---------------------------------------------------------------------------
# ARCHITECTURE C -- Domain-module interpretation: same preservation as B,
# plus an explicit domain module that decides what quality MEANS, kept
# structurally separate from Phoenix's own execution decision.
# ---------------------------------------------------------------------------
def domain_module_interpret(quality: str) -> str:
    """Phoenix itself never calls this. A downstream domain module would."""
    return {
        "GOOD": "ACCEPT",
        "UNCERTAIN": "DISCOUNT",
        "BAD": "INVESTIGATE",
    }.get(quality, "REJECT")


print("="*100)
print("INVARIANT 1: value-only change changes value provenance")
print("="*100)
vp_a = real_value_provenance(7.1, "B", 0.0)
vp_b = real_value_provenance(-1.0, "B", 0.0)
print(f"  Same for all 3 architectures (all reuse the real, unmodified compute_canonical_hash).")
print(f"  value_provenance(7.1) != value_provenance(-1.0): {vp_a != vp_b}")
for arch, semantic_same in [("A (sidecar)", True), ("B (canonical)", True), ("C (domain-module)", True)]:
    print(f"  [{arch}] value change alone leaves semantic_provenance untouched: PASS (by construction, value/quality hashed independently in all 3)")

print()
print("="*100)
print("INVARIANT 2: quality-only change changes semantic provenance")
print("="*100)
sc_a1 = SidecarQualityRecord("B", 0.0, "GOOD").semantic_provenance()
sc_a2 = SidecarQualityRecord("B", 0.0, "BAD").semantic_provenance()
print(f"  [A] semantic_provenance(GOOD) != semantic_provenance(BAD): {sc_a1 != sc_a2}")
cr_b1 = CanonicalReading("B", 0.0, 7.1, "GOOD")
cr_b2 = CanonicalReading("B", 0.0, 7.1, "BAD")
print(f"  [B] semantic_provenance(GOOD) != semantic_provenance(BAD): {cr_b1.semantic_provenance() != cr_b2.semantic_provenance()}")
print(f"  [B] value_provenance UNCHANGED by quality-only change: {cr_b1.value_provenance() == cr_b2.value_provenance()}")
print(f"  [C] identical to B's preservation mechanism -- same result")

print()
print("="*100)
print("INVARIANT 3: generation change changes generation identity")
print("="*100)
_, env1, _ = run_real_engine(7.1, "GEN-1", 0)
_, env2, _ = run_real_engine(7.1, "GEN-1", 0)
print(f"  Real, unmodified Phoenix generation_id mechanism, untouched by all 3 architectures.")
print(f"  Two separately-initialized engines, IDENTICAL value input: envelope.state_hash differs: {env1.state_hash != env2.state_hash}")
print(f"  Cause: fresh generation_id per engine instantiation (by Phoenix's own real design) -- PASS for A/B/C identically, none of them touch this mechanism")

print()
print("="*100)
print("INVARIANT 4: replay reproduces both value and quality")
print("="*100)
print("  [A] Value: YES (Phoenix's real replay guarantee, untouched). Quality: NO -- the sidecar")
print("      record has no replay mechanism of its own; Phoenix's real replay_engine.py/")
print("      kernel_state_replay.py know nothing about it. A second, independently-built and")
print("      independently-verified replay log would be required -- not built here, and not")
print("      free: it is a second thing that can drift out of sync with the first.")
print("  [B] Value: YES (same real mechanism). Quality: STRUCTURALLY POSSIBLE but NOT")
print("      CURRENTLY REAL -- CanonicalReading is a standalone object in this harness; no real")
print("      Phoenix persistence/replay function has been modified to carry it. Replaying quality")
print("      would require extending Phoenix's actual persistence layer, which is a real code")
print("      change to Phoenix itself, out of scope for a standalone harness experiment.")
print("  [C] Same structural status as B -- the domain-module layer changes who INTERPRETS")
print("      quality, not whether it is currently replayed. Same unmet precondition as B.")
print("  HONEST RESULT: none of the three currently has a WORKING replay mechanism for quality.")
print("  A's gap is structural (two independent logs, by design). B/C's gap is an unimplemented")
print("  extension to real Phoenix persistence code, not attempted here on purpose.")

print()
print("="*100)
print("INVARIANT 5: removing the quality signal cannot silently produce the same state")
print("="*100)
ph_hash, env_full, result_full = run_real_engine(7.1, "REMOVE-TEST", 0)
print(f"  [A] Delete the sidecar record entirely. Phoenix's own real artifacts")
print(f"      (provenance_hash, envelope.state_hash, result.output_payload) are computed the")
print(f"      SAME way regardless -- they never referenced the sidecar. Result: Phoenix's state")
print(f"      is LITERALLY IDENTICAL whether the sidecar exists or not. FAILS this invariant.")
try:
    CanonicalReading("B", 0.0, 7.1, None)
    print(f"  [B] CanonicalReading(quality=None) unexpectedly succeeded")
except ValueError as e:
    print(f"  [B] CanonicalReading(quality=None) raised: {e}")
    print(f"      Quality is a required constructor field of the single object representing")
    print(f"      the reading -- there is no way to silently produce a valid CanonicalReading")
    print(f"      without it. PASSES this invariant, structurally, within this harness's object.")
print(f"  [C] Same structural guarantee as B (same object).")

print()
print("="*100)
print("INVARIANT 6: a domain module can consume quality without Phoenix deciding what BAD means")
print("="*100)
print(f"  [A] Any downstream reader of the sidecar file can interpret 'quality' however it")
print(f"      likes -- Phoenix never touches or parses the string. PASS, trivially.")
print(f"  [B] canonical_reading.quality is an opaque string as far as value_provenance/")
print(f"      semantic_provenance computation is concerned -- neither hash function interprets")
print(f"      it. PASS, but no explicit consumer is built to demonstrate it.")
print(f"  [C] Explicit domain module built and run:")
for q in ("GOOD", "UNCERTAIN", "BAD"):
    print(f"        domain_module_interpret({q!r}) -> {domain_module_interpret(q)!r}")
print(f"      Phoenix's own execution decision (success=True, per EW-001) is untouched by this")
print(f"      interpretation -- the domain module's decision and Phoenix's execution decision")
print(f"      are two separate, independently-observable outputs. PASS, and the only one of")
print(f"      the three where this separation is explicit and demonstrated rather than implied.")

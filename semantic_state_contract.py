"""
semantic_state_contract.py - Semantic State Persistence Contract
Classification: Surface Layer (experimental, Phase 2C of the External
Workload Validation campaign -- see EW-001, PHOENIX_EXTERNAL_GENERALIZATION_v1.md)

Purpose, stated narrowly and deliberately: preserve an external quality/
trust assertion alongside a numeric value, through persistence and cold
reconstruction, WITHOUT Phoenix A interpreting what that assertion means.
"BAD" is an opaque string here -- this module never branches on its
content, never rejects, discounts, or accepts anything based on it. A
downstream domain module decides what "BAD" means; this contract only
guarantees the assertion survives unchanged and is cryptographically
distinguishable from any other quality state for the same value.

Deliberately excluded from this first extension, per explicit scope: no
confidence scores, no AI judgment fields, no domain reasoning, no coupling
to VentAdapterContract/BridgeIntegrator/DeterministicExecutionEngine. This
module does not import from, and is not imported by, any existing Phoenix
A pipeline file. It is additive and freestanding.
"""

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class SemanticReading:
    """The smallest possible semantic object: one value, one opaque
    quality assertion, and a hash binding them together. Frozen, like
    every other data-transfer object in this codebase."""
    value: float
    quality: str
    semantic_hash: bytes


def compute_semantic_hash(value: float, quality: str) -> bytes:
    """SHA-256 over (value, quality), struct-packed the same way
    VentAdapterContract.compute_canonical_hash packs its own inputs, for
    consistency with this codebase's existing hashing convention."""
    hasher = hashlib.sha256()
    hasher.update(struct.pack(">d", value))
    hasher.update(quality.encode("utf-8"))
    return hasher.digest()


def make_semantic_reading(value: float, quality: str) -> SemanticReading:
    return SemanticReading(
        value=value, quality=quality,
        semantic_hash=compute_semantic_hash(value, quality),
    )


def semantic_reading_to_json(reading: SemanticReading) -> str:
    return json.dumps({
        "value": reading.value,
        "quality": reading.quality,
        "semantic_hash": reading.semantic_hash.hex(),
    })


def semantic_reading_from_json(json_str: str) -> SemanticReading:
    """Reconstructs a SemanticReading from JSON. The stored semantic_hash
    is never trusted -- it is always recomputed from (value, quality) and
    compared, mirroring decision_record_persistence.py's own stated
    convention (never read or trust a persisted hash; recompute it)."""
    payload = json.loads(json_str)
    value = payload["value"]
    quality = payload["quality"]
    recomputed = compute_semantic_hash(value, quality)
    stored = bytes.fromhex(payload["semantic_hash"])
    if recomputed != stored:
        raise ValueError(
            "semantic_hash mismatch: value/quality was tampered with or "
            "corrupted between persistence and reconstruction"
        )
    return SemanticReading(value=value, quality=quality, semantic_hash=recomputed)


def append_semantic_log(path: Path, reading: SemanticReading) -> None:
    """Append-only, one JSON line per reading -- same shape as this
    codebase's other *_log_append functions."""
    with open(path, "a") as f:
        f.write(semantic_reading_to_json(reading) + "\n")


def read_semantic_log(path: Path) -> List[SemanticReading]:
    """Cold reconstruction: reads every line back from disk, in a process
    that holds no memory of how the readings were originally produced.
    Each line's hash is independently reverified on the way in."""
    readings = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                readings.append(semantic_reading_from_json(line))
    return readings

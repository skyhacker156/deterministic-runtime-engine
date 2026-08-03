"""
Execution Context
(execution_context.py)

Maintains deterministic, hash-chained state evolution between execution frames.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import hashlib
import json

GENESIS_PARENT_HASH = b"\x00" * 32


@dataclass(frozen=True)
class ExecutionContext:
    """
    Immutable execution state snapshot.
    """
    seq_id: int
    timestamp_ns: int
    state_vector: Dict = field(default_factory=dict)
    parent_state_hash: bytes = field(default=GENESIS_PARENT_HASH)
    history_window: Tuple[bytes, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        try:
            json.dumps(self.state_vector, sort_keys=True)
        except TypeError as e:
            raise TypeError(f"Non-serializable type in state_vector: {e}") from e

    @property
    def state_hash(self) -> bytes:
        serialized = json.dumps(self.state_vector, sort_keys=True).encode()
        return hashlib.sha256(serialized).digest()

    def derive_next(
        self,
        next_seq_id: int,
        next_timestamp_ns: int,
        state_delta: Dict,
        max_history_len: Optional[int] = None,
    ) -> "ExecutionContext":
        if next_seq_id != self.seq_id + 1:
            raise ValueError(
                f"Non-monotonic context transition: expected seq_id "
                f"{self.seq_id + 1}, got {next_seq_id}"
            )

        updated_state = dict(self.state_vector)
        updated_state.update(state_delta)

        extended_history = self.history_window + (self.state_hash,)
        new_history = (
            extended_history[-max_history_len:]
            if max_history_len is not None
            else extended_history
        )

        return ExecutionContext(
            seq_id=next_seq_id,
            timestamp_ns=next_timestamp_ns,
            state_vector=updated_state,
            parent_state_hash=self.state_hash,
            history_window=new_history,
        )

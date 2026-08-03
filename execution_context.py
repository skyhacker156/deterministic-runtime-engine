"""
Execution Context
(execution_context.py)

Maintains deterministic state evolution
between execution frames.
"""


from dataclasses import dataclass
from typing import Dict

import hashlib
import json



@dataclass(frozen=True)
class ExecutionContext:
    """
    Immutable execution state snapshot.
    """

    seq_id: int

    timestamp_ns: int

    state_vector: Dict



    @property
    def state_hash(self) -> bytes:
        """
        Deterministic context fingerprint.
        """

        serialized = json.dumps(
            self.state_vector,
            sort_keys=True,
            default=str
        ).encode()


        return hashlib.sha256(
            serialized
        ).digest()



    def derive_next(
        self,
        next_seq_id: int,
        next_timestamp_ns: int,
        state_delta: Dict
    ):
        """
        Deterministically derive next context.
        """

        updated = dict(
            self.state_vector
        )


        updated.update(
            state_delta
        )


        return ExecutionContext(
            seq_id=next_seq_id,
            timestamp_ns=next_timestamp_ns,
            state_vector=updated
        )
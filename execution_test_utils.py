"""
Execution Test Utilities

Deterministic generators for Phoenix A validation.
"""


import numpy as np

from execution_kernel_contract import CoreExecutionFrame



def deterministic_payload(
    seed: int = 0
):

    rng = np.random.default_rng(
        seed
    )

    return rng.normal(
        0,
        1,
        256
    ).astype(
        np.float64
    )



def make_frame(
    seq_id: int,
    seed: int = 0,
    timestamp_ns: int = None
):

    if timestamp_ns is None:

        timestamp_ns = seq_id * 1000


    return CoreExecutionFrame.create(
        seq_id=seq_id,
        timestamp_ns=timestamp_ns,
        payload=deterministic_payload(seed)
    )



def make_sequence(
    count: int
):

    return [
        make_frame(
            seq_id=i,
            seed=i
        )
        for i in range(count)
    ]
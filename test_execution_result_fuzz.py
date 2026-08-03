"""
Fuzzing Test Suite - Execution Result Contract
(test_execution_result_fuzz.py)
"""
from hypothesis import given, strategies as st
import numpy as np
import pytest

from execution_module_contract import ExecutionResult


# Strategy for strictly valid finite payloads of shape (256,)
st_valid_payload = st.lists(
    st.floats(
        allow_nan=False,
        allow_infinity=False,
        min_value=-1e12,
        max_value=1e12,
        width=64,
    ),
    min_size=256,
    max_size=256,
).map(lambda lst: np.array(lst, dtype=np.float64))

# Strategy for sequence IDs
st_seq_id = st.integers(min_value=0, max_value=2**63 - 1)

# Strategy for metric keys and dictionary
st_metrics_keys = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=20,
)
st_metrics_dict = st.dictionaries(
    keys=st_metrics_keys,
    values=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e9, max_value=1e9),
    max_size=10,
)

# Strategy for error messages: non-empty AFTER stripping whitespace/control chars,
# since ExecutionResult treats a message that strips to empty as "no message provided".
st_valid_error_message = st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != "")


@given(seq_id=st_seq_id, payload=st_valid_payload, metrics=st_metrics_dict)
def test_fuzz_valid_successful_execution_result(seq_id: int, payload: np.ndarray, metrics: dict):
    res = ExecutionResult(
        seq_id=seq_id,
        success=True,
        output_payload=payload,
        metrics=metrics,
    )
    assert res.seq_id == seq_id
    assert res.success is True
    assert len(res.module_hash) == 32


@given(seq_id=st_seq_id, payload=st_valid_payload, err_msg=st_valid_error_message)
def test_fuzz_valid_failed_execution_result(seq_id: int, payload: np.ndarray, err_msg: str):
    res = ExecutionResult(
        seq_id=seq_id,
        success=False,
        output_payload=payload,
        error_message=err_msg,
    )
    assert res.seq_id == seq_id
    assert res.success is False
    assert res.error_message == err_msg
    assert len(res.module_hash) == 32


@given(
    seq_id=st_seq_id,
    payload=st_valid_payload,
    kv_pairs=st.lists(
        st.tuples(st_metrics_keys, st.floats(allow_nan=False, allow_infinity=False)),
        min_size=2,
        max_size=8,
        unique_by=lambda x: x[0],
    ),
)
def test_fuzz_hash_independence_from_dict_insertion_order(
    seq_id: int, payload: np.ndarray, kv_pairs: list
):
    dict1 = dict(kv_pairs)
    dict2 = dict(reversed(kv_pairs))
    res1 = ExecutionResult(seq_id=seq_id, success=True, output_payload=payload.copy(), metrics=dict1)
    res2 = ExecutionResult(seq_id=seq_id, success=True, output_payload=payload.copy(), metrics=dict2)
    assert res1.module_hash == res2.module_hash


def test_fuzz_invalid_payload_shape_rejected():
    invalid_payload = np.zeros(100, dtype=np.float64)
    with pytest.raises(ValueError, match="shape must be"):
        ExecutionResult(seq_id=1, success=True, output_payload=invalid_payload)


def test_fuzz_failure_without_valid_error_message_rejected():
    valid_payload = np.zeros(256, dtype=np.float64)
    with pytest.raises(ValueError, match="error_message must be provided"):
        ExecutionResult(seq_id=1, success=False, output_payload=valid_payload, error_message="")


def test_fuzz_success_with_error_message_rejected():
    valid_payload = np.zeros(256, dtype=np.float64)
    with pytest.raises(ValueError, match="error_message must be None"):
        ExecutionResult(
            seq_id=1,
            success=True,
            output_payload=valid_payload,
            error_message="Unexpected error",
        )
"""compare 유틸리티 단위 테스트."""

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.utils import ALLOWED_OPERATORS, compare

# === scalar 비교 ===


@pytest.mark.parametrize(
    "operator,left,right,expected",
    [
        (">", 5, 3, True),
        (">", 3, 5, False),
        (">=", 5, 5, True),
        (">=", 4, 5, False),
        ("<", 3, 5, True),
        ("<", 5, 3, False),
        ("<=", 5, 5, True),
        ("<=", 6, 5, False),
        ("==", 5, 5, True),
        ("==", 5, 6, False),
    ],
)
def test_compare_scalar(operator, left, right, expected):
    assert compare(left, operator, right) is expected or compare(left, operator, right) == expected


# === Series vs scalar ===


def test_compare_series_vs_scalar():
    s = pd.Series([1, 2, 3, 4, 5])
    result = compare(s, ">=", 3)
    expected = pd.Series([False, False, True, True, True])
    pd.testing.assert_series_equal(result, expected)


# === Series vs Series ===


def test_compare_series_vs_series():
    a = pd.Series([1, 2, 3])
    b = pd.Series([2, 2, 2])
    result = compare(a, ">", b)
    pd.testing.assert_series_equal(result, pd.Series([False, False, True]))


# === NaN 처리 ===


def test_compare_with_nan_returns_false():
    """NaN은 어느 비교에서도 False (pandas 표준)."""
    s = pd.Series([1.0, np.nan, 3.0])
    result = compare(s, ">", 0)
    pd.testing.assert_series_equal(result, pd.Series([True, False, True]))


# === 미지원 연산자 ===


def test_compare_invalid_operator_raises():
    with pytest.raises(InvalidOperatorError) as excinfo:
        compare(1, "!=", 2)
    assert excinfo.value.code == "INVALID_OPERATOR"
    assert "!=" in str(excinfo.value)


def test_compare_unknown_operator_message_lists_allowed():
    with pytest.raises(InvalidOperatorError) as excinfo:
        compare(1, "<>", 2)
    msg = str(excinfo.value)
    for op in ALLOWED_OPERATORS:
        assert op in msg


# === ALLOWED_OPERATORS 잠금 ===


def test_allowed_operators_immutable_tuple():
    assert isinstance(ALLOWED_OPERATORS, tuple)
    assert ALLOWED_OPERATORS == (">", ">=", "<", "<=", "==")

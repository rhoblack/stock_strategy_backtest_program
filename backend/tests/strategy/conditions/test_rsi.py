"""rsi_level 조건 테스트."""

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.conditions.rsi import RSI_LEVEL_META, rsi_level


def test_rsi_level_uptrend_is_above_70():
    """단조 상승 → RSI 100 → >= 70 만족."""
    df = pd.DataFrame({"adj_close": np.arange(1, 51, dtype=float)})
    result = rsi_level(df, {"period": 14, "operator": ">=", "value": 70})
    assert result.iloc[-1] == True  # noqa: E712


def test_rsi_level_downtrend_is_below_30():
    """단조 하락 → RSI 0 → <= 30 만족."""
    df = pd.DataFrame({"adj_close": np.arange(50, 0, -1, dtype=float)})
    result = rsi_level(df, {"period": 14, "operator": "<=", "value": 30})
    assert result.iloc[-1] == True  # noqa: E712


def test_rsi_level_default_period_14():
    """period 미지정 시 14."""
    df = pd.DataFrame({"adj_close": np.arange(1, 51, dtype=float)})
    result_default = rsi_level(df, {"operator": ">=", "value": 70})
    result_explicit = rsi_level(df, {"period": 14, "operator": ">=", "value": 70})
    pd.testing.assert_series_equal(result_default, result_explicit)


def test_rsi_level_invalid_value_raises():
    df = pd.DataFrame({"adj_close": np.arange(1, 30, dtype=float)})
    with pytest.raises(ValueError):
        rsi_level(df, {"period": 14, "operator": ">=", "value": 150})  # > 100
    with pytest.raises(ValueError):
        rsi_level(df, {"period": 14, "operator": ">=", "value": -10})


def test_rsi_level_invalid_operator_raises():
    df = pd.DataFrame({"adj_close": np.arange(1, 30, dtype=float)})
    with pytest.raises(InvalidOperatorError):
        rsi_level(df, {"period": 14, "operator": "??", "value": 70})


def test_rsi_level_initial_nan_evaluates_to_false():
    """RSI가 NaN인 초기 구간은 비교 결과 False."""
    df = pd.DataFrame({"adj_close": np.arange(1, 20, dtype=float)})
    result = rsi_level(df, {"period": 14, "operator": ">=", "value": 50})
    # 첫 14개는 NaN → False
    assert (~result.iloc[:14]).all()


def test_rsi_level_meta_required_fields():
    for key in ("type", "category", "parameters", "allowed_in"):
        assert key in RSI_LEVEL_META
    assert RSI_LEVEL_META["category"] == "rsi"
    assert RSI_LEVEL_META["requires_position"] is False

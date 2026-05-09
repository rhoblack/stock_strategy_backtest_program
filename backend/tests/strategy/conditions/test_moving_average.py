"""price_vs_ma + ma_cross 조건 테스트."""

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.conditions.moving_average import (
    MA_CROSS_META,
    PRICE_VS_MA_META,
    ma_cross,
    price_vs_ma,
)

# === price_vs_ma ===


def _df_with_close(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"adj_close": values})


def test_price_vs_ma_above_ma():
    # 처음에는 평탄하다가 끝에서 급등 → 마지막은 MA 위
    df = _df_with_close([100, 100, 100, 100, 100, 110])
    result = price_vs_ma(df, {"ma_period": 5, "operator": ">"})
    assert result.iloc[5] == True  # noqa: E712
    # MA가 NaN인 구간(0~3)은 비교 결과 False (NaN > x → False)
    assert (~result.iloc[:4]).all()


def test_price_vs_ma_below_ma():
    df = _df_with_close([100, 100, 100, 100, 100, 90])
    result = price_vs_ma(df, {"ma_period": 5, "operator": "<"})
    assert result.iloc[5] == True  # noqa: E712


def test_price_vs_ma_default_price_field_is_adj_close():
    """price_field 미지정 시 adj_close 사용 (정확성 정책 13.7)."""
    df = pd.DataFrame({"adj_close": [100] * 5 + [110]})
    result = price_vs_ma(df, {"ma_period": 5, "operator": ">"})
    assert result.iloc[5] == True  # noqa: E712


def test_price_vs_ma_invalid_operator_raises():
    df = _df_with_close([100, 101, 102, 103, 104])
    with pytest.raises(InvalidOperatorError):
        price_vs_ma(df, {"ma_period": 3, "operator": "??"})


def test_price_vs_ma_meta_required_fields():
    for key in (
        "type",
        "category",
        "requires_position",
        "name",
        "sentence_template",
        "parameters",
        "allowed_in",
    ):
        assert key in PRICE_VS_MA_META, f"META에 {key} 누락"
    assert PRICE_VS_MA_META["requires_position"] is False
    assert "exit_position" not in PRICE_VS_MA_META["allowed_in"]


# === ma_cross ===


def test_ma_cross_golden_cross_detected():
    """단기선이 장기선 아래에서 위로 교차하는 시점에 True."""
    # 처음에는 단기 < 장기, 끝에서 단기가 급등하여 장기를 넘는 시나리오.
    close = pd.Series([100] * 10 + [110, 120, 130, 140, 150])
    df = pd.DataFrame({"adj_close": close.values})
    result = ma_cross(df, {"short_period": 3, "long_period": 10, "direction": "golden_cross"})
    # 어딘가에서 한 번이라도 True가 발생해야 함
    assert result.any(), f"골든크로스 미검출. 결과: {result.tolist()}"


def test_ma_cross_dead_cross_detected():
    close = pd.Series([100] * 10 + [90, 80, 70, 60, 50])
    df = pd.DataFrame({"adj_close": close.values})
    result = ma_cross(df, {"short_period": 3, "long_period": 10, "direction": "dead_cross"})
    assert result.any()


def test_ma_cross_no_cross_in_flat_data():
    """변동 없는 평탄 데이터에서 교차 발생 안 함."""
    close = pd.Series([100.0] * 30)
    df = pd.DataFrame({"adj_close": close.values})
    result = ma_cross(df, {"short_period": 3, "long_period": 10, "direction": "golden_cross"})
    assert not result.any()


def test_ma_cross_short_must_be_less_than_long():
    df = _df_with_close([100] * 30)
    with pytest.raises(ValueError):
        ma_cross(df, {"short_period": 20, "long_period": 5, "direction": "golden_cross"})


def test_ma_cross_invalid_direction_raises():
    df = _df_with_close([100] * 30)
    with pytest.raises(ValueError):
        ma_cross(df, {"short_period": 3, "long_period": 10, "direction": "sideways"})


def test_ma_cross_no_lookahead_bias():
    """ma_cross는 shift(1)을 사용해 신호 발생 시점이 정확해야 함.

    시계열 1~N까지 ma_cross 신호 → 같은 데이터 1~N+5까지 ma_cross 신호의
    동일 인덱스 결과가 같아야 한다 (미래 데이터로 과거 결과가 바뀌면 안 됨).
    """
    close_short = pd.Series([100] * 10 + [110, 120, 130])
    close_long = pd.Series([100] * 10 + [110, 120, 130, 140, 150, 160])
    df_short = pd.DataFrame({"adj_close": close_short.values})
    df_long = pd.DataFrame({"adj_close": close_long.values})

    res_short = ma_cross(df_short, {"short_period": 3, "long_period": 5, "direction": "golden_cross"})
    res_long = ma_cross(df_long, {"short_period": 3, "long_period": 5, "direction": "golden_cross"})

    # 동일 인덱스 결과 비교
    np.testing.assert_array_equal(res_short.to_numpy(), res_long.iloc[: len(res_short)].to_numpy())


def test_ma_cross_meta_required_fields():
    for key in ("type", "category", "requires_position", "parameters", "allowed_in"):
        assert key in MA_CROSS_META
    assert MA_CROSS_META["requires_position"] is False
    assert "exit_position" not in MA_CROSS_META["allowed_in"]

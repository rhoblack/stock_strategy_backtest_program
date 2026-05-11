"""price_vs_ma + ma_cross + ma_alignment 조건 테스트."""

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.conditions.moving_average import (
    MA_ALIGNMENT_META,
    MA_CROSS_META,
    PRICE_VS_MA_META,
    ma_alignment,
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


# === ma_alignment ===


def _df_aligned(n_warmup: int = 80) -> pd.DataFrame:
    """상승 정렬 (5일MA > 20일MA > 60일MA) 이 확실하게 성립하는 DataFrame.

    n_warmup일간 단조 상승하는 가격 시계열.
    """
    prices = [float(i) for i in range(1, n_warmup + 1)]
    return pd.DataFrame({"adj_close": prices})


def _df_descending(n_warmup: int = 80) -> pd.DataFrame:
    """하락 정렬 (5일MA < 20일MA < 60일MA) 이 확실하게 성립하는 DataFrame."""
    prices = [float(n_warmup - i) for i in range(n_warmup)]
    return pd.DataFrame({"adj_close": prices})


def test_ma_alignment_bullish_detected():
    """단조 상승 시계열에서 bullish 정렬이 감지되어야 함."""
    df = _df_aligned(n_warmup=80)
    result = ma_alignment(df, {"short_period": 5, "mid_period": 20, "long_period": 60, "direction": "bullish"})
    # 충분한 warm-up 후 (마지막 구간) bullish 정렬 True
    assert result.iloc[-1] is True or bool(result.iloc[-1]) is True


def test_ma_alignment_bearish_detected():
    """단조 하락 시계열에서 bearish 정렬이 감지되어야 함."""
    df = _df_descending(n_warmup=80)
    result = ma_alignment(df, {"short_period": 5, "mid_period": 20, "long_period": 60, "direction": "bearish"})
    assert bool(result.iloc[-1]) is True


def test_ma_alignment_bullish_false_when_descending():
    """하락 시계열에서 bullish 정렬은 False여야 함."""
    df = _df_descending(n_warmup=80)
    result = ma_alignment(df, {"short_period": 5, "mid_period": 20, "long_period": 60, "direction": "bullish"})
    assert bool(result.iloc[-1]) is False


def test_ma_alignment_bearish_false_when_ascending():
    """상승 시계열에서 bearish 정렬은 False여야 함."""
    df = _df_aligned(n_warmup=80)
    result = ma_alignment(df, {"short_period": 5, "mid_period": 20, "long_period": 60, "direction": "bearish"})
    assert bool(result.iloc[-1]) is False


def test_ma_alignment_nan_before_warmup():
    """long_period 미만 구간은 NaN → False."""
    df = _df_aligned(n_warmup=80)
    result = ma_alignment(df, {"short_period": 5, "mid_period": 20, "long_period": 60, "direction": "bullish"})
    # 인덱스 0~58(60-1-1) 은 long_ma가 NaN이라 False
    assert (~result.iloc[:59]).all()


def test_ma_alignment_default_params():
    """기본 파라미터 (5/20/60, bullish) 가 정상 동작."""
    df = _df_aligned(n_warmup=80)
    result = ma_alignment(df, {})
    assert bool(result.iloc[-1]) is True


def test_ma_alignment_invalid_period_order_raises():
    """short >= mid 또는 mid >= long이면 ValueError."""
    df = _df_aligned()
    with pytest.raises(ValueError, match="short_period"):
        ma_alignment(df, {"short_period": 20, "mid_period": 5, "long_period": 60})
    with pytest.raises(ValueError, match="short_period"):
        ma_alignment(df, {"short_period": 5, "mid_period": 60, "long_period": 20})
    with pytest.raises(ValueError, match="short_period"):
        ma_alignment(df, {"short_period": 5, "mid_period": 5, "long_period": 60})


def test_ma_alignment_invalid_direction_raises():
    """허용되지 않는 direction은 ValueError."""
    df = _df_aligned()
    with pytest.raises(ValueError, match="direction"):
        ma_alignment(df, {"direction": "sideways"})


def test_ma_alignment_no_lookahead_bias():
    """미래 데이터 추가로 과거 결과가 변하지 않아야 함.

    단조 상승 시계열 1~80과 1~90의 ma_alignment 결과가 동일 인덱스에서 같아야 함.
    """
    prices_short = list(range(1, 81))
    prices_long = list(range(1, 91))
    df_short = pd.DataFrame({"adj_close": [float(p) for p in prices_short]})
    df_long = pd.DataFrame({"adj_close": [float(p) for p in prices_long]})

    cond = {"short_period": 5, "mid_period": 20, "long_period": 60, "direction": "bullish"}
    res_short = ma_alignment(df_short, cond)
    res_long = ma_alignment(df_long, cond)

    np.testing.assert_array_equal(
        res_short.to_numpy(),
        res_long.iloc[: len(res_short)].to_numpy(),
    )


def test_ma_alignment_meta_required_fields():
    for key in ("type", "category", "requires_position", "name", "sentence_template", "parameters", "allowed_in"):
        assert key in MA_ALIGNMENT_META, f"META에 {key} 누락"
    assert MA_ALIGNMENT_META["requires_position"] is False
    assert "exit_position" not in MA_ALIGNMENT_META["allowed_in"]
    assert "exit_signal" not in MA_ALIGNMENT_META["allowed_in"]
    assert "entry" in MA_ALIGNMENT_META["allowed_in"]
    assert "filters" in MA_ALIGNMENT_META["allowed_in"]

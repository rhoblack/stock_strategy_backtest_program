"""rsi_level + rsi_cross 조건 테스트."""

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.conditions.rsi import RSI_CROSS_META, RSI_LEVEL_META, rsi_cross, rsi_level


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


# === rsi_cross ===


def _make_cross_above_df() -> pd.DataFrame:
    """RSI가 30 아래에서 30 이상으로 크로스하는 시계열 생성.

    전략: 먼저 하락(RSI 낮음)하다가 마지막에 급등.
    - 0~24: 단조 하락 (50→26) → RSI < 30 구간 형성
    - 25~49: 단조 상승 (26→75) → RSI 30 돌파 유발
    """
    down = np.linspace(50, 26, 25)
    up = np.linspace(26, 75, 25)
    prices = np.concatenate([down, up])
    return pd.DataFrame({"adj_close": prices})


def _make_cross_below_df() -> pd.DataFrame:
    """RSI가 70 위에서 70 이하로 크로스하는 시계열 생성.

    - 0~24: 단조 상승 (30→75) → RSI > 70 구간 형성
    - 25~49: 단조 하락 (75→25) → RSI 70 하향 돌파 유발
    """
    up = np.linspace(30, 75, 25)
    down = np.linspace(75, 25, 25)
    prices = np.concatenate([up, down])
    return pd.DataFrame({"adj_close": prices})


def test_rsi_cross_above_detected():
    """RSI가 30을 상향 돌파하는 날이 한 번 이상 True여야 함."""
    df = _make_cross_above_df()
    result = rsi_cross(df, {"period": 14, "threshold": 30, "direction": "cross_above"})
    assert result.any(), f"cross_above 미검출. RSI 시리즈를 확인하세요."


def test_rsi_cross_below_detected():
    """RSI가 70을 하향 돌파하는 날이 한 번 이상 True여야 함."""
    df = _make_cross_below_df()
    result = rsi_cross(df, {"period": 14, "threshold": 70, "direction": "cross_below"})
    assert result.any(), f"cross_below 미검출."


def test_rsi_cross_above_false_when_already_above():
    """RSI가 이미 threshold 이상인 상태에서 계속 상승하면 cross_above는 False."""
    # 단조 상승 → RSI 100에 가까워짐 → 한 번 크로스 후 계속 위에 머무름
    # 마지막 row는 이미 위에 있으므로 크로스(전일<, 당일>=) 아님
    prices = np.linspace(1, 200, 100)
    df = pd.DataFrame({"adj_close": prices})
    result = rsi_cross(df, {"period": 14, "threshold": 30, "direction": "cross_above"})
    # 마지막 10개는 이미 RSI >> 30 이므로 False여야 함
    assert (~result.iloc[-10:]).all()


def test_rsi_cross_no_cross_in_flat_data():
    """가격 변화 없는 평탄 데이터에서 크로스 발생 없음."""
    df = pd.DataFrame({"adj_close": [100.0] * 50})
    result_above = rsi_cross(df, {"period": 14, "threshold": 50, "direction": "cross_above"})
    result_below = rsi_cross(df, {"period": 14, "threshold": 50, "direction": "cross_below"})
    assert not result_above.any()
    assert not result_below.any()


def test_rsi_cross_initial_nan_evaluates_to_false():
    """RSI NaN 구간(초기)은 비교 결과 False여야 함."""
    df = _make_cross_above_df()
    result = rsi_cross(df, {"period": 14, "threshold": 30, "direction": "cross_above"})
    # 첫 14개는 RSI NaN → shift 결과도 NaN → False
    assert (~result.iloc[:14]).all()


def test_rsi_cross_default_params():
    """기본 파라미터 (period=14, threshold=30, cross_above) 가 정상 동작."""
    df = _make_cross_above_df()
    result = rsi_cross(df, {})
    # 기본값으로 실행하면 에러 없이 결과 Series 반환
    assert len(result) == len(df)
    assert result.dtype == bool


def test_rsi_cross_invalid_threshold_raises():
    """threshold가 0~100 범위 밖이면 ValueError."""
    df = pd.DataFrame({"adj_close": np.arange(1, 30, dtype=float)})
    with pytest.raises(ValueError, match="threshold"):
        rsi_cross(df, {"threshold": -1, "direction": "cross_above"})
    with pytest.raises(ValueError, match="threshold"):
        rsi_cross(df, {"threshold": 101, "direction": "cross_above"})


def test_rsi_cross_invalid_direction_raises():
    """허용되지 않는 direction이면 ValueError."""
    df = pd.DataFrame({"adj_close": np.arange(1, 30, dtype=float)})
    with pytest.raises(ValueError, match="direction"):
        rsi_cross(df, {"direction": "sideways"})


def test_rsi_cross_no_lookahead_bias():
    """미래 데이터 추가로 과거 결과가 변하지 않아야 함 (shift(1) 검증).

    동일 시계열의 짧은 버전과 긴 버전에서 동일 인덱스 결과가 같아야 한다.
    만약 shift(1)이 없으면 당일 RSI를 기준으로 판단해서 결과가 다를 수 있다.
    """
    # 크로스가 발생하는 기본 시계열
    down = np.linspace(50, 26, 25)
    up = np.linspace(26, 75, 25)
    prices_base = np.concatenate([down, up])

    # 짧은 버전 (50행)
    df_short = pd.DataFrame({"adj_close": prices_base})
    # 긴 버전 (추가 10행 계속 상승)
    extra = np.linspace(75, 85, 10)
    df_long = pd.DataFrame({"adj_close": np.concatenate([prices_base, extra])})

    cond = {"period": 14, "threshold": 30, "direction": "cross_above"}
    res_short = rsi_cross(df_short, cond)
    res_long = rsi_cross(df_long, cond)

    np.testing.assert_array_equal(
        res_short.to_numpy(),
        res_long.iloc[: len(res_short)].to_numpy(),
    )


def test_rsi_cross_meta_required_fields():
    for key in ("type", "category", "requires_position", "name", "sentence_template", "parameters", "allowed_in"):
        assert key in RSI_CROSS_META, f"META에 {key} 누락"
    assert RSI_CROSS_META["requires_position"] is False
    assert "exit_position" not in RSI_CROSS_META["allowed_in"]
    assert "entry" in RSI_CROSS_META["allowed_in"]
    assert "exit_signal" in RSI_CROSS_META["allowed_in"]

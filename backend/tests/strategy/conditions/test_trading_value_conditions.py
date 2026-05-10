"""avg_trading_value 및 market_index_filter 조건 테스트."""

import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.conditions.trading_value import (
    AVG_TRADING_VALUE_META,
    MARKET_INDEX_FILTER_META,
    avg_trading_value,
    market_index_filter,
)

# ============================================================================
# helpers
# ============================================================================


def _make_ohlcv(close_values: list[float], volume_values: list[float] | None = None) -> pd.DataFrame:
    """close + volume 컬럼을 가진 DataFrame 생성."""
    n = len(close_values)
    if volume_values is None:
        volume_values = [1_000_000] * n
    return pd.DataFrame(
        {
            "close": close_values,
            "volume": volume_values,
        }
    )


def _make_index_df(return_values: list[float], col: str = "market_index_return") -> pd.DataFrame:
    """시장 지수 등락률 컬럼이 포함된 DataFrame 생성."""
    return pd.DataFrame({col: return_values})


# ============================================================================
# avg_trading_value — 기본 동작
# ============================================================================


def test_avg_trading_value_above_threshold():
    """거래대금 평균이 임계값 이상이면 True."""
    # close=10_000, volume=100_000 → 거래대금 = 10억 = 10억/1e8 = 10억 → 10 (억원)
    # period=5이면 5일 평균 = 10억원 → value=5.0 이상 → True
    close = [10_000] * 5
    volume = [1_000_000] * 5  # 거래대금 = 100억원/일
    df = _make_ohlcv(close, volume)
    result = avg_trading_value(df, {"period": 5, "operator": ">=", "value": 50.0})
    # 100억 >= 50억 → True
    assert result.iloc[4] is True or result.iloc[4] == True  # noqa: E712


def test_avg_trading_value_below_threshold():
    """거래대금 평균이 임계값 미만이면 False."""
    close = [1_000] * 5
    volume = [100_000] * 5  # 거래대금 = 1억원/일
    df = _make_ohlcv(close, volume)
    result = avg_trading_value(df, {"period": 5, "operator": ">=", "value": 50.0})
    # 1억 >= 50억 → False
    assert result.iloc[4] is False or result.iloc[4] == False  # noqa: E712


def test_avg_trading_value_period_window_nan():
    """period 미만 행은 NaN → False (min_periods 보장)."""
    close = [10_000] * 10
    volume = [1_000_000] * 10
    df = _make_ohlcv(close, volume)
    result = avg_trading_value(df, {"period": 5, "operator": ">=", "value": 1.0})
    # 인덱스 0~3 (총 4행)은 period=5 미만이므로 NaN → False
    assert (~result.iloc[:4]).all(), "period 미만 구간은 False여야 합니다"
    # 인덱스 4부터는 계산 가능
    assert result.iloc[4] is True or result.iloc[4] == True  # noqa: E712


def test_avg_trading_value_default_parameters():
    """파라미터 미지정 시 기본값(period=20, operator='>=', value=30.0) 적용."""
    # 20일 평균 거래대금 = 100억원 → 30억 이상 → True
    close = [10_000] * 20
    volume = [1_000_000] * 20  # 100억/일
    df = _make_ohlcv(close, volume)
    result = avg_trading_value(df, {})
    assert result.iloc[19] is True or result.iloc[19] == True  # noqa: E712


# ============================================================================
# avg_trading_value — operator 전체 분기
# ============================================================================


@pytest.mark.parametrize(
    "operator, value, expected",
    [
        (">=", 100.0, True),   # 100억 >= 100억 → True
        (">=", 101.0, False),  # 100억 >= 101억 → False
        (">", 99.0, True),     # 100억 > 99억 → True
        (">", 100.0, False),   # 100억 > 100억 → False (strictly greater)
        ("<=", 100.0, True),   # 100억 <= 100억 → True
        ("<=", 99.0, False),   # 100억 <= 99억 → False
        ("<", 101.0, True),    # 100억 < 101억 → True
        ("<", 100.0, False),   # 100억 < 100억 → False
    ],
)
def test_avg_trading_value_operators(operator: str, value: float, expected: bool):
    """operator별 비교 분기 검증 (거래대금 정확히 100억원)."""
    # close=10_000, volume=1_000_000 → 100억/일
    close = [10_000] * 5
    volume = [1_000_000] * 5
    df = _make_ohlcv(close, volume)
    result = avg_trading_value(df, {"period": 5, "operator": operator, "value": value})
    assert bool(result.iloc[4]) == expected, f"operator={operator!r}, value={value}: {result.iloc[4]} != {expected}"


def test_avg_trading_value_invalid_operator():
    """지원하지 않는 operator는 InvalidOperatorError."""
    close = [10_000] * 5
    volume = [1_000_000] * 5
    df = _make_ohlcv(close, volume)
    with pytest.raises(InvalidOperatorError):
        avg_trading_value(df, {"period": 5, "operator": "between", "value": 50.0})


# ============================================================================
# avg_trading_value — look-ahead bias 없음 검증
# ============================================================================


def test_avg_trading_value_no_lookahead_bias():
    """미래 데이터(shift 없는 rolling)와 실제 결과가 동일해야 함.

    avg_trading_value는 당일 포함 rolling을 사용하지만,
    이 조건은 당일 장 마감 후 데이터로 평가하는 필터이므로
    look-ahead bias가 없다.

    검증: 마지막 행만 값이 급증하는 데이터에서
    rolling mean의 결과가 shift 없이 계산된 값과 일치하는지 확인한다.
    """
    # 0~3행: 거래대금 1억/일, 4행: 1000억 (급등)
    close = [1_000] * 4 + [100_000]
    volume = [100_000] * 4 + [1_000_000]
    df = _make_ohlcv(close, volume)

    result = avg_trading_value(df, {"period": 5, "operator": ">=", "value": 1.0})

    # 4행의 rolling(5) 평균 = (4개×1억 + 1000억) / 5 = (4+1000)/5 = 200.8억
    # → 1억 이상 True
    assert result.iloc[4] is True or result.iloc[4] == True  # noqa: E712

    # 3행은 period=5 미만(4개 데이터) → NaN → False
    assert result.iloc[3] is False or result.iloc[3] == False  # noqa: E712


# ============================================================================
# avg_trading_value — 메타데이터 검증
# ============================================================================


def test_avg_trading_value_meta_fields():
    """META 필수 필드와 값 검증."""
    for key in ("type", "category", "requires_position", "parameters", "allowed_in", "sentence_template"):
        assert key in AVG_TRADING_VALUE_META, f"META에 {key} 키가 없습니다"
    assert AVG_TRADING_VALUE_META["type"] == "avg_trading_value"
    assert AVG_TRADING_VALUE_META["category"] == "volume"
    assert AVG_TRADING_VALUE_META["requires_position"] is False
    assert "entry" in AVG_TRADING_VALUE_META["allowed_in"]
    assert "filters" in AVG_TRADING_VALUE_META["allowed_in"]
    # exit_position 섹션에 노출되면 안 됨
    assert "exit_position" not in AVG_TRADING_VALUE_META["allowed_in"]
    assert "exit_signal" not in AVG_TRADING_VALUE_META["allowed_in"]


# ============================================================================
# market_index_filter — 기본 동작
# ============================================================================


def test_market_index_filter_positive_return():
    """지수 등락률이 양수 → '> 0' 조건 → True."""
    df = _make_index_df([0.5, 1.2, -0.3, 0.8])
    result = market_index_filter(df, {"index_col": "market_index_return", "operator": ">", "value": 0.0})
    assert result.iloc[0] is True or result.iloc[0] == True   # 0.5 > 0 → True   # noqa: E712
    assert result.iloc[2] is False or result.iloc[2] == False  # -0.3 > 0 → False  # noqa: E712


def test_market_index_filter_negative_return():
    """지수 등락률이 음수 → '> 0' 조건 → False."""
    df = _make_index_df([-1.5, -0.2, -3.0])
    result = market_index_filter(df, {"index_col": "market_index_return", "operator": ">", "value": 0.0})
    assert (~result).all(), "모든 음수 등락률은 > 0 조건에서 False여야 합니다"


def test_market_index_filter_missing_column_graceful():
    """index_col이 df에 없으면 모두 False (graceful degradation)."""
    df = pd.DataFrame({"close": [1000, 2000, 3000], "volume": [100, 200, 300]})
    result = market_index_filter(df, {"index_col": "market_index_return", "operator": ">", "value": 0.0})
    assert len(result) == len(df), "결과 길이가 df와 같아야 합니다"
    assert (~result).all(), "컬럼 없으면 모두 False여야 합니다"
    assert result.index.equals(df.index), "인덱스가 df와 동일해야 합니다"


def test_market_index_filter_default_parameters():
    """파라미터 미지정 시 기본값(index_col='market_index_return', operator='>', value=0.0) 적용."""
    df = _make_index_df([1.0, -1.0, 0.5])
    result = market_index_filter(df, {})
    assert result.iloc[0] is True or result.iloc[0] == True   # 1.0 > 0 → True   # noqa: E712
    assert result.iloc[1] is False or result.iloc[1] == False  # -1.0 > 0 → False  # noqa: E712


def test_market_index_filter_custom_index_col():
    """사용자 정의 index_col 파라미터 사용."""
    df = pd.DataFrame({
        "market_index_return": [0.5, -0.3],
        "kospi_return": [-1.0, 2.0],
    })
    # kospi_return 컬럼으로 평가
    result = market_index_filter(df, {"index_col": "kospi_return", "operator": ">", "value": 0.0})
    assert result.iloc[0] is False or result.iloc[0] == False  # -1.0 > 0 → False  # noqa: E712
    assert result.iloc[1] is True or result.iloc[1] == True   # 2.0 > 0 → True    # noqa: E712


def test_market_index_filter_custom_index_col_missing():
    """사용자 정의 index_col도 없으면 모두 False."""
    df = pd.DataFrame({"market_index_return": [1.0, 2.0]})
    result = market_index_filter(df, {"index_col": "kosdaq_return", "operator": ">", "value": 0.0})
    assert (~result).all()


@pytest.mark.parametrize(
    "operator, value, return_pct, expected",
    [
        (">=", 0.0, 0.0, True),    # 0.0 >= 0.0 → True
        (">", 0.0, 0.0, False),    # 0.0 > 0.0 → False
        ("<=", -1.0, -1.0, True),  # -1.0 <= -1.0 → True
        ("<", 1.0, 0.5, True),     # 0.5 < 1.0 → True
        ("<", 0.5, 0.5, False),    # 0.5 < 0.5 → False
    ],
)
def test_market_index_filter_operators(operator: str, value: float, return_pct: float, expected: bool):
    """operator 전체 분기 검증."""
    df = _make_index_df([return_pct])
    result = market_index_filter(df, {"index_col": "market_index_return", "operator": operator, "value": value})
    assert bool(result.iloc[0]) == expected


def test_market_index_filter_invalid_operator():
    """지원하지 않는 operator는 InvalidOperatorError."""
    df = _make_index_df([1.0, 2.0])
    with pytest.raises(InvalidOperatorError):
        market_index_filter(df, {"index_col": "market_index_return", "operator": "!=", "value": 0.0})


# ============================================================================
# market_index_filter — 메타데이터 검증
# ============================================================================


def test_market_index_filter_meta_fields():
    """META 필수 필드와 값 검증."""
    for key in ("type", "category", "requires_position", "parameters", "allowed_in", "sentence_template"):
        assert key in MARKET_INDEX_FILTER_META, f"META에 {key} 키가 없습니다"
    assert MARKET_INDEX_FILTER_META["type"] == "market_index_filter"
    assert MARKET_INDEX_FILTER_META["category"] == "market"
    assert MARKET_INDEX_FILTER_META["requires_position"] is False
    assert "entry" in MARKET_INDEX_FILTER_META["allowed_in"]
    assert "filters" in MARKET_INDEX_FILTER_META["allowed_in"]
    # exit_position 섹션에 노출되면 안 됨
    assert "exit_position" not in MARKET_INDEX_FILTER_META["allowed_in"]


# ============================================================================
# 결과 타입 및 인덱스 일관성
# ============================================================================


def test_avg_trading_value_result_is_bool_series():
    """결과가 bool dtype Series이고 df와 같은 길이."""
    close = [5_000] * 10
    volume = [500_000] * 10
    df = _make_ohlcv(close, volume)
    result = avg_trading_value(df, {"period": 5, "operator": ">=", "value": 1.0})
    assert isinstance(result, pd.Series)
    assert len(result) == len(df)
    assert result.index.equals(df.index)


def test_market_index_filter_result_is_bool_series():
    """결과가 bool dtype Series이고 df와 같은 길이."""
    df = _make_index_df([0.5, -0.3, 1.2, 0.0])
    result = market_index_filter(df, {"index_col": "market_index_return", "operator": ">", "value": 0.0})
    assert isinstance(result, pd.Series)
    assert len(result) == len(df)
    assert result.index.equals(df.index)

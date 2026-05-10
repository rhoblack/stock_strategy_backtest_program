"""bullish_candle + price_change_pct 조건 테스트.

테스트 항목:
    bullish_candle:
        1.  양봉이고 몸통 비율 >= 기준 → True
        2.  음봉 (종가 < 시가) → False
        3.  도지봉 (고가 == 저가) → False (몸통 비율 NaN)
        4.  min_body_pct=0 → 양봉이기만 하면 True
        5.  양봉이지만 몸통 비율 미달 → False
        6.  look-ahead bias 없음 (당일 OHLC만 사용, 미래 데이터 추가 시 과거 불변)
        7.  결과 타입 bool Series, df.index와 동일 길이

    price_change_pct:
        8.  전일 대비 양수 등락률 > 임계값 → True
        9.  전일 대비 음수 등락률 < 임계값 → True
        10. 첫 번째 행 NaN (shift(1) 없음) → False
        11. 등락률 계산 정확성 (전일 10000, 당일 10300 → 3.0%)
        12. operator >= / <= 비교
        13. look-ahead bias 없음 (shift(1) 전일 데이터, 미래 추가 시 과거 불변)
        14. price_field="adj_open" 사용 가능
        15. 잘못된 operator → InvalidOperatorError

    condition_definitions:
        16. ALL_DEFINITIONS에 bullish_candle + price_change_pct 등록 확인
        17. bullish_candle requires_position=False 확인
        18. price_change_pct allowed_in 확인 (entry, exit_signal, filters 포함)
        19. bullish_candle allowed_in에 exit_position / exit_signal 없음
        20. get_condition_catalog()에 2개 조건 포함
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.condition_definitions import ALL_DEFINITIONS
from app.strategy.conditions.candle import (
    BULLISH_CANDLE_META,
    PRICE_CHANGE_PCT_META,
    bullish_candle,
    price_change_pct,
)

# ============================================================================
# 헬퍼
# ============================================================================


def _make_ohlc(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> pd.DataFrame:
    """OHLC 컬럼을 가진 DataFrame 생성."""
    return pd.DataFrame(
        {
            "adj_open": opens,
            "adj_high": highs,
            "adj_low": lows,
            "adj_close": closes,
        }
    )


def _single_candle(open_: float, high: float, low: float, close: float) -> pd.DataFrame:
    """단일 봉 DataFrame 생성 헬퍼."""
    return _make_ohlc([open_], [high], [low], [close])


# ============================================================================
# bullish_candle 테스트
# ============================================================================


def test_bullish_candle_satisfied():
    """1. 양봉이고 몸통 비율 >= 기준 → True.

    시가 100, 고가 120, 저가 90, 종가 115
    몸통 = 115 - 100 = 15, 범위 = 120 - 90 = 30, 비율 = 50%
    min_body_pct=30 → 50% >= 30% → True
    """
    df = _single_candle(open_=100.0, high=120.0, low=90.0, close=115.0)
    result = bullish_candle(df, {"min_body_pct": 30.0})
    assert result.iloc[0] == True  # noqa: E712


def test_bullish_candle_bearish_returns_false():
    """2. 음봉 (종가 < 시가) → False."""
    df = _single_candle(open_=110.0, high=115.0, low=90.0, close=100.0)
    result = bullish_candle(df, {"min_body_pct": 30.0})
    assert result.iloc[0] == False  # noqa: E712


def test_bullish_candle_doji_high_equals_low_returns_false():
    """3. 도지봉 (고가 == 저가) → False.

    고가 = 저가 = 100이면 범위 = 0 → NaN → body_condition False.
    종가 == 시가로 설정해도 양봉 조건(종가 > 시가)이 이미 False.
    """
    df = _single_candle(open_=100.0, high=100.0, low=100.0, close=100.0)
    result = bullish_candle(df, {"min_body_pct": 0.0})
    assert result.iloc[0] == False  # noqa: E712


def test_bullish_candle_doji_nonzero_range_but_close_equals_open():
    """3. 종가 == 시가이고 고저 범위가 있는 도지봉 → False (is_bullish 조건 불충족)."""
    # 시가 = 종가 = 100, 고가 120, 저가 80 → 몸통 0%지만 양봉 조건 실패
    df = _single_candle(open_=100.0, high=120.0, low=80.0, close=100.0)
    result = bullish_candle(df, {"min_body_pct": 0.0})
    assert result.iloc[0] == False  # noqa: E712


def test_bullish_candle_min_body_pct_zero_returns_true_for_bullish():
    """4. min_body_pct=0 → 양봉이기만 하면 True.

    종가 > 시가면 몸통 비율 조건이 0% >= 0%로 충족된다.
    """
    # 아주 작은 양봉 (몸통 비율 약 5%)
    df = _single_candle(open_=100.0, high=110.0, low=95.0, close=101.0)
    result = bullish_candle(df, {"min_body_pct": 0.0})
    assert result.iloc[0] == True  # noqa: E712


def test_bullish_candle_body_ratio_below_threshold_returns_false():
    """5. 양봉이지만 몸통 비율 미달 → False.

    시가 100, 고가 150, 저가 50, 종가 105
    몸통 = 5, 범위 = 100, 비율 = 5% < min_body_pct=30%
    """
    df = _single_candle(open_=100.0, high=150.0, low=50.0, close=105.0)
    result = bullish_candle(df, {"min_body_pct": 30.0})
    assert result.iloc[0] == False  # noqa: E712


def test_bullish_candle_no_lookahead_bias():
    """6. look-ahead bias 없음: 미래 데이터를 추가해도 과거 신호가 바뀌지 않는다.

    bullish_candle은 당일 OHLC만 사용하므로 미래 행 추가가 과거 결과에 영향 없다.
    """
    opens  = [100.0, 105.0, 102.0, 108.0, 99.0]
    highs  = [120.0, 115.0, 118.0, 130.0, 110.0]
    lows   = [ 90.0,  95.0,  88.0, 100.0,  80.0]
    closes = [115.0, 100.0, 116.0, 125.0, 108.0]

    df_short = _make_ohlc(opens, highs, lows, closes)
    # 미래에 전혀 다른 패턴의 봉 추가
    df_long = _make_ohlc(
        opens  + [50.0, 50.0],
        highs  + [200.0, 200.0],
        lows   + [10.0, 10.0],
        closes + [150.0, 30.0],
    )

    cond = {"min_body_pct": 30.0}
    res_short = bullish_candle(df_short, cond)
    res_long = bullish_candle(df_long, cond)

    np.testing.assert_array_equal(
        res_short.to_numpy(),
        res_long.iloc[: len(res_short)].to_numpy(),
        err_msg="미래 데이터 추가 후 과거 bullish_candle 신호가 변경됨 (look-ahead bias 의심)",
    )


def test_bullish_candle_result_is_bool_series_same_length():
    """7. 결과 타입이 bool Series이고 입력 df와 동일 길이."""
    df = _make_ohlc(
        opens  = [100.0, 102.0, 105.0],
        highs  = [110.0, 115.0, 120.0],
        lows   = [ 90.0,  95.0,  98.0],
        closes = [105.0,  98.0, 118.0],
    )
    result = bullish_candle(df, {"min_body_pct": 20.0})
    assert isinstance(result, pd.Series)
    assert result.dtype == bool
    assert len(result) == len(df)


def test_bullish_candle_body_ratio_exactly_at_threshold():
    """몸통 비율이 임계값과 정확히 같을 때 True (>= 조건)."""
    # 시가 100, 고가 120, 저가 100, 종가 110
    # 몸통 = 10, 범위 = 20, 비율 = 50%
    df = _single_candle(open_=100.0, high=120.0, low=100.0, close=110.0)
    result = bullish_candle(df, {"min_body_pct": 50.0})
    assert result.iloc[0] == True  # noqa: E712

    # min_body_pct=50.01 → False
    result2 = bullish_candle(df, {"min_body_pct": 50.01})
    assert result2.iloc[0] == False  # noqa: E712


# ============================================================================
# price_change_pct 테스트
# ============================================================================


def test_price_change_pct_positive_above_threshold():
    """8. 전일 대비 양수 등락률 > 임계값 → True.

    전일 10000, 당일 10400 → 등락률 4.0% > 3.0% → True
    """
    df = pd.DataFrame({"adj_close": [10000.0, 10400.0]})
    result = price_change_pct(df, {"operator": ">", "value": 3.0})
    assert result.iloc[1] == True  # noqa: E712


def test_price_change_pct_negative_below_threshold():
    """9. 전일 대비 음수 등락률 < 임계값 → True.

    전일 10000, 당일 9700 → 등락률 -3.0% < -2.0% → True
    """
    df = pd.DataFrame({"adj_close": [10000.0, 9700.0]})
    result = price_change_pct(df, {"operator": "<", "value": -2.0})
    assert result.iloc[1] == True  # noqa: E712


def test_price_change_pct_first_row_is_false():
    """10. 첫 번째 행은 전일 데이터 없음 → NaN → False."""
    df = pd.DataFrame({"adj_close": [10000.0, 10300.0]})
    result = price_change_pct(df, {"operator": ">", "value": 0.0})
    assert result.iloc[0] == False  # noqa: E712


def test_price_change_pct_calculation_accuracy():
    """11. 등락률 계산 정확성.

    전일 10000, 당일 10300 → 등락률 = (10300 - 10000) / 10000 * 100 = 3.0%
    value=3.0이면 > 3.0은 False, >= 3.0은 True.
    """
    df = pd.DataFrame({"adj_close": [10000.0, 10300.0]})
    result_gt = price_change_pct(df, {"operator": ">", "value": 3.0})
    result_gte = price_change_pct(df, {"operator": ">=", "value": 3.0})

    assert result_gt.iloc[1] == False   # noqa: E712  # 3.0 > 3.0 → False
    assert result_gte.iloc[1] == True   # noqa: E712  # 3.0 >= 3.0 → True


def test_price_change_pct_operator_lte():
    """12. operator <= 비교.

    전일 10000, 당일 9800 → 등락률 -2.0%
    -2.0 <= -2.0 → True, -2.0 <= -3.0 → False
    """
    df = pd.DataFrame({"adj_close": [10000.0, 9800.0]})
    assert price_change_pct(df, {"operator": "<=", "value": -2.0}).iloc[1] == True   # noqa: E712
    assert price_change_pct(df, {"operator": "<=", "value": -3.0}).iloc[1] == False  # noqa: E712


def test_price_change_pct_no_lookahead_bias():
    """13. look-ahead bias 없음: 미래 데이터를 추가해도 과거 신호가 바뀌지 않는다.

    shift(1)은 과거 데이터만 참조하므로 미래 행 추가가 과거 결과에 영향 없다.
    """
    closes_short = [10000.0, 10300.0, 10200.0, 10500.0, 10450.0]
    closes_long = closes_short + [20000.0, 5000.0]  # 미래에 극단적 값 추가

    df_short = pd.DataFrame({"adj_close": closes_short})
    df_long = pd.DataFrame({"adj_close": closes_long})

    cond = {"operator": ">", "value": 2.0}
    res_short = price_change_pct(df_short, cond)
    res_long = price_change_pct(df_long, cond)

    np.testing.assert_array_equal(
        res_short.to_numpy(),
        res_long.iloc[: len(res_short)].to_numpy(),
        err_msg="미래 데이터 추가 후 과거 price_change_pct 신호가 변경됨 (look-ahead bias 의심)",
    )


def test_price_change_pct_uses_adj_open_field():
    """14. price_field="adj_open" 사용 가능.

    전일 시가 10000, 당일 시가 11000 → 등락률 10.0% > 5.0% → True
    """
    df = pd.DataFrame({"adj_open": [10000.0, 11000.0]})
    result = price_change_pct(df, {"operator": ">", "value": 5.0, "price_field": "adj_open"})
    assert result.iloc[1] == True  # noqa: E712


def test_price_change_pct_invalid_operator_raises():
    """15. 잘못된 operator → InvalidOperatorError."""
    df = pd.DataFrame({"adj_close": [10000.0, 10300.0]})
    with pytest.raises(InvalidOperatorError):
        price_change_pct(df, {"operator": "between", "value": 3.0})


# ============================================================================
# condition_definitions 테스트
# ============================================================================


def test_all_definitions_contains_candle_conditions():
    """16. ALL_DEFINITIONS에 bullish_candle + price_change_pct 등록 확인."""
    assert "bullish_candle" in ALL_DEFINITIONS
    assert "price_change_pct" in ALL_DEFINITIONS

    assert ALL_DEFINITIONS["bullish_candle"] is BULLISH_CANDLE_META
    assert ALL_DEFINITIONS["price_change_pct"] is PRICE_CHANGE_PCT_META


def test_bullish_candle_requires_position_false():
    """17. bullish_candle requires_position=False 확인."""
    from app.strategy.registry import condition_registry

    entry = condition_registry._conditions["bullish_candle"]
    assert entry.requires_position is False
    assert BULLISH_CANDLE_META["requires_position"] is False


def test_price_change_pct_allowed_in():
    """18. price_change_pct allowed_in에 entry, exit_signal, filters 포함.

    exit_position에는 없어야 한다 (시계열 조건).
    """
    allowed = PRICE_CHANGE_PCT_META["allowed_in"]
    assert "entry" in allowed
    assert "exit_signal" in allowed
    assert "filters" in allowed
    assert "exit_position" not in allowed


def test_bullish_candle_allowed_in_no_exit():
    """19. bullish_candle allowed_in에 exit_position / exit_signal 없음.

    양봉 조건은 진입/필터 전용으로, 청산 섹션에 노출되어선 안 된다.
    """
    allowed = BULLISH_CANDLE_META["allowed_in"]
    assert "entry" in allowed
    assert "filters" in allowed
    assert "exit_position" not in allowed
    assert "exit_signal" not in allowed


def test_condition_catalog_contains_candle_conditions():
    """20. get_condition_catalog()에 bullish_candle + price_change_pct 포함."""
    from app.strategy.condition_definitions import get_condition_catalog

    types = {item["type"] for item in get_condition_catalog()}
    assert "bullish_candle" in types
    assert "price_change_pct" in types


def test_bullish_candle_meta_required_fields():
    """BULLISH_CANDLE_META 필수 필드 존재 검증."""
    required_keys = {
        "type", "category", "requires_position",
        "name", "description", "sentence_template",
        "parameters", "allowed_in",
    }
    for key in required_keys:
        assert key in BULLISH_CANDLE_META, f"BULLISH_CANDLE_META에 {key} 누락"

    assert BULLISH_CANDLE_META["type"] == "bullish_candle"
    assert BULLISH_CANDLE_META["category"] == "candle"

    # min_body_pct 파라미터 기본값
    pct_param = next(p for p in BULLISH_CANDLE_META["parameters"] if p["name"] == "min_body_pct")
    assert pct_param["default"] == 30.0
    assert pct_param["min"] == 0.0
    assert pct_param["max"] == 100.0


def test_price_change_pct_meta_required_fields():
    """PRICE_CHANGE_PCT_META 필수 필드 존재 검증."""
    required_keys = {
        "type", "category", "requires_position",
        "name", "description", "sentence_template",
        "parameters", "allowed_in",
    }
    for key in required_keys:
        assert key in PRICE_CHANGE_PCT_META, f"PRICE_CHANGE_PCT_META에 {key} 누락"

    assert PRICE_CHANGE_PCT_META["type"] == "price_change_pct"
    assert PRICE_CHANGE_PCT_META["category"] == "price"
    assert PRICE_CHANGE_PCT_META["requires_position"] is False

    # price_field 기본값은 adj_close (정확성 정책 13.7)
    pf_param = next(p for p in PRICE_CHANGE_PCT_META["parameters"] if p["name"] == "price_field")
    assert pf_param["default"] == "adj_close"

    # operator 기본값
    op_param = next(p for p in PRICE_CHANGE_PCT_META["parameters"] if p["name"] == "operator")
    assert op_param["default"] == ">"

"""new_high_breakout + gap_pct + momentum_return 조건 테스트.

테스트 항목:
    new_high_breakout:
        1.  신고가 돌파 날만 True (명백한 케이스)
        2.  신고가 미달 날은 False
        3.  shift(1) 사용 — 당일 값은 비교 대상에서 제외 (look-ahead bias 없음)
        4.  period 미만 구간(NaN) → False (min_periods)
        5.  field="adj_close" 사용 가능
        6.  META 필수 필드 + requires_position=False + allowed_in 검증

    gap_pct:
        7.  상갭 (adj_open > prev_adj_close) → gap > 0 → True (operator ">")
        8.  하갭 (adj_open < prev_adj_close) → gap < 0 → True (operator "<")
        9.  첫 번째 행 NaN (prev_close 없음) → False
        10. 갭률 계산 정확성 (전일 종가 10000, 당일 시가 10300 → 3.0%)
        11. operator ">=" / ">" / "<=" / "<" 모두 정상
        12. META 필수 필드 + allowed_in 검증

    momentum_return:
        13. N일 수익률 양수 → True (operator ">", value=0)
        14. N일 수익률 음수 → True (operator "<", value=0)
        15. period일 전 데이터 없으면 NaN → False
        16. look-ahead bias 없음 (미래 데이터 추가 시 과거 결과 불변)
        17. value 임계값 비교 (10% 이상 수익률)
        18. META 필수 필드 + allowed_in 검증

    condition_definitions:
        19. ALL_DEFINITIONS에 3개 META 모두 등록 확인
        20. get_condition_catalog()에 3개 조건 포함
        21. new_high_breakout + gap_pct allowed_in에 exit_position 없음
        22. momentum_return allowed_in에 exit_signal 포함
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.condition_definitions import ALL_DEFINITIONS
from app.strategy.conditions.breakout import (
    GAP_PCT_META,
    MOMENTUM_RETURN_META,
    NEW_HIGH_BREAKOUT_META,
    gap_pct,
    momentum_return,
    new_high_breakout,
)

# ============================================================================
# 헬퍼
# ============================================================================


def _make_df_high(values: list[float], field: str = "adj_high") -> pd.DataFrame:
    """adj_high 컬럼만 있는 DataFrame 생성."""
    return pd.DataFrame({field: values})


def _make_df_ohlc(
    opens: list[float],
    highs: list[float],
    closes: list[float],
    lows: list[float] | None = None,
) -> pd.DataFrame:
    """OHLC 컬럼을 가진 DataFrame 생성."""
    data: dict = {
        "adj_open": opens,
        "adj_high": highs,
        "adj_close": closes,
    }
    if lows is not None:
        data["adj_low"] = lows
    return pd.DataFrame(data)


# ============================================================================
# new_high_breakout 테스트
# ============================================================================


def test_new_high_breakout_detected():
    """1. 신고가 돌파 날만 True — 명백한 케이스.

    처음 20개: 고가 100.0 (period=20이므로 이전 20일 최고가 = 100)
    21번째: 고가 101.0 → 전일까지의 20일 최고가(100) 초과 → True
    """
    highs = [100.0] * 20 + [101.0]
    df = _make_df_high(highs)
    result = new_high_breakout(df, {"period": 20, "field": "adj_high"})

    assert isinstance(result, pd.Series)
    assert result.dtype == bool
    # 21번째 봉(index=20)이 True
    assert result.iloc[20] == True  # noqa: E712


def test_new_high_breakout_not_detected():
    """2. 신고가 미달 날은 False.

    처음 20개: 고가 100.0, 21번째: 100.0 (초과 아님) → False
    """
    highs = [100.0] * 21
    df = _make_df_high(highs)
    result = new_high_breakout(df, {"period": 20, "field": "adj_high"})
    assert result.iloc[20] == False  # noqa: E712


def test_new_high_breakout_strictly_greater():
    """2. 같은 값은 돌파가 아님 (> 조건, >= 아님)."""
    highs = [90.0, 95.0, 100.0] * 7 + [100.0]  # 22개, 마지막은 최고가와 동일
    df = _make_df_high(highs)
    result = new_high_breakout(df, {"period": 20, "field": "adj_high"})
    # 마지막 값(100.0)은 전일까지의 최고가(100.0)와 동일 → False
    assert result.iloc[-1] == False  # noqa: E712


def test_new_high_breakout_no_lookahead_bias():
    """3. look-ahead bias 없음: 미래 데이터를 추가해도 과거 신호가 바뀌지 않는다.

    shift(1)을 사용하므로 당일 값은 비교 대상 rolling 윈도우에 포함되지 않는다.
    """
    highs_short = [100.0] * 20 + [101.0, 102.0, 103.0]
    highs_long = highs_short + [200.0, 200.0, 200.0]  # 미래에 매우 큰 값 추가

    df_short = _make_df_high(highs_short)
    df_long = _make_df_high(highs_long)

    cond = {"period": 20, "field": "adj_high"}
    res_short = new_high_breakout(df_short, cond)
    res_long = new_high_breakout(df_long, cond)

    np.testing.assert_array_equal(
        res_short.to_numpy(),
        res_long.iloc[: len(res_short)].to_numpy(),
        err_msg="미래 데이터 추가 후 과거 신호가 변경됨 (look-ahead bias 의심)",
    )


def test_new_high_breakout_period_insufficient_returns_false():
    """4. period 미만 구간 → NaN → False (min_periods=period 설정).

    period=20이면 인덱스 0~19 (20개)는 shift(1) 후 rolling을 채울 수 없어 NaN.
    """
    highs = [100.0] * 15  # period=20인데 15개밖에 없음
    df = _make_df_high(highs)
    result = new_high_breakout(df, {"period": 20, "field": "adj_high"})
    # 전부 False여야 함
    assert not result.any()


def test_new_high_breakout_uses_adj_close_field():
    """5. field="adj_close"로 변경 가능 — adj_high 없이 adj_close로도 동작."""
    closes = [100.0] * 20 + [101.0]
    df = pd.DataFrame({"adj_close": closes})
    result = new_high_breakout(df, {"period": 20, "field": "adj_close"})
    assert result.iloc[20] == True  # noqa: E712


def test_new_high_breakout_meta_fields():
    """6. META 필수 필드 존재, requires_position=False, allowed_in 검증."""
    required_keys = {
        "type", "category", "requires_position",
        "name", "description", "sentence_template",
        "parameters", "allowed_in",
    }
    for key in required_keys:
        assert key in NEW_HIGH_BREAKOUT_META, f"NEW_HIGH_BREAKOUT_META에 {key} 누락"

    assert NEW_HIGH_BREAKOUT_META["requires_position"] is False
    assert NEW_HIGH_BREAKOUT_META["category"] == "breakout"
    assert "entry" in NEW_HIGH_BREAKOUT_META["allowed_in"]
    assert "filters" in NEW_HIGH_BREAKOUT_META["allowed_in"]
    # 시계열 조건은 exit_position에 노출되어선 안 됨
    assert "exit_position" not in NEW_HIGH_BREAKOUT_META["allowed_in"]
    # exit_signal에도 없어야 함 (돌파는 진입 전용)
    assert "exit_signal" not in NEW_HIGH_BREAKOUT_META["allowed_in"]

    # period 파라미터 기본값 및 범위 검증
    period_param = next(p for p in NEW_HIGH_BREAKOUT_META["parameters"] if p["name"] == "period")
    assert period_param["default"] == 20
    assert period_param["min"] == 2
    assert period_param["max"] == 250

    # field 기본값은 adj_high
    field_param = next(p for p in NEW_HIGH_BREAKOUT_META["parameters"] if p["name"] == "field")
    assert field_param["default"] == "adj_high"


# ============================================================================
# gap_pct 테스트
# ============================================================================


def test_gap_pct_upward_gap_detected():
    """7. 상갭 — adj_open이 전일 adj_close보다 높으면 gap > 0 → True (operator ">")."""
    df = _make_df_ohlc(
        opens=[10000.0, 10000.0, 10300.0],  # 3번째: 전일 종가 10000 대비 +3%
        highs=[10100.0, 10100.0, 10400.0],
        closes=[10000.0, 10000.0, 10350.0],
    )
    result = gap_pct(df, {"operator": ">", "value": 2.0})
    assert result.iloc[2] == True  # noqa: E712


def test_gap_pct_downward_gap_detected():
    """8. 하갭 — adj_open이 전일 adj_close보다 낮으면 gap < 0 → True (operator "<")."""
    df = _make_df_ohlc(
        opens=[10000.0, 10000.0, 9700.0],  # 3번째: 전일 종가 10000 대비 -3%
        highs=[10100.0, 10100.0, 9900.0],
        closes=[10000.0, 10000.0, 9750.0],
    )
    result = gap_pct(df, {"operator": "<", "value": -2.0})
    assert result.iloc[2] == True  # noqa: E712


def test_gap_pct_first_row_is_false():
    """9. 첫 번째 행은 전일 종가가 없어 NaN → False."""
    df = _make_df_ohlc(
        opens=[10300.0, 10300.0],
        highs=[10400.0, 10400.0],
        closes=[10200.0, 10200.0],
    )
    result = gap_pct(df, {"operator": ">", "value": 0.0})
    assert result.iloc[0] == False  # noqa: E712


def test_gap_pct_calculation_accuracy():
    """10. 갭률 계산 정확성 — 전일 종가 10000, 당일 시가 10300 → gap=3.0%.

    value=3.0이면 gap > 3.0은 False, gap >= 3.0은 True.
    """
    df = _make_df_ohlc(
        opens=[10000.0, 10300.0],
        highs=[10100.0, 10400.0],
        closes=[10000.0, 10350.0],
    )
    # 갭 = (10300 - 10000) / 10000 * 100 = 3.0%
    result_gt = gap_pct(df, {"operator": ">", "value": 3.0})
    result_gte = gap_pct(df, {"operator": ">=", "value": 3.0})

    assert result_gt.iloc[1] == False   # noqa: E712  # 3.0 > 3.0 은 False
    assert result_gte.iloc[1] == True   # noqa: E712  # 3.0 >= 3.0 은 True


def test_gap_pct_all_operators():
    """11. operator ">", ">=", "<", "<=" 모두 정상 동작."""
    df = _make_df_ohlc(
        opens=[10000.0, 10300.0],
        highs=[10100.0, 10400.0],
        closes=[10000.0, 10350.0],
    )
    # gap = 3.0%
    assert gap_pct(df, {"operator": ">", "value": 2.0}).iloc[1] == True   # noqa: E712
    assert gap_pct(df, {"operator": ">", "value": 3.0}).iloc[1] == False  # noqa: E712
    assert gap_pct(df, {"operator": ">=", "value": 3.0}).iloc[1] == True  # noqa: E712
    assert gap_pct(df, {"operator": "<", "value": 4.0}).iloc[1] == True   # noqa: E712
    assert gap_pct(df, {"operator": "<=", "value": 3.0}).iloc[1] == True  # noqa: E712
    assert gap_pct(df, {"operator": "<=", "value": 2.0}).iloc[1] == False # noqa: E712


def test_gap_pct_no_gap_below_threshold():
    """11. 갭이 임계값 미만이면 False."""
    df = _make_df_ohlc(
        opens=[10000.0, 10100.0],   # gap = 1%
        highs=[10100.0, 10200.0],
        closes=[10000.0, 10150.0],
    )
    result = gap_pct(df, {"operator": ">", "value": 2.0})
    assert result.iloc[1] == False  # noqa: E712


def test_gap_pct_invalid_operator_raises():
    """11. 지원하지 않는 operator는 InvalidOperatorError."""
    df = _make_df_ohlc(
        opens=[10000.0, 10300.0],
        highs=[10100.0, 10400.0],
        closes=[10000.0, 10350.0],
    )
    with pytest.raises(InvalidOperatorError):
        gap_pct(df, {"operator": "between", "value": 3.0})


def test_gap_pct_meta_fields():
    """12. META 필수 필드 + allowed_in 검증."""
    required_keys = {
        "type", "category", "requires_position",
        "name", "description", "sentence_template",
        "parameters", "allowed_in",
    }
    for key in required_keys:
        assert key in GAP_PCT_META, f"GAP_PCT_META에 {key} 누락"

    assert GAP_PCT_META["requires_position"] is False
    assert GAP_PCT_META["category"] == "breakout"
    assert "entry" in GAP_PCT_META["allowed_in"]
    assert "filters" in GAP_PCT_META["allowed_in"]
    assert "exit_position" not in GAP_PCT_META["allowed_in"]

    # operator 기본값
    op_param = next(p for p in GAP_PCT_META["parameters"] if p["name"] == "operator")
    assert op_param["default"] == ">"

    # value 기본값
    val_param = next(p for p in GAP_PCT_META["parameters"] if p["name"] == "value")
    assert val_param["default"] == 3.0


# ============================================================================
# momentum_return 테스트
# ============================================================================


def test_momentum_return_positive_detected():
    """13. N일 수익률 양수 → True (operator ">", value=0)."""
    # 20일 전: 100.0, 현재: 115.0 → 수익률 15% > 0
    closes = [100.0] * 20 + [115.0]
    df = pd.DataFrame({"adj_close": closes})
    result = momentum_return(df, {"period": 20, "operator": ">", "value": 0.0})
    assert result.iloc[20] == True  # noqa: E712


def test_momentum_return_negative_detected():
    """14. N일 수익률 음수 → True (operator "<", value=0)."""
    # 20일 전: 100.0, 현재: 85.0 → 수익률 -15% < 0
    closes = [100.0] * 20 + [85.0]
    df = pd.DataFrame({"adj_close": closes})
    result = momentum_return(df, {"period": 20, "operator": "<", "value": 0.0})
    assert result.iloc[20] == True  # noqa: E712


def test_momentum_return_insufficient_period_returns_false():
    """15. period일 전 데이터가 없으면 NaN → False."""
    closes = [100.0] * 10  # period=20인데 10개밖에 없음
    df = pd.DataFrame({"adj_close": closes})
    result = momentum_return(df, {"period": 20, "operator": ">", "value": 0.0})
    assert not result.any()


def test_momentum_return_no_lookahead_bias():
    """16. look-ahead bias 없음: 미래 데이터를 추가해도 과거 신호가 바뀌지 않는다.

    shift(period)는 과거 데이터만 참조하므로 미래 행 추가가 과거 계산에 영향 없음.
    """
    closes_short = [100.0 + i * 0.5 for i in range(40)]
    closes_long = closes_short + [500.0] * 10  # 미래에 매우 큰 값 추가

    df_short = pd.DataFrame({"adj_close": closes_short})
    df_long = pd.DataFrame({"adj_close": closes_long})

    cond = {"period": 20, "operator": ">", "value": 5.0}
    res_short = momentum_return(df_short, cond)
    res_long = momentum_return(df_long, cond)

    np.testing.assert_array_equal(
        res_short.to_numpy(),
        res_long.iloc[: len(res_short)].to_numpy(),
        err_msg="미래 데이터 추가 후 과거 수익률 신호가 변경됨 (look-ahead bias 의심)",
    )


def test_momentum_return_threshold_accuracy():
    """17. value 임계값 비교 정확성 — 10% 이상 수익률.

    20일 전 100.0, 현재 110.0 → 수익률 10.0%.
    value=10.0이면 > 10.0은 False, >= 10.0은 True.
    """
    closes = [100.0] * 20 + [110.0]
    df = pd.DataFrame({"adj_close": closes})

    result_gt = momentum_return(df, {"period": 20, "operator": ">", "value": 10.0})
    result_gte = momentum_return(df, {"period": 20, "operator": ">=", "value": 10.0})

    assert result_gt.iloc[20] == False    # noqa: E712  # 10.0 > 10.0 → False
    assert result_gte.iloc[20] == True    # noqa: E712  # 10.0 >= 10.0 → True


def test_momentum_return_meta_fields():
    """18. META 필수 필드 + allowed_in 검증."""
    required_keys = {
        "type", "category", "requires_position",
        "name", "description", "sentence_template",
        "parameters", "allowed_in",
    }
    for key in required_keys:
        assert key in MOMENTUM_RETURN_META, f"MOMENTUM_RETURN_META에 {key} 누락"

    assert MOMENTUM_RETURN_META["requires_position"] is False
    assert MOMENTUM_RETURN_META["category"] == "momentum"
    assert "entry" in MOMENTUM_RETURN_META["allowed_in"]
    assert "exit_signal" in MOMENTUM_RETURN_META["allowed_in"]
    assert "filters" in MOMENTUM_RETURN_META["allowed_in"]
    assert "exit_position" not in MOMENTUM_RETURN_META["allowed_in"]

    # period 기본값
    period_param = next(p for p in MOMENTUM_RETURN_META["parameters"] if p["name"] == "period")
    assert period_param["default"] == 20
    assert period_param["min"] == 1

    # price_field 기본값은 adj_close (정확성 정책 13.7)
    pf_param = next(p for p in MOMENTUM_RETURN_META["parameters"] if p["name"] == "price_field")
    assert pf_param["default"] == "adj_close"


def test_momentum_return_uses_adj_open_field():
    """18. price_field="adj_open"으로 변경 가능."""
    opens = [100.0] * 20 + [120.0]
    df = pd.DataFrame({"adj_open": opens})
    result = momentum_return(df, {"period": 20, "operator": ">", "value": 15.0, "price_field": "adj_open"})
    assert result.iloc[20] == True  # noqa: E712


def test_momentum_return_invalid_operator_raises():
    """18. 지원하지 않는 operator는 InvalidOperatorError."""
    closes = [100.0] * 25
    df = pd.DataFrame({"adj_close": closes})
    with pytest.raises(InvalidOperatorError):
        momentum_return(df, {"period": 20, "operator": "!=", "value": 0.0})


# ============================================================================
# condition_definitions 테스트
# ============================================================================


def test_all_definitions_contains_all_three():
    """19. ALL_DEFINITIONS에 3개 META 모두 등록 확인."""
    assert "new_high_breakout" in ALL_DEFINITIONS
    assert "gap_pct" in ALL_DEFINITIONS
    assert "momentum_return" in ALL_DEFINITIONS

    assert ALL_DEFINITIONS["new_high_breakout"] is NEW_HIGH_BREAKOUT_META
    assert ALL_DEFINITIONS["gap_pct"] is GAP_PCT_META
    assert ALL_DEFINITIONS["momentum_return"] is MOMENTUM_RETURN_META


def test_condition_catalog_contains_all_three():
    """20. get_condition_catalog()에 3개 조건 포함."""
    from app.strategy.condition_definitions import get_condition_catalog

    types = {item["type"] for item in get_condition_catalog()}
    assert "new_high_breakout" in types
    assert "gap_pct" in types
    assert "momentum_return" in types


def test_new_high_breakout_gap_pct_not_in_exit_position():
    """21. new_high_breakout + gap_pct allowed_in에 exit_position 없음."""
    from app.strategy.condition_definitions import get_condition_catalog

    items = {item["type"]: item for item in get_condition_catalog()}
    assert "exit_position" not in items["new_high_breakout"]["allowed_in"]
    assert "exit_position" not in items["gap_pct"]["allowed_in"]


def test_momentum_return_allowed_in_exit_signal():
    """22. momentum_return allowed_in에 exit_signal 포함."""
    from app.strategy.condition_definitions import get_condition_catalog

    items = {item["type"]: item for item in get_condition_catalog()}
    assert "exit_signal" in items["momentum_return"]["allowed_in"]


def test_requires_position_false_for_all_three():
    """new_high_breakout, gap_pct, momentum_return 모두 requires_position=False."""
    from app.strategy.registry import condition_registry

    for ctype in ("new_high_breakout", "gap_pct", "momentum_return"):
        entry = condition_registry._conditions[ctype]
        assert entry.requires_position is False, f"{ctype} requires_position이 False가 아님"

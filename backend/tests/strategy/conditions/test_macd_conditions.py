"""macd_cross + macd_histogram 조건 테스트.

테스트 항목:
    macd_cross:
        1.  골든크로스: MACD가 시그널 상향 돌파 날만 True
        2.  데드크로스: MACD가 시그널 하향 돌파 날만 True
        3.  look-ahead bias 없음: shift(1) 사용 확인
        4.  fast >= slow 시 ValueError
        5.  크로스 없는 구간 → 모두 False
        6.  period 미만 구간 NaN → False
        7.  잘못된 direction → ValueError
        8.  기본 price_field = adj_close (정확성 정책 13.7)
        9.  requires_position=False 확인
        10. META 필수 필드 + allowed_in 검증

    macd_histogram:
        11. 히스토그램 > 0 조건 (양수 모멘텀)
        12. 히스토그램 < 0 조건 (음수 모멘텀)
        13. ">=" / "<=" operator
        14. period 미만 구간 NaN → False
        15. look-ahead bias 없음 (미래 데이터 추가 시 과거 결과 불변)
        16. META 필수 필드 + allowed_in 검증 (filters 포함)

    API / condition_definitions:
        17. condition_definitions에 macd_cross + macd_histogram 등록 확인
        18. GET /api/conditions 응답에 두 조건 포함
        19. macd_histogram allowed_in에 filters 포함 확인
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.strategy.condition_definitions import ALL_DEFINITIONS
from app.strategy.conditions.macd import (
    MACD_CROSS_META,
    MACD_HISTOGRAM_META,
    macd_cross,
    macd_histogram,
)

# ============================================================================
# 헬퍼
# ============================================================================


def _make_df(values: list[float], field: str = "adj_close") -> pd.DataFrame:
    return pd.DataFrame({field: values})


def _golden_cross_data(n: int = 100) -> list[float]:
    """하락 후 급등 패턴 — MACD 골든크로스 유발.

    처음 40개 봉은 하락(MACD < 시그널), 이후 급등으로 MACD가 시그널을 상향 돌파.
    """
    down = [100.0 - i * 0.5 for i in range(40)]
    up = [80.0 + i * 3.0 for i in range(n - 40)]
    return down + up


def _dead_cross_data(n: int = 100) -> list[float]:
    """상승 후 급락 패턴 — MACD 데드크로스 유발.

    처음 40개 봉은 상승(MACD > 시그널), 이후 급락으로 MACD가 시그널을 하향 돌파.
    """
    up = [100.0 + i * 0.5 for i in range(40)]
    down = [120.0 - i * 3.0 for i in range(n - 40)]
    return up + down


# ============================================================================
# macd_cross 테스트
# ============================================================================


def test_macd_cross_golden_cross_detected():
    """1. MACD가 시그널을 상향 돌파하는 날 True가 발생한다."""
    df = _make_df(_golden_cross_data())
    result = macd_cross(df, {"fast": 12, "slow": 26, "signal": 9, "direction": "golden_cross"})
    assert isinstance(result, pd.Series)
    assert result.dtype == bool
    assert result.any(), f"골든크로스 미검출: {result.tolist()}"


def test_macd_cross_golden_cross_only_at_crossover():
    """1. 골든크로스 날만 True. MACD가 시그널 위에 있는 연속 구간은 False."""
    df = _make_df(_golden_cross_data())
    result = macd_cross(df, {"fast": 12, "slow": 26, "signal": 9, "direction": "golden_cross"})
    # True가 연속으로 나타나면 안 됨 — 크로스 당일만 True여야 함
    # (연속 True 쌍이 0개여야 함)
    consecutive_trues = (result & result.shift(1, fill_value=False)).sum()
    assert consecutive_trues == 0, f"연속 True 발생(크로스 중복): {consecutive_trues}건"


def test_macd_cross_dead_cross_detected():
    """2. MACD가 시그널을 하향 돌파하는 날 True가 발생한다."""
    df = _make_df(_dead_cross_data())
    result = macd_cross(df, {"fast": 12, "slow": 26, "signal": 9, "direction": "dead_cross"})
    assert result.any(), f"데드크로스 미검출: {result.tolist()}"


def test_macd_cross_no_lookahead_bias():
    """3. look-ahead bias 없음: 미래 데이터를 추가해도 과거 신호가 바뀌지 않는다."""
    values_short = _golden_cross_data(n=70)
    values_long = _golden_cross_data(n=80)

    df_short = _make_df(values_short)
    df_long = _make_df(values_long)

    cond = {"fast": 12, "slow": 26, "signal": 9, "direction": "golden_cross"}
    res_short = macd_cross(df_short, cond)
    res_long = macd_cross(df_long, cond)

    np.testing.assert_array_equal(
        res_short.to_numpy(),
        res_long.iloc[: len(res_short)].to_numpy(),
        err_msg="미래 데이터 추가 후 과거 신호가 변경됨 (look-ahead bias)",
    )


def test_macd_cross_fast_ge_slow_raises_valueerror():
    """4. fast >= slow 시 ValueError."""
    df = _make_df([100.0] * 50)
    with pytest.raises(ValueError, match="fast"):
        macd_cross(df, {"fast": 26, "slow": 12, "signal": 9, "direction": "golden_cross"})


def test_macd_cross_fast_eq_slow_raises_valueerror():
    """4. fast == slow 시도 ValueError."""
    df = _make_df([100.0] * 50)
    with pytest.raises(ValueError):
        macd_cross(df, {"fast": 12, "slow": 12, "signal": 9, "direction": "golden_cross"})


def test_macd_cross_no_cross_in_flat_data():
    """5. 완전히 평탄한 데이터에서 교차 발생 없음 → 전체 False."""
    df = _make_df([100.0] * 100)
    result = macd_cross(df, {"fast": 12, "slow": 26, "signal": 9, "direction": "golden_cross"})
    assert not result.any(), "평탄 데이터에서 크로스 발생"


def test_macd_cross_nan_period_returns_false():
    """6. MACD 계산 기간(slow + signal - 1) 미만 구간 → NaN → False."""
    # slow=26, signal=9 → 최소 34개 봉은 있어야 의미 있는 값 등장
    df = _make_df([100.0 + i for i in range(20)])  # 20개만
    result = macd_cross(df, {"fast": 12, "slow": 26, "signal": 9, "direction": "golden_cross"})
    # 전체가 NaN 구간이므로 True 없어야 함
    assert not result.any()


def test_macd_cross_invalid_direction_raises():
    """7. 지원하지 않는 direction은 ValueError."""
    df = _make_df([100.0] * 80)
    with pytest.raises(ValueError, match="direction"):
        macd_cross(df, {"fast": 12, "slow": 26, "signal": 9, "direction": "sideways"})


def test_macd_cross_default_price_field_adj_close():
    """8. price_field 미지정 시 adj_close를 사용한다 (정확성 정책 13.7).
    adj_open 없이 adj_close만 있는 df에서 에러 없이 동작해야 함."""
    df = _make_df(_golden_cross_data())
    # price_field를 명시하지 않음
    result = macd_cross(df, {"fast": 12, "slow": 26, "signal": 9, "direction": "golden_cross"})
    assert isinstance(result, pd.Series)


def test_macd_cross_requires_position_false():
    """9. macd_cross는 시계열 조건 — requires_position=False."""
    from app.strategy.registry import condition_registry

    entry = condition_registry._conditions["macd_cross"]
    assert entry.requires_position is False


def test_macd_cross_meta_fields():
    """10. META 필수 필드 존재 및 allowed_in 검증."""
    required_keys = {
        "type", "category", "requires_position",
        "name", "description", "sentence_template",
        "parameters", "allowed_in",
    }
    for key in required_keys:
        assert key in MACD_CROSS_META, f"MACD_CROSS_META에 {key} 누락"
    assert MACD_CROSS_META["requires_position"] is False
    assert "entry" in MACD_CROSS_META["allowed_in"]
    assert "exit_signal" in MACD_CROSS_META["allowed_in"]
    assert "exit_position" not in MACD_CROSS_META["allowed_in"]
    # fast 기본값 검증
    fast_param = next(p for p in MACD_CROSS_META["parameters"] if p["name"] == "fast")
    assert fast_param["default"] == 12
    # price_field 기본값 검증
    pf_param = next(p for p in MACD_CROSS_META["parameters"] if p["name"] == "price_field")
    assert pf_param["default"] == "adj_close"


# ============================================================================
# macd_histogram 테스트
# ============================================================================


def test_macd_histogram_positive_momentum():
    """11. 상승 추세 데이터에서 히스토그램 > 0인 구간이 존재한다."""
    df = _make_df(_golden_cross_data())
    result = macd_histogram(df, {"fast": 12, "slow": 26, "signal": 9, "operator": ">", "value": 0.0})
    assert isinstance(result, pd.Series)
    assert result.dtype == bool
    assert result.any(), "상승 추세에서 히스토그램 > 0 구간 없음"


def test_macd_histogram_negative_momentum():
    """12. 하락 추세 데이터에서 히스토그램 < 0인 구간이 존재한다."""
    df = _make_df(_dead_cross_data())
    result = macd_histogram(df, {"fast": 12, "slow": 26, "signal": 9, "operator": "<", "value": 0.0})
    assert result.any(), "하락 추세에서 히스토그램 < 0 구간 없음"


def test_macd_histogram_gte_operator():
    """13. '>=' operator가 정상 동작한다."""
    df = _make_df(_golden_cross_data())
    result_gt = macd_histogram(
        df, {"fast": 12, "slow": 26, "signal": 9, "operator": ">", "value": 0.0}
    )
    result_gte = macd_histogram(
        df, {"fast": 12, "slow": 26, "signal": 9, "operator": ">=", "value": 0.0}
    )
    # '>=' 는 '>' 보다 같거나 더 많은 True 포함
    assert result_gte.sum() >= result_gt.sum()


def test_macd_histogram_lte_operator():
    """13. '<=' operator가 정상 동작한다."""
    df = _make_df(_dead_cross_data())
    result_lt = macd_histogram(
        df, {"fast": 12, "slow": 26, "signal": 9, "operator": "<", "value": 0.0}
    )
    result_lte = macd_histogram(
        df, {"fast": 12, "slow": 26, "signal": 9, "operator": "<=", "value": 0.0}
    )
    assert result_lte.sum() >= result_lt.sum()


def test_macd_histogram_nan_period_returns_false():
    """14. 계산 기간 미만 구간 NaN → False."""
    df = _make_df([100.0 + i for i in range(20)])  # 20개만
    result = macd_histogram(
        df, {"fast": 12, "slow": 26, "signal": 9, "operator": ">", "value": 0.0}
    )
    assert not result.any()


def test_macd_histogram_no_lookahead_bias():
    """15. look-ahead bias 없음: 미래 데이터를 추가해도 과거 히스토그램 신호 불변."""
    values_short = _golden_cross_data(n=70)
    values_long = _golden_cross_data(n=80)

    df_short = _make_df(values_short)
    df_long = _make_df(values_long)

    cond = {"fast": 12, "slow": 26, "signal": 9, "operator": ">", "value": 0.0}
    res_short = macd_histogram(df_short, cond)
    res_long = macd_histogram(df_long, cond)

    np.testing.assert_array_equal(
        res_short.to_numpy(),
        res_long.iloc[: len(res_short)].to_numpy(),
        err_msg="미래 데이터 추가 후 과거 히스토그램 신호가 변경됨 (look-ahead bias)",
    )


def test_macd_histogram_meta_fields():
    """16. META 필수 필드 존재 및 allowed_in 검증 (filters 포함)."""
    required_keys = {
        "type", "category", "requires_position",
        "name", "description", "sentence_template",
        "parameters", "allowed_in",
    }
    for key in required_keys:
        assert key in MACD_HISTOGRAM_META, f"MACD_HISTOGRAM_META에 {key} 누락"
    assert MACD_HISTOGRAM_META["requires_position"] is False
    assert "entry" in MACD_HISTOGRAM_META["allowed_in"]
    assert "exit_signal" in MACD_HISTOGRAM_META["allowed_in"]
    assert "filters" in MACD_HISTOGRAM_META["allowed_in"]
    assert "exit_position" not in MACD_HISTOGRAM_META["allowed_in"]
    # operator 기본값
    op_param = next(p for p in MACD_HISTOGRAM_META["parameters"] if p["name"] == "operator")
    assert op_param["default"] == ">"
    # price_field 기본값
    pf_param = next(p for p in MACD_HISTOGRAM_META["parameters"] if p["name"] == "price_field")
    assert pf_param["default"] == "adj_close"


# ============================================================================
# condition_definitions / API 테스트
# ============================================================================


def test_all_definitions_contains_macd_cross():
    """17. ALL_DEFINITIONS에 macd_cross 등록 확인."""
    assert "macd_cross" in ALL_DEFINITIONS
    assert ALL_DEFINITIONS["macd_cross"] is MACD_CROSS_META


def test_all_definitions_contains_macd_histogram():
    """17. ALL_DEFINITIONS에 macd_histogram 등록 확인."""
    assert "macd_histogram" in ALL_DEFINITIONS
    assert ALL_DEFINITIONS["macd_histogram"] is MACD_HISTOGRAM_META


def test_api_conditions_includes_macd_cross():
    """18. GET /api/conditions catalog에 macd_cross 포함 (ALL_DEFINITIONS 경유).

    HTTP client 없이 get_condition_catalog()로 직접 검증.
    HTTP 레벨 검증은 tests/api/test_conditions.py 참조.
    """
    from app.strategy.condition_definitions import get_condition_catalog

    types = {item["type"] for item in get_condition_catalog()}
    assert "macd_cross" in types


def test_api_conditions_includes_macd_histogram():
    """18. GET /api/conditions catalog에 macd_histogram 포함."""
    from app.strategy.condition_definitions import get_condition_catalog

    types = {item["type"] for item in get_condition_catalog()}
    assert "macd_histogram" in types


def test_catalog_macd_histogram_allowed_in_filters():
    """19. macd_histogram은 filters에서 사용 가능."""
    from app.strategy.condition_definitions import get_condition_catalog

    items = get_condition_catalog()
    hist_item = next(i for i in items if i["type"] == "macd_histogram")
    assert "filters" in hist_item["allowed_in"]


def test_catalog_macd_cross_not_allowed_in_exit_position():
    """macd_cross는 exit_position에 노출되지 않아야 함."""
    from app.strategy.condition_definitions import get_condition_catalog

    items = get_condition_catalog()
    cross_item = next(i for i in items if i["type"] == "macd_cross")
    assert "exit_position" not in cross_item["allowed_in"]


def test_catalog_macd_cross_required_fields():
    """macd_cross 카탈로그 항목에 필수 필드 존재."""
    from app.strategy.condition_definitions import get_condition_catalog

    items = get_condition_catalog()
    cross_item = next(i for i in items if i["type"] == "macd_cross")
    for field in ("type", "category", "requires_position", "name", "parameters", "allowed_in"):
        assert field in cross_item, f"macd_cross 카탈로그에 {field} 누락"
    assert cross_item["requires_position"] is False

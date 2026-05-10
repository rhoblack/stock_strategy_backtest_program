"""돌파/갭/모멘텀 기반 시계열 조건.

수록 조건:
    - new_high_breakout: 당일 가격이 N일 전 고점(전일까지)을 상향 돌파
    - gap_pct: 당일 시가가 전일 종가 대비 갭(%)이 임계값 조건 충족
    - momentum_return: N일 전 종가 대비 당일 수익률(%)이 임계값 조건 충족

look-ahead bias 방지:
    - new_high_breakout: df[field].shift(1).rolling(period).max() — 전일까지의 최고가와 비교 (§7.4)
    - gap_pct: df["adj_close"].shift(1) — 전일 종가 사용
    - momentum_return: price.shift(period) — N일 전 과거 데이터 사용
"""

from __future__ import annotations

import pandas as pd

from app.strategy.registry import condition_registry
from app.strategy.utils import compare

# ============================================================================
# new_high_breakout
# ============================================================================


@condition_registry.register(
    "new_high_breakout",
    requires_position=False,
    category="breakout",
)
def new_high_breakout(df: pd.DataFrame, condition: dict) -> pd.Series:
    """당일 가격이 N일 전 고점(전일까지)을 상향 돌파하면 True.

    look-ahead bias 차단: shift(1)로 전일까지의 rolling max를 구한다.
    전일까지의 period일 최고가를 당일 가격과 비교하므로 미래 데이터가 사용되지 않는다.

    파라미터:
        period (int): 신고가 기준 기간. 기본 20.
        field (str): 비교 기준 가격 컬럼명. 기본 "adj_high" (정확성 정책 13.7).
    """
    period = condition.get("period", 20)
    field = condition.get("field", "adj_high")

    if period < 2:
        raise ValueError(f"period는 2 이상이어야 합니다: {period}")

    # 전일까지의 period일 최고가 (look-ahead bias 차단)
    previous_high = df[field].shift(1).rolling(period, min_periods=period).max()
    result = df[field] > previous_high
    return result.fillna(False)


NEW_HIGH_BREAKOUT_META: dict = {
    "type": "new_high_breakout",
    "category": "breakout",
    "requires_position": False,
    "name": "신고가 돌파",
    "description": "당일 가격이 N일 전 고점(전일까지)을 상향 돌파하는지 판단합니다.",
    "sentence_template": "{field_label}가 {period}일 신고가 돌파",
    "parameters": [
        {
            "name": "period",
            "label": "기준 기간(일)",
            "input_type": "number",
            "default": 20,
            "min": 2,
            "max": 250,
        },
        {
            "name": "field",
            "label": "가격 기준",
            "input_type": "select",
            "options": [
                {"label": "수정 고가", "value": "adj_high"},
                {"label": "수정 종가", "value": "adj_close"},
            ],
            "default": "adj_high",
        },
    ],
    "allowed_in": ["entry", "filters"],
}


# ============================================================================
# gap_pct
# ============================================================================


@condition_registry.register(
    "gap_pct",
    requires_position=False,
    category="breakout",
)
def gap_pct(df: pd.DataFrame, condition: dict) -> pd.Series:
    """당일 시가가 전일 종가 대비 갭(%)이 임계값 조건을 충족하면 True.

    갭% = (당일 시가 - 전일 종가) / 전일 종가 * 100

    look-ahead bias 없음: 전일 종가(shift(1)) 대비 당일 시가 비교 — 모두 과거/당일 데이터.

    파라미터:
        operator (str): 비교 연산자. 기본 ">".
        value (float): 갭률 임계값(%). 기본 3.0.
    """
    operator = condition.get("operator", ">")
    value = condition.get("value", 3.0)

    prev_close = df["adj_close"].shift(1)
    gap = (df["adj_open"] - prev_close) / prev_close * 100
    result = compare(gap, operator, value)
    return result.fillna(False)


GAP_PCT_META: dict = {
    "type": "gap_pct",
    "category": "breakout",
    "requires_position": False,
    "name": "갭 발생 조건",
    "description": "당일 시가가 전일 종가 대비 갭(%)이 임계값보다 크거나 작을 때 True입니다.",
    "sentence_template": "갭률이 {value}% {operator_label}",
    "parameters": [
        {
            "name": "operator",
            "label": "비교",
            "input_type": "select",
            "options": [
                {"label": "초과(상갭)", "value": ">"},
                {"label": "미만(하갭)", "value": "<"},
                {"label": "이상", "value": ">="},
                {"label": "이하", "value": "<="},
            ],
            "default": ">",
        },
        {
            "name": "value",
            "label": "갭률 임계값(%)",
            "input_type": "number",
            "default": 3.0,
            "min": -30.0,
            "max": 30.0,
        },
    ],
    "allowed_in": ["entry", "filters"],
}


# ============================================================================
# momentum_return
# ============================================================================


@condition_registry.register(
    "momentum_return",
    requires_position=False,
    category="momentum",
)
def momentum_return(df: pd.DataFrame, condition: dict) -> pd.Series:
    """N일 전 종가 대비 당일 종가의 수익률(%)이 임계값 조건을 충족하면 True.

    수익률% = (현재가 - N일 전 종가) / N일 전 종가 * 100

    look-ahead bias 없음: shift(period)는 과거 데이터만 참조.

    파라미터:
        period (int): 모멘텀 기간. 기본 20.
        operator (str): 비교 연산자. 기본 ">".
        value (float): 수익률 임계값(%). 기본 10.0.
        price_field (str): 가격 컬럼명. 기본 "adj_close" (정확성 정책 13.7).
    """
    period = condition.get("period", 20)
    operator = condition.get("operator", ">")
    value = condition.get("value", 10.0)
    price_field = condition.get("price_field", "adj_close")

    if period < 1:
        raise ValueError(f"period는 1 이상이어야 합니다: {period}")

    price = df[price_field]
    past_price = price.shift(period)
    ret = (price - past_price) / past_price * 100
    result = compare(ret, operator, value)
    return result.fillna(False)


MOMENTUM_RETURN_META: dict = {
    "type": "momentum_return",
    "category": "momentum",
    "requires_position": False,
    "name": "모멘텀 수익률",
    "description": "N일 전 종가 대비 당일 종가의 수익률(%)이 임계값 조건을 충족하는지 판단합니다.",
    "sentence_template": "{period}일 수익률이 {value}% {operator_label}",
    "parameters": [
        {
            "name": "period",
            "label": "모멘텀 기간(일)",
            "input_type": "number",
            "default": 20,
            "min": 1,
            "max": 250,
        },
        {
            "name": "operator",
            "label": "비교",
            "input_type": "select",
            "options": [
                {"label": "초과", "value": ">"},
                {"label": "미만", "value": "<"},
                {"label": "이상", "value": ">="},
                {"label": "이하", "value": "<="},
            ],
            "default": ">",
        },
        {
            "name": "value",
            "label": "수익률 임계값(%)",
            "input_type": "number",
            "default": 10.0,
            "min": -100.0,
            "max": 1000.0,
        },
        {
            "name": "price_field",
            "label": "가격 기준",
            "input_type": "select",
            "options": [
                {"label": "수정 종가", "value": "adj_close"},
                {"label": "수정 시가", "value": "adj_open"},
            ],
            "default": "adj_close",
        },
    ],
    "allowed_in": ["entry", "exit_signal", "filters"],
}

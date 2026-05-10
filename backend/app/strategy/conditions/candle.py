"""봉차트 패턴 기반 시계열 조건 + 기타 가격 조건.

수록 조건:
    - bullish_candle: 양봉 + 몸통 비율 필터 (당일 OHLC 기반)
    - price_change_pct: 당일 가격 등락률(%) 임계값 비교

look-ahead bias 방지:
    - bullish_candle: 당일 OHLC만 사용 — 미래 데이터 불참조.
      도지봉(고가 == 저가)은 NaN으로 처리해 자동으로 False 처리.
    - price_change_pct: shift(1)로 전일 종가 사용 — 당일 데이터와 전일 데이터만 참조.
      첫 번째 행은 전일 데이터 없음 → NaN → False.
"""

from __future__ import annotations

import pandas as pd

from app.strategy.registry import condition_registry
from app.strategy.utils import compare

# ============================================================================
# bullish_candle
# ============================================================================


@condition_registry.register(
    "bullish_candle",
    requires_position=False,
    category="candle",
)
def bullish_candle(df: pd.DataFrame, condition: dict) -> pd.Series:
    """양봉 + 몸통 비율 조건.

    조건 충족 기준:
        1. 당일 종가 > 시가 (양봉)
        2. 몸통 비율(%) = (종가 - 시가) / (고가 - 저가) * 100 >= min_body_pct

    look-ahead bias 없음:
        당일 OHLC(adj_close, adj_open, adj_high, adj_low)만 사용.
        미래 데이터가 개입하지 않는다.

    도지봉 처리:
        고가 == 저가인 경우 고저 범위가 0이므로 float("nan")으로 대체 → 몸통 비율 NaN.
        NaN 비교는 pandas 기본 규칙상 False이므로 body_condition이 False가 된다.

    파라미터:
        min_body_pct (float): 몸통이 전체 봉 범위에서 차지하는 비율 하한(%).
            기본 30.0. 0.0이면 양봉이기만 하면 True.
    """
    min_body_pct = condition.get("min_body_pct", 30.0)

    # 조건 1: 양봉 (종가 > 시가)
    is_bullish = df["adj_close"] > df["adj_open"]

    # 조건 2: 몸통 비율
    # 고저 범위가 0인 도지봉은 NaN으로 처리 → 비율 NaN → body_condition False
    high_low_range = (df["adj_high"] - df["adj_low"]).replace(0, float("nan"))
    body_pct = (df["adj_close"] - df["adj_open"]).abs() / high_low_range * 100
    body_condition = body_pct >= min_body_pct  # NaN >= X → False (pandas 기본)

    result = is_bullish & body_condition
    return result.astype(bool)


BULLISH_CANDLE_META: dict = {
    "type": "bullish_candle",
    "category": "candle",
    "requires_position": False,
    "name": "양봉 (몸통 비율 조건)",
    "description": (
        "당일 종가가 시가보다 높은 양봉이고, "
        "몸통(종가-시가)이 전체 봉 범위(고가-저가)의 min_body_pct% 이상일 때 True입니다. "
        "도지봉(고가=저가) 및 음봉은 False입니다."
    ),
    "sentence_template": "양봉이고 몸통이 전체 범위의 {min_body_pct}% 이상",
    "parameters": [
        {
            "name": "min_body_pct",
            "label": "최소 몸통 비율(%)",
            "input_type": "number",
            "default": 30.0,
            "min": 0.0,
            "max": 100.0,
        },
    ],
    "allowed_in": ["entry", "filters"],
}


# ============================================================================
# price_change_pct
# ============================================================================


@condition_registry.register(
    "price_change_pct",
    requires_position=False,
    category="price",
)
def price_change_pct(df: pd.DataFrame, condition: dict) -> pd.Series:
    """당일 가격 등락률(%)이 임계값 조건을 충족하면 True.

    등락률% = (당일 가격 - 전일 가격) / 전일 가격 * 100

    look-ahead bias 없음:
        shift(1)로 전일 데이터를 사용하므로 당일과 전일 데이터만 참조한다.
        첫 번째 행은 전일 데이터가 없으므로 NaN → compare() → False.

    파라미터:
        operator (str): 비교 연산자. 기본 ">".
        value (float): 등락률 임계값(%). 기본 3.0.
        price_field (str): 가격 컬럼명. 기본 "adj_close" (정확성 정책 13.7).
    """
    operator = condition.get("operator", ">")
    value = condition.get("value", 3.0)
    price_field = condition.get("price_field", "adj_close")

    price = df[price_field]
    prev_price = price.shift(1)
    pct_change = (price - prev_price) / prev_price * 100
    result = compare(pct_change, operator, value)
    return result.fillna(False)


PRICE_CHANGE_PCT_META: dict = {
    "type": "price_change_pct",
    "category": "price",
    "requires_position": False,
    "name": "당일 가격 등락률",
    "description": (
        "당일 가격의 전일 대비 등락률(%)이 임계값 조건을 충족할 때 True입니다. "
        "첫 번째 행은 전일 데이터가 없으므로 항상 False입니다."
    ),
    "sentence_template": "{price_field_label}의 당일 등락률이 {value}% {operator_label}",
    "parameters": [
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
            "label": "등락률 임계값(%)",
            "input_type": "number",
            "default": 3.0,
            "min": -30.0,
            "max": 30.0,
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

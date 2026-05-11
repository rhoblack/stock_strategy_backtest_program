"""이동평균 기반 시계열 조건.

수록 조건:
    - price_vs_ma: 가격이 이동평균보다 위/아래
    - ma_cross: 골든크로스 / 데드크로스
    - ma_alignment: 삼선 정렬 (단기 > 중기 > 장기 또는 반대)
"""

from __future__ import annotations

import pandas as pd

from app.strategy.indicators import moving_average
from app.strategy.registry import condition_registry
from app.strategy.utils import compare

# ============================================================================
# price_vs_ma
# ============================================================================


@condition_registry.register(
    "price_vs_ma",
    requires_position=False,
    category="moving_average",
)
def price_vs_ma(df: pd.DataFrame, condition: dict) -> pd.Series:
    """가격이 N일 이동평균선보다 위(>)/아래(<)인지.

    파라미터:
        price_field (str): 가격 컬럼명. 기본 "adj_close" (정확성 정책 13.7).
        ma_period (int): 이동평균 기간.
        operator (str): ">" 또는 "<".
    """
    price_field = condition.get("price_field", "adj_close")
    ma_period = condition["ma_period"]
    operator = condition["operator"]

    series = df[price_field]
    ma = moving_average(series, ma_period)
    return compare(series, operator, ma)


PRICE_VS_MA_META: dict = {
    "type": "price_vs_ma",
    "category": "moving_average",
    "requires_position": False,
    "name": "가격과 이동평균 비교",
    "description": "지정한 가격이 N일 이동평균선보다 위 또는 아래인지 판단합니다.",
    "sentence_template": "{price_field_label}가 {ma_period}일 이동평균선보다 {operator_label}",
    "parameters": [
        {
            "name": "price_field",
            "label": "가격 기준",
            "input_type": "select",
            "options": [
                {"label": "수정 종가", "value": "adj_close"},
                {"label": "수정 시가", "value": "adj_open"},
                {"label": "수정 고가", "value": "adj_high"},
                {"label": "수정 저가", "value": "adj_low"},
            ],
            "default": "adj_close",
        },
        {
            "name": "ma_period",
            "label": "이동평균 기간(일)",
            "input_type": "number",
            "default": 20,
            "min": 2,
            "max": 300,
        },
        {
            "name": "operator",
            "label": "비교",
            "input_type": "select",
            "options": [
                {"label": "위", "value": ">"},
                {"label": "아래", "value": "<"},
            ],
            "default": ">",
        },
    ],
    "allowed_in": ["entry", "exit_signal", "filters"],
}


# ============================================================================
# ma_cross
# ============================================================================


@condition_registry.register(
    "ma_cross",
    requires_position=False,
    category="moving_average",
)
def ma_cross(df: pd.DataFrame, condition: dict) -> pd.Series:
    """단기 이동평균이 장기 이동평균을 상향/하향 돌파한 날.

    골든크로스: 전일 short_ma <= long_ma 이고 당일 short_ma > long_ma
    데드크로스: 전일 short_ma >= long_ma 이고 당일 short_ma < long_ma

    파라미터:
        short_period (int): 단기 이동평균 기간.
        long_period (int): 장기 이동평균 기간. short_period보다 커야 함.
        direction (str): "golden_cross" 또는 "dead_cross".
        price_field (str): 가격 컬럼명. 기본 "adj_close".
    """
    short_period = condition["short_period"]
    long_period = condition["long_period"]
    direction = condition["direction"]
    price_field = condition.get("price_field", "adj_close")

    if short_period >= long_period:
        raise ValueError(
            f"short_period({short_period})는 long_period({long_period})보다 작아야 합니다"
        )

    series = df[price_field]
    short_ma = moving_average(series, short_period)
    long_ma = moving_average(series, long_period)

    if direction == "golden_cross":
        return (short_ma.shift(1) <= long_ma.shift(1)) & (short_ma > long_ma)
    if direction == "dead_cross":
        return (short_ma.shift(1) >= long_ma.shift(1)) & (short_ma < long_ma)

    raise ValueError(
        f"지원하지 않는 direction입니다: {direction!r} (허용: 'golden_cross', 'dead_cross')"
    )


MA_CROSS_META: dict = {
    "type": "ma_cross",
    "category": "moving_average",
    "requires_position": False,
    "name": "이동평균 교차",
    "description": "단기 이동평균이 장기 이동평균을 돌파하는 시점을 잡습니다.",
    "sentence_template": "{short_period}일 이동평균이 {long_period}일 이동평균을 {direction_label}",
    "parameters": [
        {
            "name": "short_period",
            "label": "단기 기간(일)",
            "input_type": "number",
            "default": 5,
            "min": 2,
            "max": 100,
        },
        {
            "name": "long_period",
            "label": "장기 기간(일)",
            "input_type": "number",
            "default": 20,
            "min": 5,
            "max": 300,
        },
        {
            "name": "direction",
            "label": "방향",
            "input_type": "select",
            "options": [
                {"label": "상향 돌파(골든크로스)", "value": "golden_cross"},
                {"label": "하향 돌파(데드크로스)", "value": "dead_cross"},
            ],
            "default": "golden_cross",
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
    "allowed_in": ["entry", "exit_signal"],
}


# ============================================================================
# ma_alignment
# ============================================================================


@condition_registry.register(
    "ma_alignment",
    requires_position=False,
    category="moving_average",
)
def ma_alignment(df: pd.DataFrame, condition: dict) -> pd.Series:
    """단기·중기·장기 이동평균이 정렬된 날 True (삼선 정렬).

    상승 정렬(bullish): short_ma > mid_ma > long_ma
    하락 정렬(bearish): short_ma < mid_ma < long_ma

    look-ahead bias 없음: 각 MA는 rolling(window) 계산이며 당일까지의 데이터만
    포함한다. MA 간 대소 비교는 당일 값끼리의 관계이므로 미래 참조 없음.

    파라미터:
        short_period (int): 단기 이동평균 기간. 기본 5.
        mid_period (int): 중기 이동평균 기간. 기본 20.
        long_period (int): 장기 이동평균 기간. 기본 60.
        direction (str): "bullish" 또는 "bearish".
        price_field (str): 가격 컬럼명. 기본 "adj_close" (정확성 정책 13.7).
    """
    short_period = condition.get("short_period", 5)
    mid_period = condition.get("mid_period", 20)
    long_period = condition.get("long_period", 60)
    direction = condition.get("direction", "bullish")
    price_field = condition.get("price_field", "adj_close")

    if not (short_period < mid_period < long_period):
        raise ValueError(
            f"short_period({short_period}) < mid_period({mid_period}) < long_period({long_period}) "
            "순서를 만족해야 합니다"
        )
    if direction not in ("bullish", "bearish"):
        raise ValueError(
            f"지원하지 않는 direction입니다: {direction!r} (허용: 'bullish', 'bearish')"
        )

    series = df[price_field]
    short_ma = moving_average(series, short_period)
    mid_ma = moving_average(series, mid_period)
    long_ma = moving_average(series, long_period)

    if direction == "bullish":
        return (short_ma > mid_ma) & (mid_ma > long_ma)
    # direction == "bearish"
    return (short_ma < mid_ma) & (mid_ma < long_ma)


MA_ALIGNMENT_META: dict = {
    "type": "ma_alignment",
    "category": "moving_average",
    "requires_position": False,
    "name": "삼선 정렬",
    "description": "단기·중기·장기 이동평균이 정렬된 구간을 선별합니다 (상승: 단기>중기>장기, 하락: 반대).",
    "sentence_template": "{short_period}일·{mid_period}일·{long_period}일 이동평균이 {direction_label} 정렬",
    "parameters": [
        {
            "name": "short_period",
            "label": "단기 기간(일)",
            "input_type": "number",
            "default": 5,
            "min": 2,
            "max": 100,
        },
        {
            "name": "mid_period",
            "label": "중기 기간(일)",
            "input_type": "number",
            "default": 20,
            "min": 3,
            "max": 200,
        },
        {
            "name": "long_period",
            "label": "장기 기간(일)",
            "input_type": "number",
            "default": 60,
            "min": 5,
            "max": 500,
        },
        {
            "name": "direction",
            "label": "정렬 방향",
            "input_type": "select",
            "options": [
                {"label": "상승 정렬 (단기>중기>장기)", "value": "bullish"},
                {"label": "하락 정렬 (단기<중기<장기)", "value": "bearish"},
            ],
            "default": "bullish",
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
    "allowed_in": ["entry", "filters"],
}

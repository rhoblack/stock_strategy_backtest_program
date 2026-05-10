"""MACD 기반 시계열 조건.

수록 조건:
    - macd_cross: MACD 라인이 시그널 라인을 상향/하향 돌파하는 날 True
    - macd_histogram: MACD 히스토그램(macd_line - signal_line)이 임계값보다 위/아래

look-ahead bias 검증:
    - macd_cross: shift(1)으로 전일 상태를 참조해 당일 크로스만 감지. 미래 데이터 미참조.
    - macd_histogram: 당일 히스토그램 값 자체를 비교. 지표 계산은 EMA 누적이므로
      당일까지의 데이터만 사용. 미래 데이터 미참조.
"""

from __future__ import annotations

import pandas as pd

from app.strategy.indicators import macd as calc_macd
from app.strategy.registry import condition_registry
from app.strategy.utils import compare

# ============================================================================
# macd_cross
# ============================================================================


@condition_registry.register(
    "macd_cross",
    requires_position=False,
    category="macd",
)
def macd_cross(df: pd.DataFrame, condition: dict) -> pd.Series:
    """MACD 라인이 시그널 라인을 상향/하향 돌파하는 날 True.

    골든크로스: 전일 macd_line <= signal_line 이고 당일 macd_line > signal_line
    데드크로스: 전일 macd_line >= signal_line 이고 당일 macd_line < signal_line

    look-ahead bias 없음: shift(1)으로 전일 상태를 참조하며, 당일 크로스 발생만 감지.

    파라미터:
        fast (int): 단기 EMA 기간. 기본 12.
        slow (int): 장기 EMA 기간. 기본 26. fast보다 커야 함.
        signal (int): 시그널 EMA 기간. 기본 9.
        direction (str): "golden_cross" 또는 "dead_cross".
        price_field (str): 가격 컬럼명. 기본 "adj_close" (정확성 정책 13.7).
    """
    fast = condition.get("fast", 12)
    slow = condition.get("slow", 26)
    signal = condition.get("signal", 9)
    direction = condition.get("direction", "golden_cross")
    price_field = condition.get("price_field", "adj_close")

    # fast < slow 유효성 검사는 calc_macd 내부에서 수행
    macd_line, signal_line, _ = calc_macd(df[price_field], fast=fast, slow=slow, signal=signal)

    if direction == "golden_cross":
        return (macd_line.shift(1) <= signal_line.shift(1)) & (macd_line > signal_line)
    if direction == "dead_cross":
        return (macd_line.shift(1) >= signal_line.shift(1)) & (macd_line < signal_line)

    raise ValueError(
        f"지원하지 않는 direction입니다: {direction!r} (허용: 'golden_cross', 'dead_cross')"
    )


MACD_CROSS_META: dict = {
    "type": "macd_cross",
    "category": "macd",
    "requires_position": False,
    "name": "MACD 교차",
    "description": "MACD 라인이 시그널 라인을 상향 또는 하향 돌파하는 시점을 잡습니다.",
    "sentence_template": "MACD({fast},{slow},{signal})가 시그널 라인을 {direction_label}",
    "parameters": [
        {
            "name": "fast",
            "label": "단기 EMA 기간",
            "input_type": "number",
            "default": 12,
            "min": 2,
            "max": 100,
        },
        {
            "name": "slow",
            "label": "장기 EMA 기간",
            "input_type": "number",
            "default": 26,
            "min": 3,
            "max": 300,
        },
        {
            "name": "signal",
            "label": "시그널 EMA 기간",
            "input_type": "number",
            "default": 9,
            "min": 2,
            "max": 100,
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
# macd_histogram
# ============================================================================


@condition_registry.register(
    "macd_histogram",
    requires_position=False,
    category="macd",
)
def macd_histogram(df: pd.DataFrame, condition: dict) -> pd.Series:
    """MACD 히스토그램(macd_line - signal_line)이 임계값보다 위/아래.

    히스토그램이 양수이면 MACD 라인이 시그널 라인 위 (상승 모멘텀).
    히스토그램이 음수이면 MACD 라인이 시그널 라인 아래 (하락 모멘텀).

    look-ahead bias 없음: 히스토그램은 EMA 누적 계산으로 당일까지의 데이터만 사용.

    파라미터:
        fast (int): 단기 EMA 기간. 기본 12.
        slow (int): 장기 EMA 기간. 기본 26.
        signal (int): 시그널 EMA 기간. 기본 9.
        operator (str): 비교 연산자. ">" / ">=" / "<" / "<=".
        value (float): 히스토그램 임계값. 기본 0.0.
        price_field (str): 가격 컬럼명. 기본 "adj_close" (정확성 정책 13.7).
    """
    fast = condition.get("fast", 12)
    slow = condition.get("slow", 26)
    signal = condition.get("signal", 9)
    operator = condition.get("operator", ">")
    value = condition.get("value", 0.0)
    price_field = condition.get("price_field", "adj_close")

    _, _, histogram = calc_macd(df[price_field], fast=fast, slow=slow, signal=signal)
    return compare(histogram, operator, value)


MACD_HISTOGRAM_META: dict = {
    "type": "macd_histogram",
    "category": "macd",
    "requires_position": False,
    "name": "MACD 히스토그램 비교",
    "description": "MACD 히스토그램(MACD 라인 - 시그널 라인)이 지정한 임계값보다 위 또는 아래인지 판단합니다.",
    "sentence_template": "MACD({fast},{slow},{signal}) 히스토그램이 {value} {operator_label}",
    "parameters": [
        {
            "name": "fast",
            "label": "단기 EMA 기간",
            "input_type": "number",
            "default": 12,
            "min": 2,
            "max": 100,
        },
        {
            "name": "slow",
            "label": "장기 EMA 기간",
            "input_type": "number",
            "default": 26,
            "min": 3,
            "max": 300,
        },
        {
            "name": "signal",
            "label": "시그널 EMA 기간",
            "input_type": "number",
            "default": 9,
            "min": 2,
            "max": 100,
        },
        {
            "name": "operator",
            "label": "비교",
            "input_type": "select",
            "options": [
                {"label": "초과", "value": ">"},
                {"label": "이상", "value": ">="},
                {"label": "미만", "value": "<"},
                {"label": "이하", "value": "<="},
            ],
            "default": ">",
        },
        {
            "name": "value",
            "label": "임계값",
            "input_type": "number",
            "default": 0.0,
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

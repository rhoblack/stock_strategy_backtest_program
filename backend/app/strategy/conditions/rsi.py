"""RSI 기반 시계열 조건.

수록 조건:
    - rsi_level: RSI가 임계값보다 위/아래
    - rsi_cross: RSI가 임계선을 상향/하향 돌파한 날

look-ahead bias 검증:
    - rsi_cross: shift(1)으로 전일 RSI를 참조해 당일 크로스만 감지. 미래 데이터 미참조.
"""

from __future__ import annotations

import pandas as pd

from app.strategy.indicators import rsi
from app.strategy.registry import condition_registry
from app.strategy.utils import compare


@condition_registry.register(
    "rsi_level",
    requires_position=False,
    category="rsi",
)
def rsi_level(df: pd.DataFrame, condition: dict) -> pd.Series:
    """RSI가 기준값보다 큼/작음/이상/이하.

    파라미터:
        period (int): RSI 기간. 기본 14.
        operator (str): 비교 연산자.
        value (float): RSI 기준값 (0~100).
        price_field (str): 기준 가격 컬럼. 기본 "adj_close".
    """
    period = condition.get("period", 14)
    operator = condition["operator"]
    value = condition["value"]
    price_field = condition.get("price_field", "adj_close")

    if not 0 <= value <= 100:
        raise ValueError(f"RSI value는 0~100 범위여야 합니다: {value}")

    rsi_series = rsi(df[price_field], period=period)
    return compare(rsi_series, operator, value)


RSI_LEVEL_META: dict = {
    "type": "rsi_level",
    "category": "rsi",
    "requires_position": False,
    "name": "RSI 기준값",
    "description": "RSI(N)가 지정한 기준값보다 위 또는 아래인지 판단합니다.",
    "sentence_template": "RSI({period})가 {value} {operator_label}",
    "parameters": [
        {
            "name": "period",
            "label": "RSI 기간",
            "input_type": "number",
            "default": 14,
            "min": 2,
            "max": 100,
        },
        {
            "name": "operator",
            "label": "비교",
            "input_type": "select",
            "options": [
                {"label": "이상", "value": ">="},
                {"label": "초과", "value": ">"},
                {"label": "이하", "value": "<="},
                {"label": "미만", "value": "<"},
            ],
            "default": "<=",
        },
        {
            "name": "value",
            "label": "기준값",
            "input_type": "number",
            "default": 70,
            "min": 0,
            "max": 100,
        },
    ],
    "allowed_in": ["entry", "exit_signal", "filters"],
}


# ============================================================================
# rsi_cross
# ============================================================================


@condition_registry.register(
    "rsi_cross",
    requires_position=False,
    category="rsi",
)
def rsi_cross(df: pd.DataFrame, condition: dict) -> pd.Series:
    """RSI가 임계선을 상향/하향 돌파한 날 True.

    cross_above (과매도 탈출, 매수 신호):
        전일 RSI < threshold 이고 당일 RSI >= threshold
    cross_below (과매수 탈출, 매도 신호):
        전일 RSI > threshold 이고 당일 RSI <= threshold

    look-ahead bias 없음: shift(1)으로 전일 RSI를 참조하며, 당일 크로스 발생만 감지.

    파라미터:
        period (int): RSI 기간. 기본 14.
        threshold (float): 크로스 기준선 (0~100). 기본 30.
        direction (str): "cross_above" 또는 "cross_below".
        price_field (str): 가격 컬럼명. 기본 "adj_close" (정확성 정책 13.7).
    """
    period = condition.get("period", 14)
    threshold = condition.get("threshold", 30)
    direction = condition.get("direction", "cross_above")
    price_field = condition.get("price_field", "adj_close")

    if not 0 <= threshold <= 100:
        raise ValueError(f"threshold는 0~100 범위여야 합니다: {threshold}")
    if direction not in ("cross_above", "cross_below"):
        raise ValueError(
            f"지원하지 않는 direction입니다: {direction!r} (허용: 'cross_above', 'cross_below')"
        )

    rsi_series = rsi(df[price_field], period=period)

    if direction == "cross_above":
        return (rsi_series.shift(1) < threshold) & (rsi_series >= threshold)
    # direction == "cross_below"
    return (rsi_series.shift(1) > threshold) & (rsi_series <= threshold)


RSI_CROSS_META: dict = {
    "type": "rsi_cross",
    "category": "rsi",
    "requires_position": False,
    "name": "RSI 크로스",
    "description": "RSI(N)가 기준선을 상향 또는 하향 돌파하는 시점을 감지합니다.",
    "sentence_template": "RSI({period})가 {threshold}를 {direction_label}",
    "parameters": [
        {
            "name": "period",
            "label": "RSI 기간",
            "input_type": "number",
            "default": 14,
            "min": 2,
            "max": 100,
        },
        {
            "name": "threshold",
            "label": "기준선",
            "input_type": "number",
            "default": 30,
            "min": 0,
            "max": 100,
        },
        {
            "name": "direction",
            "label": "돌파 방향",
            "input_type": "select",
            "options": [
                {"label": "상향 돌파 (과매도 탈출)", "value": "cross_above"},
                {"label": "하향 돌파 (과매수 탈출)", "value": "cross_below"},
            ],
            "default": "cross_above",
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

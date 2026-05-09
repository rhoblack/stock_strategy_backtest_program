"""RSI 기반 시계열 조건.

수록 조건:
    - rsi_level: RSI가 임계값보다 위/아래
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

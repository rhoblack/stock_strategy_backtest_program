"""거래량 기반 시계열 조건.

수록 조건:
    - volume_ratio: 거래량이 N일 평균의 몇 배
"""

from __future__ import annotations

import pandas as pd

from app.strategy.indicators import moving_average
from app.strategy.registry import condition_registry
from app.strategy.utils import compare


@condition_registry.register(
    "volume_ratio",
    requires_position=False,
    category="volume",
)
def volume_ratio(df: pd.DataFrame, condition: dict) -> pd.Series:
    """거래량이 N일 평균 거래량의 X배 이상/이하인지.

    파라미터:
        period (int): 평균 기간. 기본 20.
        operator (str): 비교 연산자.
        value (float): 비율 임계값. 예) 2.0 → 2배.
        volume_field (str): 거래량 컬럼명. 기본 "adj_volume" (정확성 정책 13.7).
    """
    period = condition.get("period", 20)
    operator = condition["operator"]
    value = condition["value"]
    volume_field = condition.get("volume_field", "adj_volume")

    volume = df[volume_field]
    volume_ma = moving_average(volume, period)
    ratio = volume / volume_ma
    return compare(ratio, operator, value)


VOLUME_RATIO_META: dict = {
    "type": "volume_ratio",
    "category": "volume",
    "requires_position": False,
    "name": "거래량이 평균 대비 N배",
    "description": "당일 거래량이 N일 평균 거래량의 몇 배인지 비교합니다.",
    "sentence_template": "거래량이 {period}일 평균의 {value}배 {operator_label}",
    "parameters": [
        {
            "name": "period",
            "label": "평균 기간(일)",
            "input_type": "number",
            "default": 20,
            "min": 2,
            "max": 200,
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
            "default": ">=",
        },
        {
            "name": "value",
            "label": "배수",
            "input_type": "number",
            "default": 2.0,
            "min": 0.1,
            "max": 100.0,
        },
    ],
    "allowed_in": ["entry", "filters"],
}

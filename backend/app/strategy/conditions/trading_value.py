"""거래대금 및 시장 지수 기반 시계열 조건.

수록 조건:
    - avg_trading_value: N일 평균 거래대금이 임계값 이상 (유동성 필터)
    - market_index_filter: 시장 지수 당일 등락률 조건
"""

from __future__ import annotations

import pandas as pd

from app.strategy.registry import condition_registry
from app.strategy.utils import compare

# ============================================================================
# avg_trading_value
# ============================================================================


@condition_registry.register(
    "avg_trading_value",
    requires_position=False,
    category="volume",
)
def avg_trading_value(df: pd.DataFrame, condition: dict) -> pd.Series:
    """N일 평균 거래대금이 임계값보다 크면 True (유동성 필터).

    거래대금 = close * volume (CLAUDE.md 정책 #5: close는 거래대금 필터에 사용).
    단위는 억원 (/ 1e8).

    look-ahead bias 없음: rolling(period, min_periods=period)는 당일 포함이지만,
    당일 장 마감 후 종가·거래량으로 계산한 값이므로 다음날 체결 기준에서
    미래 데이터 참조가 아니다. (정확성 정책 13.15)

    파라미터:
        period (int): 평균 기간. 기본 20.
        operator (str): 비교 연산자. 기본 ">=".
        value (float): 거래대금 임계값 (억원). 기본 30.0.
    """
    period = condition.get("period", 20)
    operator = condition.get("operator", ">=")
    value = condition.get("value", 30.0)

    trading_value = df["close"] * df["volume"] / 1e8
    avg_tv = trading_value.rolling(period, min_periods=period).mean()
    return compare(avg_tv, operator, value)


AVG_TRADING_VALUE_META: dict = {
    "type": "avg_trading_value",
    "category": "volume",
    "requires_position": False,
    "name": "평균 거래대금 필터",
    "description": (
        "N일 평균 거래대금(억원)이 임계값 이상인지 확인합니다. "
        "유동성이 낮은 종목을 사전에 걸러내는 필터 조건으로 주로 사용합니다."
    ),
    "sentence_template": "{period}일 평균 거래대금이 {value}억원 {operator_label}",
    "parameters": [
        {
            "name": "period",
            "label": "평균 기간(일)",
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
                {"label": "이상", "value": ">="},
                {"label": "초과", "value": ">"},
                {"label": "이하", "value": "<="},
                {"label": "미만", "value": "<"},
            ],
            "default": ">=",
        },
        {
            "name": "value",
            "label": "거래대금 임계값(억원)",
            "input_type": "number",
            "default": 30.0,
            "min": 0.1,
            "max": 100000.0,
        },
    ],
    "allowed_in": ["entry", "filters"],
}


# ============================================================================
# market_index_filter
# ============================================================================


@condition_registry.register(
    "market_index_filter",
    requires_position=False,
    category="market",
)
def market_index_filter(df: pd.DataFrame, condition: dict) -> pd.Series:
    """시장 지수 당일 등락률(%)이 조건을 만족하면 True.

    df에 `index_col` 파라미터로 지정한 컬럼이 없으면 모두 False를 반환한다
    (graceful degradation). BacktestEngine이 시장 지수 데이터를 주입하지 않은
    경우에도 조건 평가가 중단되지 않는다.

    look-ahead bias 없음: 당일 시장 지수 등락률은 당일 장 마감 후 확정된 값이며,
    다음날 체결 기준에서 미래 데이터 참조가 아니다.

    파라미터:
        index_col (str): 시장 지수 등락률 컬럼명. 기본 "market_index_return".
        operator (str): 비교 연산자. 기본 ">".
        value (float): 등락률 임계값(%). 기본 0.0.
    """
    index_col = condition.get("index_col", "market_index_return")
    operator = condition.get("operator", ">")
    value = condition.get("value", 0.0)

    if index_col not in df.columns:
        return pd.Series(False, index=df.index)

    return compare(df[index_col], operator, value)


MARKET_INDEX_FILTER_META: dict = {
    "type": "market_index_filter",
    "category": "market",
    "requires_position": False,
    "name": "시장 지수 등락률 필터",
    "description": (
        "KOSPI/KOSDAQ 등 시장 지수의 당일 등락률(%)이 임계값 조건을 만족하는지 확인합니다. "
        "시장 전체가 하락하는 날에는 매수를 억제하는 용도로 사용합니다."
    ),
    "sentence_template": "{index_col_label}이 {value}% {operator_label}",
    "parameters": [
        {
            "name": "index_col",
            "label": "지수 컬럼",
            "input_type": "select",
            "options": [
                {"label": "시장 지수 (기본)", "value": "market_index_return"},
                {"label": "KOSPI 등락률", "value": "kospi_return"},
                {"label": "KOSDAQ 등락률", "value": "kosdaq_return"},
            ],
            "default": "market_index_return",
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
            "default": ">",
        },
        {
            "name": "value",
            "label": "등락률 기준(%)",
            "input_type": "number",
            "default": 0.0,
            "min": -30.0,
            "max": 30.0,
        },
    ],
    "allowed_in": ["entry", "filters"],
}

"""포지션 기반 매도 조건 (exit_position).

수록 조건:
    - take_profit: 수익률이 +N% 이상 도달 시 익절

정확성 정책 13.3절을 따른다:
    - trigger="intraday_high" (기본): 당일 고가가 익절선에 도달하면 익절선 가격에 체결
    - trigger="close": 당일 종가 기준 평가
    - 갭 업으로 시가가 이미 익절선을 넘어선 경우는 BacktestEngine의
      `evaluate_exit_position`이 별도로 시가 체결 처리 (gap_up_take_profit).
      여기서는 일중 도달만 판정.

함수 시그니처:
    take_profit(position, market_row, condition) -> tuple[bool, str | None]

`position`은 `entry_price` 속성을 가진 객체로 가정 (Position/TradeGroup은 Step 7).
`market_row`는 `adj_high`, `adj_low`, `adj_close` 키를 갖는 dict-like 또는
pandas Series row.
"""

from __future__ import annotations

from typing import Any

from app.strategy.registry import condition_registry


@condition_registry.register(
    "take_profit",
    requires_position=True,
    category="exit_position",
)
def take_profit(
    position: Any,
    market_row: Any,
    condition: dict,
) -> tuple[bool, str | None]:
    """수익률이 +percent% 이상 도달 시 익절.

    파라미터:
        percent (float): 익절 임계 수익률 (%, 양수). 예) 7.0
        trigger (str): "intraday_high" (기본) 또는 "close".
    """
    percent = condition["percent"]
    trigger = condition.get("trigger", "intraday_high")

    if percent <= 0:
        raise ValueError(f"percent는 양수여야 합니다: {percent}")

    target_price = position.entry_price * (1 + percent / 100)

    if trigger == "intraday_high":
        if market_row["adj_high"] >= target_price:
            return True, "take_profit"
    elif trigger == "close":
        if market_row["adj_close"] >= target_price:
            return True, "take_profit"
    else:
        raise ValueError(
            f"지원하지 않는 trigger입니다: {trigger!r} (허용: 'intraday_high', 'close')"
        )

    return False, None


TAKE_PROFIT_META: dict = {
    "type": "take_profit",
    "category": "exit_position",
    "requires_position": True,
    "name": "익절",
    "description": "보유 종목의 수익률이 지정한 % 이상 도달하면 매도합니다.",
    "sentence_template": "수익률이 +{percent}% 이상이면 익절 ({trigger_label} 기준)",
    "parameters": [
        {
            "name": "percent",
            "label": "익절 수익률(%)",
            "input_type": "number",
            "default": 7.0,
            "min": 0.1,
            "max": 1000.0,
        },
        {
            "name": "trigger",
            "label": "도달 판정 기준",
            "input_type": "select",
            "options": [
                {"label": "일중 고가 도달", "value": "intraday_high"},
                {"label": "당일 종가", "value": "close"},
            ],
            "default": "intraday_high",
        },
    ],
    "allowed_in": ["exit_position"],
}

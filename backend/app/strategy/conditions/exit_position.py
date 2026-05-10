"""포지션 기반 매도 조건 (exit_position).

수록 조건:
    - take_profit: 수익률이 +N% 이상 도달 시 익절
    - stop_loss: 손실률이 -N% 이상 도달 시 손절
    - max_holding_days: 보유일수가 N일 이상이면 종가 청산
    - trailing_stop: peak 대비 N% 하락 시 청산

정확성 정책 13.3절을 따른다:
    - trigger="intraday_high"/"intraday_low" (기본):
      당일 고가/저가가 임계선에 도달하면 임계선 가격에 체결
    - trigger="close": 당일 종가 기준 평가
    - 갭으로 시가가 이미 임계선을 넘어선 경우는 BacktestEngine이
      별도로 시가 체결 처리 (gap_down_stop_loss / gap_up_take_profit).
      여기서는 일중 도달만 판정.
    - 동일 봉 stop_loss + take_profit 동시 도달 시 stop 우선 (13.3.2)
      정책은 BacktestEngine의 우선순위 정렬에서 처리하므로,
      각 함수는 자기 조건만 boolean으로 반환한다.

trailing_stop의 peak_price는 position.peak_price를 그대로 읽어 평가만 한다.
peak 갱신은 Portfolio.update_market_price가 담당하며, 정확성 정책 13.3.5에 따라
"전일까지의 high"를 사용한다 (look-ahead bias 방지).

함수 시그니처 (design 03 §14):
    cond(position, market_row, condition) -> tuple[bool, str | None]

`position`은 다음 속성을 가진 객체로 가정:
    - entry_price (float): 매수 평단가 (또는 단일 lot의 entry_price)
    - first_entry_date (date): 가장 오래된 trade_group의 entry_date (max_holding_days용)
    - peak_price (float): 보유 기간 동안의 최고가 (trailing_stop용)

`market_row`는 `adj_high`, `adj_low`, `adj_close` 키를 갖는 dict-like 또는
pandas Series row. max_holding_days는 추가로 `date` 키나
DatetimeIndex 기반의 `.name`을 사용한다.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Any

from app.strategy.registry import condition_registry

# ============================================================================
# take_profit
# ============================================================================


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


# ============================================================================
# stop_loss
# ============================================================================


@condition_registry.register(
    "stop_loss",
    requires_position=True,
    category="exit_position",
)
def stop_loss(
    position: Any,
    market_row: Any,
    condition: dict,
) -> tuple[bool, str | None]:
    """손실률이 -percent% 이상 도달 시 손절 (정확성 정책 13.3.1).

    파라미터:
        percent (float): 손절 임계 손실률 (%, 양수). 예) 3.0 → -3% 도달 시 손절.
        trigger (str): "intraday_low" (기본) 또는 "close".

    동작 (일중 도달 판정만 담당):
        - intraday_low: market_row["adj_low"] <= entry_price * (1 - percent/100)
        - close:        market_row["adj_close"] <= entry_price * (1 - percent/100)

    갭 다운 (시가가 이미 손절선을 돌파)은 BacktestEngine이 별도로
    "gap_down_stop_loss"로 처리하므로 본 함수는 일중 도달만 판정한다.

    동일 봉 take_profit과 동시 도달 시 손절 우선 정책(13.3.2)은 BacktestEngine의
    우선순위 정렬에서 처리한다. 본 함수는 자기 조건만 평가한다.
    """
    percent = condition["percent"]
    trigger = condition.get("trigger", "intraday_low")

    if percent <= 0:
        raise ValueError(f"percent는 양수여야 합니다: {percent}")

    stop_price = position.entry_price * (1 - percent / 100)

    if trigger == "intraday_low":
        if market_row["adj_low"] <= stop_price:
            return True, "stop_loss"
    elif trigger == "close":
        if market_row["adj_close"] <= stop_price:
            return True, "stop_loss"
    else:
        raise ValueError(
            f"지원하지 않는 trigger입니다: {trigger!r} (허용: 'intraday_low', 'close')"
        )

    return False, None


STOP_LOSS_META: dict = {
    "type": "stop_loss",
    "category": "exit_position",
    "requires_position": True,
    "name": "손절",
    "description": "보유 종목의 손실률이 지정한 % 이상 도달하면 매도합니다.",
    "sentence_template": "손실률이 -{percent}% 이상이면 손절 ({trigger_label} 기준)",
    "parameters": [
        {
            "name": "percent",
            "label": "손절 손실률(%)",
            "input_type": "number",
            "default": 3.0,
            "min": 0.1,
            "max": 100.0,
        },
        {
            "name": "trigger",
            "label": "도달 판정 기준",
            "input_type": "select",
            "options": [
                {"label": "일중 저가 도달", "value": "intraday_low"},
                {"label": "당일 종가", "value": "close"},
            ],
            "default": "intraday_low",
        },
    ],
    "allowed_in": ["exit_position"],
}


# ============================================================================
# max_holding_days
# ============================================================================


def _row_date(market_row: Any) -> date_type:
    """market_row에서 거래일 date를 추출.

    우선순위:
        1. dict-like의 "date" 키
        2. pandas Series의 .name (DatetimeIndex)
    datetime/Timestamp는 .date()로 변환.
    """
    candidate = None

    # dict 또는 pandas Series — "date" 키 우선
    try:
        candidate = market_row["date"]
    except (KeyError, TypeError, IndexError):
        candidate = None

    if candidate is None:
        # pandas Series의 인덱스 라벨
        candidate = getattr(market_row, "name", None)

    if candidate is None:
        raise ValueError(
            "market_row에서 거래일을 찾을 수 없습니다. "
            "'date' 키 또는 DatetimeIndex 기반 Series.name을 제공하세요."
        )

    if hasattr(candidate, "date") and not isinstance(candidate, date_type):
        # pd.Timestamp나 datetime.datetime은 .date()로 변환
        return candidate.date()
    if isinstance(candidate, datetime):
        return candidate.date()
    if isinstance(candidate, date_type):
        return candidate
    raise TypeError(
        f"market_row의 거래일 타입이 지원되지 않습니다: {type(candidate)!r}"
    )


@condition_registry.register(
    "max_holding_days",
    requires_position=True,
    category="exit_position",
)
def max_holding_days(
    position: Any,
    market_row: Any,
    condition: dict,
) -> tuple[bool, str | None]:
    """보유일수가 N일 이상이면 청산 (당일 종가 기준).

    파라미터:
        days (int): 최대 보유일수 (양수). 예) 10 → 10일 이상 보유 시 청산.

    동작:
        holding_days = (today - position.first_entry_date).days
        holding_days >= days 이면 트리거.

    체결 시점은 BacktestEngine이 결정 (정책상 당일 종가 청산).
    """
    days = condition["days"]
    if days <= 0:
        raise ValueError(f"days는 양수여야 합니다: {days}")
    if not isinstance(days, int):
        # JSON에서 들어온 수치가 float이어도 정수 의미면 허용
        if isinstance(days, float) and days.is_integer():
            days = int(days)
        else:
            raise ValueError(f"days는 정수여야 합니다: {days!r}")

    today = _row_date(market_row)
    first_entry = position.first_entry_date

    if hasattr(first_entry, "date") and not isinstance(first_entry, date_type):
        first_entry = first_entry.date()
    if isinstance(first_entry, datetime):
        first_entry = first_entry.date()

    holding_days = (today - first_entry).days
    if holding_days >= days:
        return True, "max_holding_days"
    return False, None


MAX_HOLDING_DAYS_META: dict = {
    "type": "max_holding_days",
    "category": "exit_position",
    "requires_position": True,
    "name": "최대 보유일",
    "description": "보유일수가 지정한 일수 이상이면 종가에 청산합니다.",
    "sentence_template": "보유일수가 {days}일 이상이면 종가 청산",
    "parameters": [
        {
            "name": "days",
            "label": "최대 보유일(거래일 기준 아님 — 달력일)",
            "input_type": "number",
            "default": 10,
            "min": 1,
            "max": 3650,
        },
    ],
    "allowed_in": ["exit_position"],
}


# ============================================================================
# trailing_stop
# ============================================================================


@condition_registry.register(
    "trailing_stop",
    requires_position=True,
    category="exit_position",
)
def trailing_stop(
    position: Any,
    market_row: Any,
    condition: dict,
) -> tuple[bool, str | None]:
    """peak 대비 percent% 하락 시 청산 (정확성 정책 13.3.5).

    파라미터:
        percent (float): peak 대비 하락률 임계값 (%, 양수). 예) 5.0
        trigger (str): "intraday_low" (기본) 또는 "close".

    동작 (look-ahead bias 방지):
        peak_price는 position.peak_price를 그대로 읽어 평가만 한다.
        peak 갱신 책임은 Portfolio.update_market_price가 담당하며,
        13.3.5에 따라 "전일까지의 high"여야 한다.
        본 함수는 절대로 peak_price를 갱신하지 않는다.

        손절선 = position.peak_price * (1 - percent/100)
        - intraday_low: market_row["adj_low"] <= 손절선
        - close:        market_row["adj_close"] <= 손절선
    """
    percent = condition["percent"]
    trigger = condition.get("trigger", "intraday_low")

    if percent <= 0:
        raise ValueError(f"percent는 양수여야 합니다: {percent}")

    peak_price = position.peak_price
    if peak_price is None or peak_price <= 0:
        # peak이 미설정/0이면 평가 불가 — 트리거 안 함 (보수적)
        return False, None

    stop_price = peak_price * (1 - percent / 100)

    if trigger == "intraday_low":
        if market_row["adj_low"] <= stop_price:
            return True, "trailing_stop"
    elif trigger == "close":
        if market_row["adj_close"] <= stop_price:
            return True, "trailing_stop"
    else:
        raise ValueError(
            f"지원하지 않는 trigger입니다: {trigger!r} (허용: 'intraday_low', 'close')"
        )

    return False, None


TRAILING_STOP_META: dict = {
    "type": "trailing_stop",
    "category": "exit_position",
    "requires_position": True,
    "name": "트레일링 스탑",
    "description": "보유 기간 최고가 대비 지정한 % 이상 하락하면 매도합니다.",
    "sentence_template": "최고가 대비 -{percent}% 하락 시 청산 ({trigger_label} 기준)",
    "parameters": [
        {
            "name": "percent",
            "label": "최고가 대비 하락률(%)",
            "input_type": "number",
            "default": 5.0,
            "min": 0.1,
            "max": 100.0,
        },
        {
            "name": "trigger",
            "label": "도달 판정 기준",
            "input_type": "select",
            "options": [
                {"label": "일중 저가 도달", "value": "intraday_low"},
                {"label": "당일 종가", "value": "close"},
            ],
            "default": "intraday_low",
        },
    ],
    "allowed_in": ["exit_position"],
}

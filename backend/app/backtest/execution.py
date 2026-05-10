"""ExecutionModel — 체결 가격 / 비용 / 호가 단위 처리.

설계서 04번 7~9절 + 정확성 정책 13.5(호가) / 13.6(세율 시계열) / 13.7(수정주가).

순환 import를 피하기 위해 Portfolio/Position을 직접 참조하지 않는다.
호출자가 가격/수량/날짜를 넘겨주면 비용/수익을 계산해 ExecutionResult를 반환한다.

`calculate_buy_cost` / `calculate_sell_proceeds`는 단일 float이 아닌
`ExecutionResult` dataclass로 분해 결과를 노출한다 — Portfolio.trade_logs와
DB TradeExecution이 fee/tax/net을 분해 영속화할 수 있도록 함 (리뷰 011 H1 + M4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

from app.backtest.tick import round_to_tick


@dataclass(frozen=True)
class TaxRateEntry:
    """시계열 세율 한 항목: from_date 이후부터 rate 적용."""

    from_date: date_type
    rate: float


@dataclass(frozen=True)
class ExecutionResult:
    """체결 1건의 비용 분해 결과.

    Portfolio.trade_logs / DB TradeExecution / cash_events가 동일한 분해를
    영속화할 수 있도록 단일 dataclass로 노출한다 (리뷰 011 H1 + M4 해소).

    Fields
    ------
    side : "buy" | "sell"
    raw_price : 슬리피지 적용 전 입력 가격 (감사용, float — 소수 허용)
    price : 슬리피지+호가 단위 적용 후 체결가 (정수, KRW)
    quantity : 체결 수량
    gross_amount : price * quantity (비용 차감 전 거래대금, 정수 KRW)
    fee : 수수료 = gross * fee_rate, 원 단위 정수 (BUY/SELL 모두 계산)
    tax : 거래세 = gross * tax_rate(on_date), 원 단위 정수 (BUY=0, SELL만 계산)
    net_amount : 실제 현금 흐름, 원 단위 정수
        - BUY  : gross + fee  (예수금에서 빠져나가는 총액)
        - SELL : gross - fee - tax (예수금에 들어오는 순수익)
    slippage_applied : 슬리피지로 인한 비용 차이, 원 단위 정수 (감사용)

    정확성 정책 §14: 모든 금액은 KRW 정수. 소수 반올림은 int()를 통해 수행하며
    banker's rounding을 피하기 위해 _round_krw() 헬퍼를 사용한다.
    """

    side: str
    raw_price: float
    price: int
    quantity: int
    gross_amount: int
    fee: int
    tax: int
    net_amount: int
    slippage_applied: int

    def to_log_dict(self) -> dict:
        """Portfolio.trade_logs의 비용 분해 키로 펼쳐 넣을 수 있는 dict.

        Portfolio가 자체적으로 채우는 키(date / symbol / trade_group_id /
        execution_type / reason 등)는 포함하지 않는다 — 호출자가 합쳐서 사용.
        모든 금액 필드는 정수 KRW (정확성 정책 §14).
        """
        return {
            "price": self.price,
            "quantity": self.quantity,
            "gross_amount": self.gross_amount,
            "fee": self.fee,
            "tax": self.tax,
            "net_amount": self.net_amount,
            "slippage_applied": self.slippage_applied,
        }


def _round_krw(value: float) -> int:
    """금액을 원 단위 정수로 반올림.

    Python 내장 round()는 banker's rounding(짝수 반올림)을 사용하므로
    0.5 미만은 내림, 정확히 0.5는 가장 가까운 짝수로 처리된다.
    정확성 정책 §14: 부동소수 오차 방지를 위해 math.floor(x + 0.5)를 사용.
    이는 "반올림에서는 항상 올림"(round-half-up) 방식으로, 수수료/세금 계산에서
    0.5원 단위가 발생할 때 일관되게 처리한다.
    """
    return math.floor(value + 0.5)


# tax_rate 인자는 다음 셋 중 하나:
#   float (전 기간 동일)
#   list[TaxRateEntry]
#   list[dict] {"from": "2023-01-01" | date, "rate": 0.0020}
TaxRateLike = float | list[dict[str, Any]] | list[TaxRateEntry]


def _normalize_tax_rate(tax_rate: TaxRateLike) -> float | list[TaxRateEntry]:
    """list[dict] → list[TaxRateEntry] 변환. float는 그대로."""
    if isinstance(tax_rate, (int, float)):
        return float(tax_rate)
    entries: list[TaxRateEntry] = []
    for item in tax_rate:
        if isinstance(item, TaxRateEntry):
            entries.append(item)
            continue
        from_value = item["from"]
        if isinstance(from_value, str):
            from_date = date_type.fromisoformat(from_value)
        elif isinstance(from_value, date_type):
            from_date = from_value
        else:
            raise TypeError(f"tax_rate.from은 str(ISO) 또는 date여야 합니다: {from_value!r}")
        entries.append(TaxRateEntry(from_date=from_date, rate=float(item["rate"])))
    # from_date 오름차순 보장
    entries.sort(key=lambda e: e.from_date)
    return entries


class ExecutionModel:
    """체결가 보정과 비용 계산 전담."""

    def __init__(
        self,
        fee_rate: float,
        tax_rate: TaxRateLike,
        slippage: float,
        use_adjusted_price: bool = True,
        tick_rounding: str = "buy_up_sell_down",
    ):
        if fee_rate < 0:
            raise ValueError(f"fee_rate는 0 이상: {fee_rate}")
        if slippage < 0:
            raise ValueError(f"slippage는 0 이상: {slippage}")

        self.fee_rate = float(fee_rate)
        self._tax_rate = _normalize_tax_rate(tax_rate)
        self.slippage = float(slippage)
        self.use_adjusted_price = use_adjusted_price
        self.tick_rounding = tick_rounding

    def get_tax_rate(self, on_date: date_type) -> float:
        """on_date에 적용되는 거래세율을 반환 (정확성 정책 13.6.3)."""
        if isinstance(self._tax_rate, float):
            return self._tax_rate
        applicable = 0.0
        for entry in self._tax_rate:
            if on_date >= entry.from_date:
                applicable = entry.rate
            else:
                break
        return applicable

    def get_entry_price(self, row: Any, price_type: str) -> float:
        """row에서 체결 기준 가격을 꺼낸다. row는 dict 또는 pandas Series row.

        price_type: open / close / next_open / next_close
        """
        prefix = "adj_" if self.use_adjusted_price else ""
        col_map = {
            "open": f"{prefix}open",
            "close": f"{prefix}close",
            "next_open": f"{prefix}next_open",
            "next_close": f"{prefix}next_close",
        }
        if price_type not in col_map:
            raise ValueError(
                f"지원하지 않는 entry/exit price type: {price_type!r} "
                f"(허용: {', '.join(col_map.keys())})"
            )
        return float(row[col_map[price_type]])

    def apply_slippage_and_tick(self, price: float, side: str, market: str = "KOSPI") -> int:
        """슬리피지를 적용한 뒤 호가 단위로 반올림. 정수 가격 반환.

        매수는 위로(불리), 매도는 아래로(불리) 슬리피지 적용 (보수적).
        """
        if side == "buy":
            adjusted = price * (1 + self.slippage)
        elif side == "sell":
            adjusted = price * (1 - self.slippage)
        else:
            raise ValueError(f"지원하지 않는 side: {side!r}")
        return round_to_tick(adjusted, market=market, side=side, mode=self.tick_rounding)

    def calculate_buy_cost(
        self,
        price: int | float,
        quantity: int,
        *,
        raw_price: float | None = None,
    ) -> ExecutionResult:
        """매수 시 비용 분해 결과 반환.

        Parameters
        ----------
        price : 호가 단위 적용 후 체결가 (`apply_slippage_and_tick` 결과)
        quantity : 체결 수량 (>0)
        raw_price : 슬리피지 적용 전 가격. None이면 price로 간주
                    (감사용 slippage_applied 계산에 사용).

        Returns
        -------
        ExecutionResult — net_amount = gross + fee, tax = 0
        """
        if quantity <= 0:
            raise ValueError(f"quantity는 양수여야 합니다: {quantity}")

        gross = _round_krw(float(price) * quantity)
        fee = _round_krw(gross * self.fee_rate)
        net = gross + fee

        raw = float(raw_price) if raw_price is not None else float(price)
        slippage_applied = gross - _round_krw(raw * quantity)

        return ExecutionResult(
            side="buy",
            raw_price=raw,
            price=int(price),
            quantity=int(quantity),
            gross_amount=gross,
            fee=fee,
            tax=0,
            net_amount=net,
            slippage_applied=slippage_applied,
        )

    def calculate_sell_proceeds(
        self,
        price: int | float,
        quantity: int,
        on_date: date_type,
        *,
        raw_price: float | None = None,
    ) -> ExecutionResult:
        """매도 시 비용 분해 결과 반환.

        Parameters
        ----------
        price : 호가 단위 적용 후 체결가 (`apply_slippage_and_tick` 결과)
        quantity : 체결 수량 (>0)
        on_date : 체결일 (거래세 시계열 검색용 — 13.6.3)
        raw_price : 슬리피지 적용 전 가격. None이면 price로 간주.

        Returns
        -------
        ExecutionResult — net_amount = gross - fee - tax
        """
        if quantity <= 0:
            raise ValueError(f"quantity는 양수여야 합니다: {quantity}")

        gross = _round_krw(float(price) * quantity)
        fee = _round_krw(gross * self.fee_rate)
        tax = _round_krw(gross * self.get_tax_rate(on_date))
        net = gross - fee - tax

        raw = float(raw_price) if raw_price is not None else float(price)
        # 매도는 슬리피지가 가격을 낮추므로 음수로 기록 (감사 시 일관성 유지)
        slippage_applied = gross - _round_krw(raw * quantity)

        return ExecutionResult(
            side="sell",
            raw_price=raw,
            price=int(price),
            quantity=int(quantity),
            gross_amount=gross,
            fee=fee,
            tax=tax,
            net_amount=net,
            slippage_applied=slippage_applied,
        )

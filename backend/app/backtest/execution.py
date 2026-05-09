"""ExecutionModel — 체결 가격 / 비용 / 호가 단위 처리.

설계서 04번 7~9절 + 정확성 정책 13.5(호가) / 13.6(세율 시계열).

순환 import를 피하기 위해 Portfolio/Position을 직접 참조하지 않는다.
호출자가 가격/수량/날짜를 넘겨주면 비용/수익을 계산해 반환만 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

from app.backtest.tick import round_to_tick


@dataclass(frozen=True)
class TaxRateEntry:
    """시계열 세율 한 항목: from_date 이후부터 rate 적용."""

    from_date: date_type
    rate: float


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

    def calculate_buy_cost(self, price: float, quantity: int) -> float:
        """매수 시 빠져나가는 총액 = price * qty + 수수료."""
        gross = price * quantity
        return gross + gross * self.fee_rate

    def calculate_sell_proceeds(
        self, price: float, quantity: int, on_date: date_type
    ) -> float:
        """매도 시 들어오는 순수익 = price * qty - 수수료 - 거래세 (시계열)."""
        gross = price * quantity
        fee = gross * self.fee_rate
        tax = gross * self.get_tax_rate(on_date)
        return gross - fee - tax

"""CashManager — 예수금 부족 시 보유 종목 일부 매도.

설계서 05번 9~12절 + 정확성 정책 13.9.
종목코드 정렬 tie-breaker로 결정론 보장.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

from app.portfolio.portfolio import Portfolio
from app.portfolio.position import Position


class CashManager:
    """전략 JSON의 cash_management.shortage_rule 한 묶음을 받아 동작."""

    def __init__(self, rule: dict | None):
        """rule이 None 또는 enabled=False면 no-op."""
        if not rule or not rule.get("enabled", True):
            self._enabled = False
            return
        self._enabled = True
        shortage = rule.get("shortage_rule", {})
        self._action = shortage.get("action", {})
        self._target = shortage.get("target_selection", {"method": "lowest_return"})
        self._repeat = bool(shortage.get("repeat_until_cash_sufficient", False))

    @property
    def enabled(self) -> bool:
        return self._enabled

    def handle_shortage(
        self,
        portfolio: Portfolio,
        required_cash: float,
        on_date: date_type,
        price_provider,
    ) -> list[dict]:
        """필요 현금 확보 시도. 발동된 cash_event 로그 list 반환.

        price_provider(symbol, on_date) → float — 매도 체결가 산출.
        """
        if not self._enabled or portfolio.cash >= required_cash:
            return []

        events: list[dict] = []
        sell_fraction = float(self._action.get("sell_fraction", 0.25))
        method = self._target.get("method", "lowest_return")

        while portfolio.cash < required_cash:
            target = self._select_position(portfolio, method)
            if target is None:
                break
            quantity = int(target.quantity * sell_fraction)
            if quantity <= 0:
                break

            price = price_provider(target.symbol, on_date)
            cash_before = portfolio.cash
            portfolio.sell_symbol_fifo(
                symbol=target.symbol,
                price=price,
                quantity=quantity,
                on_date=on_date,
                reason="cash_shortage_partial_sell",
            )
            sell_amount = price * quantity
            events.append(
                {
                    "date": on_date,
                    "event_type": "cash_shortage",
                    "cash_before": cash_before,
                    "required_cash": required_cash,
                    "action": "partial_sell",
                    "symbol": target.symbol,
                    "sell_quantity": quantity,
                    "sell_amount": sell_amount,
                    "cash_after": portfolio.cash,
                    "reason": "cash_shortage_partial_sell",
                }
            )
            if not self._repeat:
                break
        return events

    @staticmethod
    def _select_position(portfolio: Portfolio, method: str) -> Position | None:
        positions = list(portfolio.positions.values())
        if not positions:
            return None

        # 종목코드 tie-breaker — 결정론
        if method == "lowest_return":
            return min(positions, key=lambda p: (p.unrealized_return_pct, p.symbol))
        if method == "highest_return":
            # 동순위 시 종목코드 큰 것 (max + 음수 정렬)
            return max(
                positions,
                key=lambda p: (p.unrealized_return_pct, _neg_symbol(p.symbol)),
            )
        if method == "largest_value":
            return max(
                positions, key=lambda p: (p.market_value, _neg_symbol(p.symbol))
            )
        raise ValueError(f"지원하지 않는 target_selection.method: {method!r}")


def _neg_symbol(symbol: str) -> Any:
    """max 함수에서도 종목코드 오름차순 tie-breaker."""

    class _Neg:
        __slots__ = ("v",)

        def __init__(self, v: str):
            self.v = v

        def __lt__(self, other):
            return self.v > other.v  # 부호 반전

        def __eq__(self, other):
            return self.v == other.v

    return _Neg(symbol)

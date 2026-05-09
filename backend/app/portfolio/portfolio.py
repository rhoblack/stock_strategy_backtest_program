"""Portfolio — 현금/보유 종목 상태 + 매수/매도 처리.

설계서 05번 5~7절 + 정확성 정책 13.9 (가중평균 평단가).

비용 계산(수수료/세율)은 호출자가 ExecutionModel로 미리 처리한 뒤
Portfolio.buy/sell에는 net amount(price * qty)만 전달한다.
"""

from __future__ import annotations

from datetime import date as date_type

from app.portfolio.position import Position, TradeGroup


class Portfolio:
    """전체 계좌 상태."""

    def __init__(self, initial_cash: float):
        if initial_cash < 0:
            raise ValueError(f"initial_cash는 0 이상: {initial_cash}")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: dict[str, Position] = {}
        self.trade_logs: list[dict] = []
        self._next_trade_group_id = 1

    # === 조회 ===

    def total_stock_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    def total_equity(self) -> float:
        return self.cash + self.total_stock_value()

    def positions_count(self) -> int:
        return len(self.positions)

    # === 매수 ===

    def buy(
        self,
        symbol: str,
        price: float,
        quantity: int,
        on_date: date_type,
        reason: str = "entry_signal",
        name: str = "",
        allow_pyramiding: bool = False,
        cost_override: float | None = None,
    ) -> int:
        """매수 처리. trade_group_id 반환.

        cost_override: 수수료/슬리피지를 반영한 실제 차감액. None이면 price*qty.
        """
        if quantity <= 0:
            raise ValueError(f"quantity는 양수여야 합니다: {quantity}")

        cost = cost_override if cost_override is not None else price * quantity
        if cost > self.cash:
            raise ValueError(
                f"예수금 부족: 필요 {cost:,.0f}원, 보유 {self.cash:,.0f}원"
            )

        trade_group_id = self._take_trade_group_id()

        if symbol in self.positions:
            if not allow_pyramiding:
                raise ValueError(
                    f"{symbol} 이미 보유 중. 추가매수가 비활성화되어 있습니다."
                )
            position = self.positions[symbol]
            position.trade_groups.append(
                TradeGroup(
                    trade_group_id=trade_group_id,
                    entry_date=on_date,
                    entry_price=price,
                    entry_quantity=quantity,
                    remaining_quantity=quantity,
                )
            )
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                name=name,
                current_price=price,
                peak_price=price,
                trade_groups=[
                    TradeGroup(
                        trade_group_id=trade_group_id,
                        entry_date=on_date,
                        entry_price=price,
                        entry_quantity=quantity,
                        remaining_quantity=quantity,
                    )
                ],
            )

        self.cash -= cost

        self.trade_logs.append(
            {
                "date": on_date,
                "symbol": symbol,
                "trade_group_id": trade_group_id,
                "execution_type": "BUY",
                "price": price,
                "quantity": quantity,
                "cost": cost,
                "reason": reason,
            }
        )

        return trade_group_id

    # === 매도 ===

    def sell_trade_group(
        self,
        symbol: str,
        trade_group_id: int,
        price: float,
        quantity: int,
        on_date: date_type,
        reason: str,
        proceeds_override: float | None = None,
    ) -> dict:
        """지정 trade_group의 일부 또는 전량 매도.

        proceeds_override: 수수료/세금을 반영한 실제 입금액. None이면 price*qty.
        반환: 매도 실행 로그 dict (cash_events 등에 활용).
        """
        if quantity <= 0:
            raise ValueError(f"quantity는 양수여야 합니다: {quantity}")
        if symbol not in self.positions:
            raise ValueError(f"보유하지 않은 종목: {symbol}")

        position = self.positions[symbol]
        target = next(
            (tg for tg in position.trade_groups if tg.trade_group_id == trade_group_id),
            None,
        )
        if target is None:
            raise ValueError(
                f"{symbol}에서 trade_group_id={trade_group_id} 찾을 수 없음"
            )

        sell_qty = min(quantity, target.remaining_quantity)
        proceeds = (
            proceeds_override if proceeds_override is not None else price * sell_qty
        )

        # 평단가는 trade_group.entry_price 그대로 (정확성 정책 13.9.3)
        realized_profit = (price - target.entry_price) * sell_qty
        realized_profit_rate = (price - target.entry_price) / target.entry_price * 100

        target.remaining_quantity -= sell_qty
        self.cash += proceeds

        is_partial = sell_qty < target.entry_quantity or target.remaining_quantity > 0

        log_entry = {
            "date": on_date,
            "symbol": symbol,
            "trade_group_id": trade_group_id,
            "execution_type": "PARTIAL_SELL" if is_partial else "SELL",
            "price": price,
            "quantity": sell_qty,
            "proceeds": proceeds,
            "realized_profit": realized_profit,
            "realized_profit_rate": realized_profit_rate,
            "reason": reason,
            "is_partial": is_partial,
        }
        self.trade_logs.append(log_entry)

        # remaining 0인 trade_group 제거
        position.trade_groups = [
            tg for tg in position.trade_groups if tg.remaining_quantity > 0
        ]

        # 전부 청산되면 position 자체를 제거
        if not position.trade_groups:
            del self.positions[symbol]

        return log_entry

    def sell_symbol_fifo(
        self,
        symbol: str,
        price: float,
        quantity: int,
        on_date: date_type,
        reason: str,
        proceeds_override: float | None = None,
    ) -> list[dict]:
        """종목 단위 매도. trade_group을 entry_date 오름차순으로 순회 (FIFO).

        proceeds_override는 전체 quantity에 대한 입금액. 각 trade_group에 비례 분배.
        """
        if symbol not in self.positions:
            raise ValueError(f"보유하지 않은 종목: {symbol}")

        position = self.positions[symbol]
        if quantity > position.quantity:
            raise ValueError(
                f"{symbol} 매도 요청 {quantity}주 > 보유 {position.quantity}주"
            )

        logs: list[dict] = []
        remaining = quantity

        # entry_date 오름차순 + 동순위 시 trade_group_id 오름차순 (결정론)
        sorted_groups = sorted(
            position.trade_groups,
            key=lambda tg: (tg.entry_date, tg.trade_group_id),
        )

        for tg in sorted_groups:
            if remaining <= 0:
                break
            take = min(remaining, tg.remaining_quantity)

            tg_proceeds: float | None = None
            if proceeds_override is not None:
                # 비례 분배
                tg_proceeds = proceeds_override * (take / quantity)

            log = self.sell_trade_group(
                symbol=symbol,
                trade_group_id=tg.trade_group_id,
                price=price,
                quantity=take,
                on_date=on_date,
                reason=reason,
                proceeds_override=tg_proceeds,
            )
            logs.append(log)
            remaining -= take

        return logs

    # === 평가가 갱신 ===

    def update_market_price(self, symbol: str, price: float) -> None:
        """일봉 종가 등으로 current_price 갱신. peak_price도 함께 갱신."""
        if symbol not in self.positions:
            return
        position = self.positions[symbol]
        position.current_price = price
        if price > position.peak_price:
            position.peak_price = price

    # === 내부 ===

    def _take_trade_group_id(self) -> int:
        tg_id = self._next_trade_group_id
        self._next_trade_group_id += 1
        return tg_id

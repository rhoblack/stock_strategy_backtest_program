"""Portfolio — 현금/보유 종목 상태 + 매수/매도 처리.

설계서 05번 5~7절 + 정확성 정책 13.9 (가중평균 평단가).

비용 계산(수수료/세율/슬리피지)은 호출자가 ExecutionModel로 미리 처리한 뒤
Portfolio.buy/sell에 `execution: ExecutionResult`로 전달한다. fee/tax 분해가
Portfolio.trade_logs에 함께 기록되어 영속화 단계(services.backtest_service의
TradeExecution insert)에서 그대로 매핑된다 (리뷰 011 H1 + M4 해소).

`cost_override` / `proceeds_override`는 호환성을 위해 유지되지만, ExecutionResult
가 함께 전달되면 그것이 우선한다. 신규 호출자는 ExecutionResult를 사용하라.
"""

from __future__ import annotations

from datetime import date as date_type

from app.backtest.execution import ExecutionResult
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
        execution: ExecutionResult | None = None,
    ) -> int:
        """매수 처리. trade_group_id 반환.

        Parameters
        ----------
        execution : ExecutionResult | None
            ExecutionModel.calculate_buy_cost 반환값. 우선 적용.
            fee/tax/net을 trade_logs에 기록한다.
        cost_override : float | None
            (호환) 수수료/슬리피지를 반영한 실제 차감액. execution이 None일 때만
            사용. trade_logs에는 fee/tax=0으로 기록된다.
        """
        if quantity <= 0:
            raise ValueError(f"quantity는 양수여야 합니다: {quantity}")

        # 비용 분해: execution > cost_override > price * quantity
        if execution is not None:
            if execution.side != "buy":
                raise ValueError(
                    f"buy()에 sell ExecutionResult 전달됨: side={execution.side}"
                )
            cost = execution.net_amount
            gross = execution.gross_amount
            fee = execution.fee
            tax = execution.tax
        elif cost_override is not None:
            cost = cost_override
            gross = price * quantity
            fee = max(0.0, cost - gross)  # 호환 추정 (정확하지 않을 수 있음)
            tax = 0.0
        else:
            cost = price * quantity
            gross = cost
            fee = 0.0
            tax = 0.0

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
                "side": "buy",
                "price": price,
                "quantity": quantity,
                "gross_amount": gross,
                "fee": fee,
                "tax": tax,
                "net_amount": cost,
                # 호환: 기존 키 유지 (services.backtest_service의 _persist_…가 사용)
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
        execution: ExecutionResult | None = None,
    ) -> dict:
        """지정 trade_group의 일부 또는 전량 매도.

        Parameters
        ----------
        execution : ExecutionResult | None
            ExecutionModel.calculate_sell_proceeds 반환값. 우선 적용.
            fee/tax/net이 trade_logs에 기록되며, realized_profit/_rate 계산도
            net_amount 기반으로 슬리피지·세금이 반영된다 (리뷰 011 M2 해소).
        proceeds_override : float | None
            (호환) 수수료/세금 반영 입금액. execution이 None일 때만 사용.

        Returns
        -------
        dict — 매도 실행 로그 (cash_events 등에 활용).
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

        # 비용 분해: execution > proceeds_override > price * sell_qty
        if execution is not None:
            if execution.side != "sell":
                raise ValueError(
                    f"sell_trade_group()에 buy ExecutionResult 전달됨: "
                    f"side={execution.side}"
                )
            if execution.quantity != sell_qty:
                raise ValueError(
                    f"ExecutionResult.quantity({execution.quantity})와 실제 "
                    f"sell_qty({sell_qty}) 불일치 — 호출자가 quantity를 "
                    f"맞춰서 분해해야 함"
                )
            proceeds = execution.net_amount
            gross = execution.gross_amount
            fee = execution.fee
            tax = execution.tax
        elif proceeds_override is not None:
            proceeds = proceeds_override
            gross = price * sell_qty
            # 호환 추정 — 정확하지 않을 수 있음 (M2: net_amount가 슬리피지 반영분)
            diff = max(0.0, gross - proceeds)
            fee = diff  # 분해 정보 없음 → fee로 몰아서 기록
            tax = 0.0
        else:
            proceeds = price * sell_qty
            gross = proceeds
            fee = 0.0
            tax = 0.0

        # 평단가는 trade_group.entry_price 그대로 (정확성 정책 13.9.3)
        # realized_profit/_rate는 net_amount 기반 — 슬리피지·세금·수수료 반영 (M2)
        cost_basis = target.entry_price * sell_qty
        realized_profit = proceeds - cost_basis
        realized_profit_rate = (
            (proceeds - cost_basis) / cost_basis * 100 if cost_basis > 0 else 0.0
        )

        target.remaining_quantity -= sell_qty
        self.cash += proceeds

        is_partial = sell_qty < target.entry_quantity or target.remaining_quantity > 0

        log_entry = {
            "date": on_date,
            "symbol": symbol,
            "trade_group_id": trade_group_id,
            "execution_type": "PARTIAL_SELL" if is_partial else "SELL",
            "side": "sell",
            "price": price,
            "quantity": sell_qty,
            "gross_amount": gross,
            "fee": fee,
            "tax": tax,
            "net_amount": proceeds,
            # 호환: 기존 키 유지
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
        execution: ExecutionResult | None = None,
    ) -> list[dict]:
        """종목 단위 매도. trade_group을 entry_date 오름차순으로 순회 (FIFO).

        Parameters
        ----------
        execution : ExecutionResult | None
            ExecutionResult.quantity == quantity여야 함. 비례 분배로 각
            trade_group에 fee/tax/net을 나눠서 기록한다.
        proceeds_override : float | None
            (호환) 전체 quantity에 대한 입금액. 각 trade_group에 비례 분배.
        """
        if symbol not in self.positions:
            raise ValueError(f"보유하지 않은 종목: {symbol}")

        position = self.positions[symbol]
        if quantity > position.quantity:
            raise ValueError(
                f"{symbol} 매도 요청 {quantity}주 > 보유 {position.quantity}주"
            )

        if execution is not None and execution.quantity != quantity:
            raise ValueError(
                f"ExecutionResult.quantity({execution.quantity})와 요청 "
                f"quantity({quantity}) 불일치"
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

            tg_execution: ExecutionResult | None = None
            tg_proceeds: float | None = None

            if execution is not None:
                # 비례 분배 — quantity 기준
                ratio = take / quantity
                tg_execution = ExecutionResult(
                    side="sell",
                    raw_price=execution.raw_price,
                    price=execution.price,
                    quantity=take,
                    gross_amount=execution.gross_amount * ratio,
                    fee=execution.fee * ratio,
                    tax=execution.tax * ratio,
                    net_amount=execution.net_amount * ratio,
                    slippage_applied=execution.slippage_applied * ratio,
                )
            elif proceeds_override is not None:
                tg_proceeds = proceeds_override * (take / quantity)

            log = self.sell_trade_group(
                symbol=symbol,
                trade_group_id=tg.trade_group_id,
                price=price,
                quantity=take,
                on_date=on_date,
                reason=reason,
                proceeds_override=tg_proceeds,
                execution=tg_execution,
            )
            logs.append(log)
            remaining -= take

        return logs

    # === 평가가 갱신 ===

    def update_market_price(self, symbol: str, price: float) -> None:
        """current_price만 갱신. peak_price는 건드리지 않는다.

        정확성 정책 13.3.5 + 13.15(look-ahead bias 방지):
            peak_price는 "전일까지의 high"여야 하므로 평가 시점에는 그날 high가
            반영돼서는 안 된다. 그날 high 반영은 exit_position 평가가 끝난 뒤
            `update_peak_price(symbol, today_high)`로 별도로 진행한다.
        """
        if symbol not in self.positions:
            return
        position = self.positions[symbol]
        position.current_price = price

    def update_peak_price(self, symbol: str, today_high: float) -> None:
        """exit_position 평가 후 호출되어 그날 high를 peak에 반영한다.

        정확성 정책 13.3.5: trailing_stop의 손절선은 `peak * (1 - pct/100)`.
        peak는 "전일까지의 high"로만 산정해야 하므로, 그날 high는 평가가 끝난
        뒤(다음날부터 적용되도록) 갱신한다. 이로써 같은 봉 안에서 high가
        급등했다가 즉시 trailing이 발동하는 회귀를 방지한다.
        """
        if symbol not in self.positions:
            return
        position = self.positions[symbol]
        if today_high > position.peak_price:
            position.peak_price = today_high

    # === 내부 ===

    def _take_trade_group_id(self) -> int:
        tg_id = self._next_trade_group_id
        self._next_trade_group_id += 1
        return tg_id

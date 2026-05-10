"""Portfolio — 현금/보유 종목 상태 + 매수/매도 처리.

설계서 05번 5~7절 + 정확성 정책 13.9 (가중평균 평단가).

비용 계산(수수료/세율/슬리피지)은 호출자가 ExecutionModel로 미리 처리한 뒤
Portfolio.buy/sell에 `execution: ExecutionResult`로 전달한다. fee/tax 분해가
Portfolio.trade_logs에 함께 기록되어 영속화 단계(services.backtest_service의
TradeExecution insert)에서 그대로 매핑된다 (리뷰 011 H1 + M4 해소).

`cost_override` / `proceeds_override`는 호환성을 위해 유지되지만, ExecutionResult
가 함께 전달되면 그것이 우선한다. 신규 호출자는 ExecutionResult를 사용하라.

정확성 정책 §14: 모든 금액(cash, cost, proceeds 등)은 KRW 정수.
float로 입력되면 int()로 잘라 정수화한다. 부분 매도 비례 분배 시 float 계산 후
_round_krw()로 정수 변환.
"""

from __future__ import annotations

import math
from datetime import date as date_type

from app.backtest.execution import ExecutionResult
from app.portfolio.position import Position, TradeGroup


def _round_krw(value: float) -> int:
    """금액을 원 단위 정수로 반올림 (round-half-up, banker's rounding 회피)."""
    return math.floor(value + 0.5)


class Portfolio:
    """전체 계좌 상태. 모든 금액 필드는 정수 KRW (정확성 정책 §14)."""

    def __init__(self, initial_cash: float):
        if initial_cash < 0:
            raise ValueError(f"initial_cash는 0 이상: {initial_cash}")
        self.initial_cash: int = int(initial_cash)
        self.cash: int = int(initial_cash)
        self.positions: dict[str, Position] = {}
        self.trade_logs: list[dict] = []
        self._next_trade_group_id = 1

    # === 조회 ===

    def total_stock_value(self) -> int:
        """보유 종목 평가금액 합계 (정수 KRW). Position.market_value는 float이므로 int 변환."""
        return int(sum(p.market_value for p in self.positions.values()))

    def total_equity(self) -> int:
        """총 자산 (현금 + 평가금액, 정수 KRW)."""
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
        signal_date: date_type | None = None,
    ) -> int:
        """매수 처리. trade_group_id 반환.

        Parameters
        ----------
        on_date : date
            **체결일 (execution_date)**. TradeGroup.entry_date / trade_logs.date /
            CSV·차트의 거래 마커는 모두 이 값을 사용한다. 정확성 정책 13.15 +
            CLAUDE.md look-ahead 체크리스트("신호일 종가로 신호, 다음날 시가로
            체결")에 따라, BacktestEngine은 next_open 매수에 대해 next_date(=
            다음 거래일)를 전달한다. cash_manager가 호출하는 강제 매도/매수는
            그 시점에 즉시 체결되므로 signal_date == execution_date로 today를
            그대로 전달한다.
        signal_date : date | None
            신호 발생일 (선택). next_open 체결처럼 신호일과 체결일이 다른 경우
            호출자가 today를 전달. trade_logs.signal_date 키로 기록되며 CSV/
            차트가 신호 발생 시점을 별도로 표시할 때 사용한다. None이면
            on_date(=execution_date)와 동일하다고 간주한다.
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
        # 정확성 정책 §14: 모든 금액은 정수 KRW
        if execution is not None:
            if execution.side != "buy":
                raise ValueError(
                    f"buy()에 sell ExecutionResult 전달됨: side={execution.side}"
                )
            cost: int = execution.net_amount
            gross: int = execution.gross_amount
            fee: int = execution.fee
            tax: int = execution.tax
        elif cost_override is not None:
            cost = int(cost_override)
            gross = _round_krw(float(price) * quantity)
            fee = max(0, cost - gross)  # 호환 추정 (정확하지 않을 수 있음)
            tax = 0
        else:
            gross = _round_krw(float(price) * quantity)
            cost = gross
            fee = 0
            tax = 0

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
                # date == execution_date (체결일). 기존 services 매핑 호환.
                "date": on_date,
                # 015 추가 — signal_date / execution_date 명시적 분리.
                # services 영속화 매핑 추가는 후속 step.
                "signal_date": signal_date if signal_date is not None else on_date,
                "execution_date": on_date,
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
        signal_date: date_type | None = None,
    ) -> dict:
        """지정 trade_group의 일부 또는 전량 매도.

        Parameters
        ----------
        on_date : date
            **체결일 (execution_date)**. trade_logs.date / CSV·차트 마커가
            사용. exit_signal로 인한 next_open 매도는 next_date를, 갭/일중
            stop·take/trailing/max_holding/cash_manager 강제 매도는 today를
            전달한다 (정확성 정책 13.3 + CLAUDE.md look-ahead 체크리스트).
        signal_date : date | None
            신호 발생일 (선택). exit_signal next_open 매도는 today를 전달.
            on_date와 다른 경우 trade_logs.signal_date에 기록된다. None이면
            on_date(=execution_date)와 동일하다고 간주.
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
        # 정확성 정책 §14: 모든 금액은 정수 KRW
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
            proceeds: int = execution.net_amount
            gross: int = execution.gross_amount
            fee: int = execution.fee
            tax: int = execution.tax
        elif proceeds_override is not None:
            proceeds = int(proceeds_override)
            gross = _round_krw(float(price) * sell_qty)
            # 호환 추정 — 정확하지 않을 수 있음 (M2: net_amount가 슬리피지 반영분)
            diff = max(0, gross - proceeds)
            fee = diff  # 분해 정보 없음 → fee로 몰아서 기록
            tax = 0
        else:
            gross = _round_krw(float(price) * sell_qty)
            proceeds = gross
            fee = 0
            tax = 0

        # 평단가는 trade_group.entry_price 그대로 (정확성 정책 13.9.3)
        # realized_profit/_rate는 net_amount 기반 — 슬리피지·세금·수수료 반영 (M2)
        cost_basis = _round_krw(target.entry_price * sell_qty)
        realized_profit: int = proceeds - cost_basis
        realized_profit_rate = (
            (proceeds - cost_basis) / cost_basis * 100 if cost_basis > 0 else 0.0
        )

        target.remaining_quantity -= sell_qty
        self.cash += proceeds

        is_partial = sell_qty < target.entry_quantity or target.remaining_quantity > 0

        log_entry = {
            # date == execution_date (체결일). 기존 services 매핑 호환.
            "date": on_date,
            # 015 추가 — signal_date / execution_date 명시적 분리.
            "signal_date": signal_date if signal_date is not None else on_date,
            "execution_date": on_date,
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
        signal_date: date_type | None = None,
    ) -> list[dict]:
        """종목 단위 매도. trade_group을 entry_date 오름차순으로 순회 (FIFO).

        Parameters
        ----------
        on_date : date
            **체결일 (execution_date)**. sell_trade_group의 동명 인자에 그대로
            전달.
        signal_date : date | None
            신호 발생일 (선택). exit_signal next_open 매도는 today를 전달.
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
                # 비례 분배 — quantity 기준.
                # 정확성 정책 §14: 금액은 정수 KRW. 비율 연산 후 _round_krw()로 변환.
                # 마지막 그룹은 반올림 오차가 누적되지 않도록 잔여값(총액 - 이미 분배된 합)으로 계산.
                # MVP에서는 단순 비례 반올림으로 충분 (소수 원 단위 차이는 무시).
                ratio = take / quantity
                tg_execution = ExecutionResult(
                    side="sell",
                    raw_price=execution.raw_price,
                    price=execution.price,
                    quantity=take,
                    gross_amount=_round_krw(execution.gross_amount * ratio),
                    fee=_round_krw(execution.fee * ratio),
                    tax=_round_krw(execution.tax * ratio),
                    net_amount=_round_krw(execution.net_amount * ratio),
                    slippage_applied=_round_krw(execution.slippage_applied * ratio),
                )
            elif proceeds_override is not None:
                tg_proceeds = _round_krw(proceeds_override * (take / quantity))

            log = self.sell_trade_group(
                symbol=symbol,
                trade_group_id=tg.trade_group_id,
                price=price,
                quantity=take,
                on_date=on_date,
                reason=reason,
                proceeds_override=tg_proceeds,
                execution=tg_execution,
                signal_date=signal_date,
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

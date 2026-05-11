"""CashManager — 예수금 부족 시 보유 종목 일부 매도.

설계서 05번 9~12절 + 정확성 정책 13.5(호가) / 13.6(세율) / 13.9.
종목코드 정렬 tie-breaker로 결정론 보장.

리뷰 011 C2 해소:
    강제 매도(cash_shortage_partial_sell)도 일반 exit_signal/exit_position
    매도와 동일한 ExecutionModel 경로(슬리피지 + 호가 단위 + 거래세 시계열)를
    거친다. 이전에는 raw price * qty로 직접 sell_symbol_fifo를 호출하여
    슬리피지·세금이 모두 0인 비현실적 매도가 백테스트 수익을 좋게 만들었다.

    ExecutionModel을 주입받지 않은 경우(레거시 호환)는 raw price 매도로
    fallback하지만, BacktestEngine 경로에서는 항상 주입된 상태로 사용한다.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.portfolio.position import Position


class CashManager:
    """전략 JSON의 cash_management.shortage_rule 한 묶음을 받아 동작.

    지원 trigger.type (02번 §9):
        - "cash_below_daily_buy_budget" (기존): 매수 예산 미만 시 발동.
          handle_shortage에 required_cash = 당일 매수 예산을 전달.
        - "cash_below_threshold" (02-t, step 066): 예수금이 절대값 threshold
          미만이면 발동. shortage_rule.trigger.threshold 값(원 단위) 필수.
    """

    def __init__(
        self,
        rule: dict | None,
        execution_model: ExecutionModel | None = None,
        market: str = "KOSPI",
    ):
        """rule이 None 또는 enabled=False면 no-op.

        Parameters
        ----------
        execution_model : ExecutionModel | None
            강제 매도 시 슬리피지/호가/세율을 적용할 모델. None이면 raw price
            그대로 매도(레거시 호환 — 단위 테스트 외에는 사용 금지).
        market : str
            tick_size 결정용 시장 코드. ExecutionModel에 위임.
        """
        self._execution_model = execution_model
        self._market = market

        if not rule or not rule.get("enabled", True):
            self._enabled = False
            self._trigger_type = "cash_below_daily_buy_budget"
            self._trigger_threshold: float | None = None
            return
        self._enabled = True
        shortage = rule.get("shortage_rule", {})
        trigger = shortage.get("trigger", {})
        self._trigger_type: str = trigger.get("type", "cash_below_daily_buy_budget")
        self._trigger_threshold = trigger.get("threshold", None)
        self._action = shortage.get("action", {})
        self._target = shortage.get("target_selection", {"method": "lowest_return"})
        self._repeat = bool(shortage.get("repeat_until_cash_sufficient", False))

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def trigger_type(self) -> str:
        """trigger.type 반환 (02-t, step 066)."""
        return self._trigger_type

    @property
    def trigger_threshold(self) -> float | None:
        """cash_below_threshold 트리거의 절대값 threshold (원 단위, step 066)."""
        return self._trigger_threshold

    def is_triggered(self, portfolio: Portfolio, required_cash: float) -> bool:
        """트리거 조건 충족 여부 평가 (02-t, step 066).

        Parameters
        ----------
        portfolio : Portfolio
            현재 포트폴리오.
        required_cash : float
            매수에 필요한 현금 (cash_below_daily_buy_budget 트리거 전용).

        Returns
        -------
        bool
            True이면 handle_shortage 발동 조건 충족.
        """
        if not self._enabled:
            return False
        if self._trigger_type == "cash_below_threshold":
            threshold = self._trigger_threshold
            if threshold is None:
                # threshold 미지정 시 발동 안 함 (설계 오류 — 보수적 처리)
                return False
            return portfolio.cash < threshold
        # default: cash_below_daily_buy_budget
        return portfolio.cash < required_cash

    def handle_shortage(
        self,
        portfolio: Portfolio,
        required_cash: float,
        on_date: date_type,
        price_provider,
    ) -> list[dict]:
        """필요 현금 확보 시도. 발동된 cash_event 로그 list 반환.

        price_provider(symbol, on_date) → float — 매도 체결 raw price 산출.
        ExecutionModel이 주입되어 있으면 이 raw price에 슬리피지+호가+세금을 적용.

        Step 066 (02-t): trigger 타입에 따라 발동 조건이 달라진다.
            - cash_below_daily_buy_budget: portfolio.cash < required_cash
            - cash_below_threshold: portfolio.cash < self._trigger_threshold
        """
        if not self._enabled:
            return []
        if not self.is_triggered(portfolio, required_cash):
            return []

        events: list[dict] = []
        sell_fraction = float(self._action.get("sell_fraction", 0.25))
        method = self._target.get("method", "lowest_return")

        # 루프 종료 조건: trigger 타입에 따라 "충분" 기준이 다름.
        # cash_below_threshold: cash >= threshold이면 충분.
        # cash_below_daily_buy_budget: cash >= required_cash이면 충분.
        def _is_still_short() -> bool:
            return self.is_triggered(portfolio, required_cash)

        while _is_still_short():
            target = self._select_position(portfolio, method)
            if target is None:
                break
            quantity = int(target.quantity * sell_fraction)
            if quantity <= 0:
                break

            raw_price = price_provider(target.symbol, on_date)
            cash_before = portfolio.cash

            # ExecutionModel이 주입돼 있으면 슬리피지+호가+세금을 모두 적용
            if self._execution_model is not None:
                exec_price = self._execution_model.apply_slippage_and_tick(
                    raw_price, side="sell", market=self._market
                )
                execution = self._execution_model.calculate_sell_proceeds(
                    exec_price, quantity, on_date, raw_price=raw_price
                )
                portfolio.sell_symbol_fifo(
                    symbol=target.symbol,
                    price=exec_price,
                    quantity=quantity,
                    on_date=on_date,
                    reason="cash_shortage_partial_sell",
                    execution=execution,
                )
                gross = execution.gross_amount
                fee = execution.fee
                tax = execution.tax
                net = execution.net_amount
                exec_price_used = exec_price
            else:
                # 레거시 fallback — slippage/세금 없이 raw price로 매도
                portfolio.sell_symbol_fifo(
                    symbol=target.symbol,
                    price=raw_price,
                    quantity=quantity,
                    on_date=on_date,
                    reason="cash_shortage_partial_sell",
                )
                gross = raw_price * quantity
                fee = 0.0
                tax = 0.0
                net = gross
                exec_price_used = raw_price

            events.append(
                {
                    "date": on_date,
                    "event_type": "cash_shortage",
                    "cash_before": cash_before,
                    "required_cash": required_cash,
                    "action": "partial_sell",
                    "symbol": target.symbol,
                    "sell_quantity": quantity,
                    # 기존 키 유지 (서비스 영속화 호환)
                    "sell_amount": net,
                    # 신규 분해 키 (014 step에서 영속화 매핑 가능)
                    "exec_price": exec_price_used,
                    "raw_price": raw_price,
                    "gross_amount": gross,
                    "fee": fee,
                    "tax": tax,
                    "net_amount": net,
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

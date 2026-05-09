"""BacktestEngine — 단일 종목 백테스트 오케스트레이터.

설계서 04번 5~6절 + 정확성 정책 13.3 (일중 익절/손절) / 13.4 (갭/거래정지) /
13.16 (이벤트 우선순위).

Phase 1 단일 종목 한정. universe / priority / cash_management는 후속 단계.

흐름 (정확성 정책 13.16 우선순위 적용):
    1. 거래정지 (volume=0) → skip
    2. 보유 중이면 update_market_price + exit_position 평가
       (갭 우선 → 일중 손절 → 일중 익절 → max_holding_days)
    3. 보유 중 + exit_signal True → 다음 거래일 시가 매도 (FIFO)
    4. 미보유 + final_entry_signal True → 다음 거래일 시가 매수
    5. 일별 자산 기록
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.backtest.config import BacktestConfig
from app.backtest.execution import ExecutionModel
from app.backtest.result import BacktestResult, DailyEquity
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine


class BacktestEngine:
    """단일 종목 백테스트 엔진.

    StrategyEngine으로 신호를 생성하고, ExecutionModel로 체결가/비용을 계산하며,
    Portfolio에 매수/매도를 반영한다. exit_position 평가는 본 클래스가 직접 담당
    (포지션 정보가 필요하므로 StrategyEngine 책임 밖).
    """

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        portfolio: Portfolio,
        execution_model: ExecutionModel,
        config: BacktestConfig,
    ):
        self.strategy_engine = strategy_engine
        self.portfolio = portfolio
        self.execution_model = execution_model
        self.config = config

    def run(self, df: pd.DataFrame) -> BacktestResult:
        """단일 종목 df에 대해 백테스트를 실행하고 결과를 반환.

        df는 다음 컬럼을 가진다고 가정:
            adj_open, adj_high, adj_low, adj_close, adj_volume
            next_open, next_close (PriceLoader에서 미리 채움)
            date 또는 인덱스가 datetime
        """
        df = self.strategy_engine.generate_signals(df)
        symbol = self.config.symbol
        exit_position_rules = self._get_exit_position_rules()

        result = BacktestResult(
            initial_cash=self.portfolio.initial_cash,
        )

        peak_equity = self.portfolio.initial_cash

        for idx in range(len(df)):
            row = df.iloc[idx]
            today = self._row_date(row, idx)

            if today < self.config.start_date or today > self.config.end_date:
                continue

            if self.config.skip_no_volume and row["adj_volume"] == 0:
                self._record_daily_equity(result, today, peak_equity)
                peak_equity = max(peak_equity, self.portfolio.total_equity())
                continue

            # 보유 중 처리
            if symbol in self.portfolio.positions:
                self.portfolio.update_market_price(symbol, float(row["adj_close"]))

                # 1. exit_position 평가 (정확성 정책 13.3)
                exit_info = self._evaluate_exit_position(
                    self.portfolio.positions[symbol],
                    row,
                    exit_position_rules,
                    today,
                )
                if exit_info is not None:
                    exit_price, exit_reason, full_qty = exit_info
                    self._process_sell_at_price(
                        symbol=symbol,
                        price=exit_price,
                        quantity=full_qty,
                        on_date=today,
                        reason=exit_reason,
                        result=result,
                    )
                    peak_equity = max(peak_equity, self.portfolio.total_equity())
                    self._record_daily_equity(result, today, peak_equity)
                    continue

                # 2. exit_signal 평가 → 다음 거래일 시가 매도
                if bool(row["exit_signal"]) and not pd.isna(row.get("next_open")):
                    self._process_sell_at_price(
                        symbol=symbol,
                        price=float(row["next_open"]),
                        quantity=self.portfolio.positions[symbol].quantity,
                        on_date=today,
                        reason="exit_signal",
                        result=result,
                    )

            # 3. 미보유 + final_entry_signal → 다음 시가 매수
            elif bool(row["final_entry_signal"]) and not pd.isna(row.get("next_open")):
                self._maybe_buy(symbol, row, today, result)

            peak_equity = max(peak_equity, self.portfolio.total_equity())
            self._record_daily_equity(result, today, peak_equity)

        result.final_cash = self.portfolio.cash
        result.final_equity = self.portfolio.total_equity()
        result.trade_executions = list(self.portfolio.trade_logs)
        return result

    # === 헬퍼 ===

    def _row_date(self, row: pd.Series, idx: int):
        """row에서 날짜 추출. 'date' 컬럼 또는 DatetimeIndex 가정."""
        if "date" in row.index:
            value = row["date"]
            return value.date() if hasattr(value, "date") else value
        # DatetimeIndex
        ts = row.name
        return ts.date() if hasattr(ts, "date") else ts

    def _get_exit_position_rules(self) -> list[dict]:
        section = self.strategy_engine.strategy.get("exit_position")
        if not section:
            return []
        return list(section.get("conditions", []))

    def _evaluate_exit_position(
        self,
        position: Any,
        row: pd.Series,
        rules: list[dict],
        today,
    ) -> tuple[float, str, int] | None:
        """포지션 기반 매도 평가. 반환: (exit_price, exit_reason, quantity).

        정확성 정책 13.3 우선순위:
            1. 갭 다운 손절 (open <= stop_price)
            2. 갭 업 익절 (open >= target_price)
            3. 일중 손절 (low <= stop_price) — 동일 봉 동시 도달 시 손절 우선
            4. 일중 익절 (high >= target_price)
            5. max_holding_days 도달 → 종가 청산
        """
        adj_open = float(row["adj_open"])
        adj_high = float(row["adj_high"])
        adj_low = float(row["adj_low"])
        adj_close = float(row["adj_close"])

        entry_price = position.avg_entry_price
        full_qty = position.quantity

        stop_pct = next((r["percent"] for r in rules if r["type"] == "stop_loss"), None)
        take_pct = next((r["percent"] for r in rules if r["type"] == "take_profit"), None)
        max_holding = next(
            (r["days"] for r in rules if r["type"] == "max_holding_days"), None
        )

        # 1. 갭 다운 손절
        if stop_pct is not None:
            stop_price = entry_price * (1 - stop_pct / 100)
            if adj_open <= stop_price:
                return adj_open, "gap_down_stop_loss", full_qty

        # 2. 갭 업 익절
        if take_pct is not None:
            target_price = entry_price * (1 + take_pct / 100)
            if adj_open >= target_price:
                return adj_open, "gap_up_take_profit", full_qty

        # 3. 일중 손절 (동시 도달 시 손절 우선)
        if stop_pct is not None:
            stop_price = entry_price * (1 - stop_pct / 100)
            if adj_low <= stop_price:
                return stop_price, "stop_loss", full_qty

        # 4. 일중 익절
        if take_pct is not None:
            target_price = entry_price * (1 + take_pct / 100)
            if adj_high >= target_price:
                return target_price, "take_profit", full_qty

        # 5. max_holding_days
        if max_holding is not None:
            holding_days = (today - position.first_entry_date).days
            if holding_days >= max_holding:
                return adj_close, "max_holding_days", full_qty

        return None

    def _maybe_buy(
        self,
        symbol: str,
        row: pd.Series,
        today,
        result: BacktestResult,
    ) -> None:
        """매수 시도. 갭 초과 / 거래정지 / 예수금 부족 시 skip."""
        next_open = float(row["next_open"])
        prev_close = float(row["adj_close"])

        # 다음 거래일 거래정지 체크 (정확성 정책 13.4.2)
        next_volume = row.get("next_volume")
        if self.config.skip_no_volume and next_volume is not None and next_volume == 0:
            return

        # 갭 체크 (정확성 정책 13.4.1)
        gap_pct = (next_open - prev_close) / prev_close * 100
        if gap_pct > self.config.max_gap_pct_for_entry:
            return

        # 슬리피지 + 호가 단위 적용
        exec_price = self.execution_model.apply_slippage_and_tick(
            next_open, side="buy", market=self.config.market
        )

        if exec_price <= 0:
            return

        quantity = int(self.config.position_size_amount // exec_price)
        if quantity <= 0:
            return

        cost = self.execution_model.calculate_buy_cost(exec_price, quantity)
        if cost > self.portfolio.cash:
            return

        self.portfolio.buy(
            symbol=symbol,
            price=exec_price,
            quantity=quantity,
            on_date=today,
            reason="entry_signal",
            cost_override=cost,
        )

    def _process_sell_at_price(
        self,
        symbol: str,
        price: float,
        quantity: int,
        on_date,
        reason: str,
        result: BacktestResult,
    ) -> None:
        """price를 슬리피지/호가/세금 처리한 뒤 FIFO로 매도."""
        # 갭 손절/익절은 시가 그대로 체결 (이미 정확성 정책에 따라 호출자가 결정)
        # 슬리피지는 모든 매도에 보수적으로 적용
        exec_price = self.execution_model.apply_slippage_and_tick(
            price, side="sell", market=self.config.market
        )
        proceeds = self.execution_model.calculate_sell_proceeds(
            exec_price, quantity, on_date
        )
        self.portfolio.sell_symbol_fifo(
            symbol=symbol,
            price=exec_price,
            quantity=quantity,
            on_date=on_date,
            reason=reason,
            proceeds_override=proceeds,
        )

    def _record_daily_equity(
        self, result: BacktestResult, on_date, peak_equity: float
    ) -> None:
        cash = self.portfolio.cash
        stock_value = self.portfolio.total_stock_value()
        total = cash + stock_value
        drawdown = 0.0
        if peak_equity > 0:
            drawdown = (total - peak_equity) / peak_equity * 100
        result.daily_equity.append(
            DailyEquity(
                date=on_date,
                cash=cash,
                stock_value=stock_value,
                total_equity=total,
                drawdown=drawdown,
                positions_count=self.portfolio.positions_count(),
            )
        )

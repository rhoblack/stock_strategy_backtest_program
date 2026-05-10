"""BacktestEngine — 단일 종목 백테스트 오케스트레이터.

설계서 04번 5~6절 + 정확성 정책 13.3 (일중 익절/손절) / 13.4 (갭/거래정지) /
13.16 (이벤트 우선순위) / 13.3.5 + 13.15 (peak_price 전일까지 high) /
03번 §4 + CLAUDE.md 핵심원칙 #2 (ConditionRegistry 라우팅 통일).

Phase 1 단일 종목 한정. universe / priority / cash_management는 후속 단계.

흐름 (정확성 정책 13.16 우선순위 적용):
    1. 거래정지 (volume=0) → skip
    2. 보유 중이면:
        a. update_market_price (current_price만 갱신, peak는 미변경)
        b. exit_position 평가 — 갭 다운/업 분기 후 ConditionRegistry로 라우팅
           (정렬: stop_loss → take_profit → trailing_stop → max_holding_days)
        c. exit_signal True → 다음 거래일 시가 매도 (FIFO)
        d. update_peak_price (그날 high를 peak에 반영, 다음날부터 적용)
    3. 미보유 + final_entry_signal True → 다음 거래일 시가 매수
    4. 일별 자산 기록
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.backtest.config import BacktestConfig
from app.backtest.execution import ExecutionModel
from app.backtest.result import BacktestResult, DailyEquity
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine
from app.strategy.registry import condition_registry

# exit_position 평가 우선순위 (정확성 정책 13.3).
# 갭 다운/업은 본 매핑 이전에 별도 분기로 처리하고, 일중 평가는 다음 순서로 진행한다.
# tie-breaker는 (priority_rank, type)으로 결정론을 보장한다.
_EXIT_POSITION_PRIORITY: dict[str, int] = {
    "stop_loss": 1,        # 13.3.1 + 13.3.2 (동일 봉 동시 도달 시 손절 우선)
    "take_profit": 2,      # 13.3.1
    "trailing_stop": 3,    # 13.3.5
    "max_holding_days": 4,  # 종가 청산은 마지막
}


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
        cash_manager=None,  # CashManager | None
    ):
        self.strategy_engine = strategy_engine
        self.portfolio = portfolio
        self.execution_model = execution_model
        self.config = config
        self.cash_manager = cash_manager
        # cash_events 누적 (서비스가 영속화)
        self.cash_events: list[dict] = []

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
                # current_price만 갱신 (peak는 평가 후) — 13.3.5 / 13.15 look-ahead 방지
                self.portfolio.update_market_price(symbol, float(row["adj_close"]))

                # 1. exit_position 평가 (정확성 정책 13.3 + 03번 §4 — Registry 라우팅)
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
                    # 청산되었으면 peak 갱신 불필요
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

                # 3. 평가 종료 후 그날 high를 peak에 반영 (다음날부터 trailing 적용)
                if symbol in self.portfolio.positions:
                    self.portfolio.update_peak_price(symbol, float(row["adj_high"]))

            # 4. 미보유 + final_entry_signal → 다음 시가 매수
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
            1. 갭 다운 손절 (open <= stop_price)             — 시가 체결
            2. 갭 업 익절 (open >= target_price)             — 시가 체결
            3. 일중 손절 (registry stop_loss)                — stop_price 체결
            4. 일중 익절 (registry take_profit)              — target_price 체결
            5. trailing_stop (registry trailing_stop)        — peak*(1-pct) 체결
            6. max_holding_days (registry max_holding_days)  — 종가 청산

        구현:
            - 갭 분기는 entry_price 기반 임계값 검사로 별도 처리 (별도 reason).
            - 일중 평가는 ConditionRegistry.evaluate_position 단일 진입점으로
              우선순위 정렬 후 첫 트리거를 사용 (03번 §4 + CLAUDE.md #2).
            - 동일 봉 stop+take 동시 도달 시 stop이 먼저 평가되어 보수적으로 처리됨.
            - 결정론: 정렬 키는 (priority, type) — dict 순회 순서 미의존.
        """
        adj_open = float(row["adj_open"])
        adj_close = float(row["adj_close"])

        entry_price = position.entry_price
        full_qty = position.quantity

        # 1~2. 갭 다운/업 우선 분기 — Registry 외부에서 시가 임계값으로만 판정
        stop_rule = next((r for r in rules if r["type"] == "stop_loss"), None)
        take_rule = next((r for r in rules if r["type"] == "take_profit"), None)

        if stop_rule is not None:
            stop_price = entry_price * (1 - stop_rule["percent"] / 100)
            if adj_open <= stop_price:
                return adj_open, "gap_down_stop_loss", full_qty

        if take_rule is not None:
            target_price = entry_price * (1 + take_rule["percent"] / 100)
            if adj_open >= target_price:
                return adj_open, "gap_up_take_profit", full_qty

        # 3~6. ConditionRegistry 라우팅 — 우선순위 + type tie-breaker로 정렬
        sorted_rules = sorted(
            rules,
            key=lambda r: (
                _EXIT_POSITION_PRIORITY.get(r["type"], 99),
                r["type"],
            ),
        )

        for rule in sorted_rules:
            rule_type = rule["type"]
            if rule_type not in _EXIT_POSITION_PRIORITY:
                # 미지원 타입은 건너뜀 (등록은 됐어도 우선순위 미정의)
                continue

            triggered, reason = condition_registry.evaluate_position(
                rule_type,
                position=position,
                market_row=row,
                condition=rule,
            )
            if not triggered:
                continue

            # 트리거된 룰별 체결가 재계산 (정확성 정책 13.3)
            exit_price = self._compute_exit_price(
                rule_type=rule_type,
                rule=rule,
                position=position,
                adj_close=adj_close,
            )
            return exit_price, reason or rule_type, full_qty

        return None

    def _compute_exit_price(
        self,
        *,
        rule_type: str,
        rule: dict,
        position: Any,
        adj_close: float,
    ) -> float:
        """트리거된 exit_position 룰의 체결가 계산 (정확성 정책 13.3).

        - stop_loss     : entry_price * (1 - percent/100)  — 손절선 정확 체결
        - take_profit   : entry_price * (1 + percent/100)  — 익절선 정확 체결
        - trailing_stop : peak_price  * (1 - percent/100)  — 트레일링 손절선
        - max_holding_days : adj_close                     — 종가 청산
        """
        entry_price = position.entry_price
        if rule_type == "stop_loss":
            return entry_price * (1 - rule["percent"] / 100)
        if rule_type == "take_profit":
            return entry_price * (1 + rule["percent"] / 100)
        if rule_type == "trailing_stop":
            return position.peak_price * (1 - rule["percent"] / 100)
        if rule_type == "max_holding_days":
            return adj_close
        # 등록되지 않은 우선순위는 위에서 차단되므로 도달 불가
        raise ValueError(f"체결가 계산이 정의되지 않은 rule_type: {rule_type}")

    def _maybe_buy(
        self,
        symbol: str,
        row: pd.Series,
        today,
        result: BacktestResult,
    ) -> None:
        """매수 시도. 갭 초과 / 거래정지 / 예수금 부족(CashManager 시도) 시 skip."""
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

        # 사전 fund 확보 (CashManager 옵션)
        if self.cash_manager is not None and self.cash_manager.enabled:
            # 추정 비용으로 미리 cash 확보 시도
            est_price = self.execution_model.apply_slippage_and_tick(
                next_open, side="buy", market=self.config.market
            )
            est_quantity = int(self.config.position_size_amount // max(est_price, 1))
            if est_quantity > 0:
                est_cost = self.execution_model.calculate_buy_cost(est_price, est_quantity)
                events = self.cash_manager.handle_shortage(
                    self.portfolio,
                    required_cash=est_cost,
                    on_date=today,
                    price_provider=lambda s, _d: float(row["adj_close"]),
                )
                self.cash_events.extend(events)

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

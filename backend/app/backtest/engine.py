"""BacktestEngine — 단일/복수 종목 백테스트 오케스트레이터.

설계서 04번 5~6절 + 정확성 정책 13.3 (일중 익절/손절) / 13.4 (갭/거래정지) /
13.15 (look-ahead bias 체크리스트 — "신호일 종가로 신호, 다음날 시가로 체결") /
13.16 (이벤트 우선순위) / 13.3.5 + 13.15 (peak_price 전일까지 high) /
03번 §4 + CLAUDE.md 핵심원칙 #2 (ConditionRegistry 라우팅 통일).

Phase 10 step 020 — 복수 종목 입력 지원 (외부 리뷰 CR-003).

신호일(signal_date) vs 체결일(execution_date) 분리 — 015 정합성 수정:
    next_open 체결 경로(신규 매수, exit_signal 매도)는 신호일과 체결일이
    하루 다르다. trade_logs / TradeGroup.entry_date / CSV·차트 마커가
    실제 체결일을 기록하도록 portfolio.buy/sell_*에 execution_date를 전달
    하고, signal_date는 추가 파라미터로 보존해 후속 영속화/표시 단계에서
    사용한다. 갭/일중 stop·take/trailing/max_holding/cash_manager 강제
    매도는 today 즉시 체결이므로 signal_date == execution_date == today.

복수 종목 입력 (Phase 10 020):
    run() 시그니처가 `prices: dict[str, pd.DataFrame] | pd.DataFrame`을
    받는다. 단일 DataFrame을 그대로 넘기면 자동으로 `{config.symbol: df}`
    로 wrap돼 015 이전과 동일하게 동작한다 (Phase 1 골든 fixture 호환).

    `universe_resolver(today: date) -> list[str]`로 일별 active universe
    를 동적으로 제어할 수 있다. 미지정 시 prices.keys() 전체를 모든 거래일
    의 universe로 사용한다.

    priority 알고리즘 / max_positions / max_daily_entries / event_log /
    상장폐지 강제 매도는 본 step의 scope 밖. 후보 정렬은 symbol ASC만 — step
    021이 priority 알고리즘으로 본 step의 정렬을 교체한다.

흐름 (정확성 정책 13.16 우선순위 적용; 단일 종목 → N종목으로 일반화):
    각 거래일 today에 다음 순서로 처리한다.

    1. 보유 포지션 평가 (sorted(portfolio.positions.keys())로 결정론):
        a. 그 종목의 today row가 없거나 거래정지(volume=0)면 skip
        b. update_market_price (current_price만 갱신, peak는 미변경)
        c. exit_position 평가 — 갭 다운/업 분기 후 ConditionRegistry로 라우팅
           (정렬: stop_loss → take_profit → trailing_stop → max_holding_days)
           → today 체결 (execution_date == today)
        d. exit_signal True + next_date 존재 → 다음 거래일 시가 매도 (FIFO)
           → execution_date = next_date, signal_date = today
        e. update_peak_price (그날 high를 peak에 반영, 다음날부터 적용)

    2. 신규 매수 후보 수집 (active universe × 미보유 × final_entry_signal True):
        - active universe는 universe_resolver(today)가 결정 (미지정 시 prices.keys())
        - 후보 정렬: symbol ASC tie-breaker (priority 알고리즘은 step 021)

    3. 매수 처리 (정렬된 후보 순회 — max_positions 미적용, step 022 영역):
        - 후보별로 _maybe_buy 호출
        - cash 부족 시 그 후보부터 skip (CashManager가 enabled면 사전 확보 시도)

    4. 일별 자산 기록 (Portfolio 전체 기준)

마지막 봉(next_date == NaN)에서는 next_open 체결이 불가능하므로 신규 매수 /
exit_signal 매도가 모두 skip된다. exit_position(갭/일중/trailing/max_holding)은
당일 체결이므로 마지막 봉에서도 정상 평가된다. 본 정책은 모든 종목에 일관 적용.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as date_type
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
    """단일/복수 종목 백테스트 엔진.

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

    def run(
        self,
        prices: dict[str, pd.DataFrame] | pd.DataFrame,
        universe_resolver: Callable[[date_type], list[str]] | None = None,
    ) -> BacktestResult:
        """단일 또는 복수 종목 시세에 대해 백테스트를 실행하고 결과를 반환.

        Parameters
        ----------
        prices
            - `pd.DataFrame` 단일 입력 시 자동으로 `{config.symbol: df}`로 wrap된다
              (015 이전 호환성 — Phase 1 골든 fixture 그대로 통과).
            - `dict[str, pd.DataFrame]` 입력 시 각 symbol에 대해 신호 생성 +
              일별 루프에서 후보로 평가.
            각 df는 다음 컬럼을 가진다고 가정:
                adj_open, adj_high, adj_low, adj_close, adj_volume
                next_open, next_close (PriceLoader에서 미리 채움)
                date 컬럼 또는 인덱스가 datetime.
            next_date 컬럼이 없으면 본 메서드가 채운다 (date만 1칸 shift; 가격/조건은
            보지 않음 — look-ahead 차단).
        universe_resolver
            `(today: date) -> list[str]` 콜러블. 일별 active universe(매수 후보로
            평가될 종목 집합)를 결정한다. 미지정 시 prices의 모든 종목을 매일 사용.
            보유 포지션 평가는 universe_resolver와 무관하게 항상 portfolio.positions
            전체를 평가한다 (이미 보유한 종목이 universe에서 빠져도 매도 평가는 진행).

        Returns
        -------
        BacktestResult
            기존 단일 종목 호출과 동일 인터페이스. trade_executions / daily_equity
            / final_cash / final_equity 모두 채워짐.

        Notes
        -----
        - 결정론: 종목 순회는 `sorted(...)`로 명시 정렬. dict 순회 의존 없음.
        - look-ahead bias 차단: next_date는 미리 채우지만 본 row 평가에서 next 가격/
          조건을 사용하지 않음. 매일 today를 기준으로 그 시점의 universe만 매수 후보.
        - 후보 정렬: 본 step에서는 symbol ASC만. priority 알고리즘은 step 021에서
          본 메서드의 후보 정렬 부분(_collect_entry_candidates)을 교체.
        """
        prices_dict = self._normalize_prices(prices)

        # 종목별 신호 생성 + next_date 채우기.
        signaled: dict[str, pd.DataFrame] = {}
        for symbol in sorted(prices_dict.keys()):
            df_sym = prices_dict[symbol]
            df_sym = self.strategy_engine.generate_signals(df_sym)
            df_sym = self._ensure_next_date(df_sym)
            signaled[symbol] = df_sym

        # 종목별 row 인덱스: today(date) → row(Series).
        # 동일 date에 여러 row가 있으면 마지막 것을 사용 (입력 결손 방지 — 정상적인
        # 데이터에서는 유일).
        rows_by_date: dict[str, dict[date_type, pd.Series]] = {}
        for symbol, df_sym in signaled.items():
            row_map: dict[date_type, pd.Series] = {}
            for idx in range(len(df_sym)):
                row = df_sym.iloc[idx]
                today = self._row_date(row, idx)
                row_map[today] = row
            rows_by_date[symbol] = row_map

        # 전체 거래일: 모든 symbol df의 date 합집합 후 정렬.
        all_dates: set[date_type] = set()
        for row_map in rows_by_date.values():
            all_dates.update(row_map.keys())
        trading_dates = sorted(all_dates)

        exit_position_rules = self._get_exit_position_rules()

        result = BacktestResult(
            initial_cash=self.portfolio.initial_cash,
        )

        peak_equity = self.portfolio.initial_cash

        for today in trading_dates:
            if today < self.config.start_date or today > self.config.end_date:
                continue

            # === 1. 보유 포지션 평가 ===
            # 015 흐름과 호환: today 시작 시점에 보유 중이던 종목만 매도 평가.
            # 같은 today에 청산된 종목은 매수 후보로 다시 평가하지 않는다 (단일 종목
            # 흐름이 `if/elif`로 매수와 매도를 상호 배타로 처리하던 의미를 보존 —
            # Phase 1 골든 fixture 정합성 유지).
            held_at_open = sorted(self.portfolio.positions.keys())
            for symbol in held_at_open:
                # 평가 도중 청산되었을 수 있으므로 재확인.
                if symbol not in self.portfolio.positions:
                    continue

                row_map = rows_by_date.get(symbol)
                if row_map is None:
                    # universe에는 없는 (이미 매수해서 보유 중인) 종목의 시세가
                    # 없는 경우. 마지막 종가를 그대로 유지 (04번 §6 Step 2 준수).
                    continue
                row = row_map.get(today)
                if row is None:
                    # 그날 시세 결손 → 평가 불가. 마지막 종가 유지.
                    continue

                if self.config.skip_no_volume and row["adj_volume"] == 0:
                    # 거래정지 — 매수/매도 모두 skip (정확성 정책 13.4.4).
                    continue

                self._evaluate_held_symbol(
                    symbol=symbol,
                    row=row,
                    today=today,
                    exit_position_rules=exit_position_rules,
                    result=result,
                )

            # === 2. 신규 매수 후보 수집 + 3. 매수 처리 ===
            active_universe = self._resolve_active_universe(
                today=today,
                universe_resolver=universe_resolver,
                prices_keys=signaled.keys(),
            )
            entry_candidates = self._collect_entry_candidates(
                today=today,
                active_universe=active_universe,
                rows_by_date=rows_by_date,
            )
            held_at_open_set = set(held_at_open)
            for symbol, row in entry_candidates:
                # today 시작 시점에 보유 중이던 종목은 (같은 today에 청산되어
                # 미보유가 되었어도) 매수 후보에서 제외 — 015 호환. allow_pyramiding
                # 도입 시에도 이 의미는 유지되어야 한다 (같은 봉 회전 매매 방지).
                if symbol in held_at_open_set:
                    continue
                # 보유 평가에서 다른 종목 매도로 청산된 자리 등에서도, 신규
                # 매수 대상이 같은 today 동안 추가로 보유 종목이 되는 것은 가능.
                # (예: A 매도 + B 신규 매수가 같은 today에 동시 발생.)
                # Portfolio.buy의 allow_pyramiding=False 기본값이 이미 같은 종목
                # 중복 매수를 차단한다.
                if symbol in self.portfolio.positions:
                    continue
                self._maybe_buy(symbol, row, today, result)

            # === 4. 일별 자산 기록 ===
            peak_equity = max(peak_equity, self.portfolio.total_equity())
            self._record_daily_equity(result, today, peak_equity)

        result.final_cash = self.portfolio.cash
        result.final_equity = self.portfolio.total_equity()
        result.trade_executions = list(self.portfolio.trade_logs)
        return result

    # === 입력 정규화 ===

    def _normalize_prices(
        self, prices: dict[str, pd.DataFrame] | pd.DataFrame
    ) -> dict[str, pd.DataFrame]:
        """단일 DataFrame은 `{config.symbol: df}`로 wrap. dict는 그대로 반환.

        호환성 유지 — 015 이전의 단일 종목 호출 (`engine.run(df)`)이 그대로
        동작하도록 한다. dict로 받으면 빈 dict 또는 잘못된 타입을 명시적으로
        거부.
        """
        if isinstance(prices, pd.DataFrame):
            return {self.config.symbol: prices}
        if isinstance(prices, dict):
            if not prices:
                raise ValueError("prices dict가 비어 있습니다 — 매수할 종목이 없습니다")
            for symbol, df in prices.items():
                if not isinstance(df, pd.DataFrame):
                    raise TypeError(
                        f"prices['{symbol}']가 DataFrame이 아닙니다: {type(df).__name__}"
                    )
            return prices
        raise TypeError(
            f"prices는 DataFrame 또는 dict[str, DataFrame]이어야 합니다: "
            f"{type(prices).__name__}"
        )

    # === 일별 루프 헬퍼 ===

    def _evaluate_held_symbol(
        self,
        *,
        symbol: str,
        row: pd.Series,
        today: date_type,
        exit_position_rules: list[dict],
        result: BacktestResult,
    ) -> None:
        """보유 종목 1개에 대해 today의 매도 평가 + peak 갱신.

        흐름은 015 이전의 단일 종목 분기와 동일:
            1. update_market_price (current_price만)
            2. exit_position 평가 (갭/일중/trailing/max_holding) — today 체결
            3. exit_signal True → next_open 매도 — execution_date = next_date
            4. peak_price 갱신 (그날 high — 다음날부터 trailing 적용)
        """
        # 1. current_price만 갱신 (peak는 평가 후) — 13.3.5 / 13.15 look-ahead 방지
        self.portfolio.update_market_price(symbol, float(row["adj_close"]))

        # 2. exit_position 평가 (정확성 정책 13.3 + 03번 §4 — Registry 라우팅)
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
            return  # 청산 후 peak 갱신 불필요

        # 3. exit_signal 평가 → 다음 거래일 시가 매도
        next_date = self._next_date_or_none(row)
        if (
            bool(row["exit_signal"])
            and not pd.isna(row.get("next_open"))
            and next_date is not None
        ):
            self._process_sell_at_price(
                symbol=symbol,
                price=float(row["next_open"]),
                quantity=self.portfolio.positions[symbol].quantity,
                on_date=next_date,
                reason="exit_signal",
                result=result,
                signal_date=today,
            )

        # 4. 평가 종료 후 그날 high를 peak에 반영 (다음날부터 trailing 적용)
        if symbol in self.portfolio.positions:
            self.portfolio.update_peak_price(symbol, float(row["adj_high"]))

    def _resolve_active_universe(
        self,
        *,
        today: date_type,
        universe_resolver: Callable[[date_type], list[str]] | None,
        prices_keys,
    ) -> list[str]:
        """일별 active universe 결정.

        universe_resolver가 주어지면 그 결과를 사용 (resolver 책임으로 정렬).
        None이면 prices의 모든 종목을 매일 사용.
        """
        if universe_resolver is None:
            return sorted(prices_keys)
        resolved = universe_resolver(today)
        # resolver는 list를 반환하지만 호출자가 결정론을 깨지 않도록 정렬 강제.
        return sorted(resolved)

    def _collect_entry_candidates(
        self,
        *,
        today: date_type,
        active_universe: list[str],
        rows_by_date: dict[str, dict[date_type, pd.Series]],
    ) -> list[tuple[str, pd.Series]]:
        """active_universe 중 final_entry_signal=True인 후보를 (symbol, row)로 반환.

        본 step에서는 symbol ASC tie-breaker만 적용. priority 알고리즘은 step 021
        에서 본 메서드를 교체하여 도입한다. 따라서 본 메서드의 시그니처/위치를
        다음 step이 참조한다.

        결정론: active_universe는 sorted된 상태로 들어옴 (_resolve_active_universe
        에서 강제). 본 메서드는 그 순서를 그대로 유지한다.
        """
        candidates: list[tuple[str, pd.Series]] = []
        for symbol in active_universe:
            row_map = rows_by_date.get(symbol)
            if row_map is None:
                continue
            row = row_map.get(today)
            if row is None:
                continue
            # 거래정지 종목은 매수 후보에서 제외 (정확성 정책 13.4.4).
            if self.config.skip_no_volume and row["adj_volume"] == 0:
                continue
            if not bool(row["final_entry_signal"]):
                continue
            candidates.append((symbol, row))
        return candidates

    # === 헬퍼 ===

    def _row_date(self, row: pd.Series, idx: int):
        """row에서 날짜 추출. 'date' 컬럼 또는 DatetimeIndex 가정."""
        if "date" in row.index:
            value = row["date"]
            return value.date() if hasattr(value, "date") else value
        # DatetimeIndex
        ts = row.name
        return ts.date() if hasattr(ts, "date") else ts

    def _ensure_next_date(self, df: pd.DataFrame) -> pd.DataFrame:
        """df에 next_date 컬럼이 없으면 채운다 (date만 1칸 shift; look-ahead 차단).

        - 'date' 컬럼이 있으면 `df["date"].shift(-1)`를 사용.
        - 없으면 DatetimeIndex를 가정하고 인덱스를 1칸 shift.
        - 마지막 row의 next_date는 NaT — _next_date_or_none이 None으로 변환.

        next row의 가격(open/close)이나 신호는 절대 보지 않는다 — execution
        시점 결정에만 사용. PriceLoader가 14번 문서에 맞춰 next_date를 미리
        채우는 환경에서는 본 메서드가 no-op로 동작한다.
        """
        if "next_date" in df.columns:
            return df
        df = df.copy()
        if "date" in df.columns:
            df["next_date"] = df["date"].shift(-1)
        else:
            df["next_date"] = pd.Series(df.index, index=df.index).shift(-1)
        return df

    def _next_date_or_none(self, row: pd.Series):
        """row["next_date"]를 date로 정규화. NaT/NaN이면 None.

        pandas Timestamp는 .date()로 변환, datetime.date는 그대로 반환.
        date 타입은 .date()를 가지지 않으므로 hasattr만으로 충분히 분기됨.
        """
        if "next_date" not in row.index:
            return None
        value = row["next_date"]
        if pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            return value.date()
        if hasattr(value, "date") and callable(value.date):
            # datetime.datetime 등
            return value.date()
        return value

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
        """매수 시도. 갭 초과 / 거래정지 / 예수금 부족(CashManager 시도) 시 skip.

        signal_date = today (신호 발생일), execution_date = next_date
        (다음 거래일). cash_manager 강제 매도/매수는 그 시점에 즉시 체결되므로
        today를 그대로 전달한다.

        next_date 또는 next_open이 없는 경우(마지막 봉)는 본 메서드 진입 전에
        호출자가 차단하지만, 방어적으로 한 번 더 체크한다.
        """
        if pd.isna(row.get("next_open")):
            return

        next_open = float(row["next_open"])
        prev_close = float(row["adj_close"])
        execution_date = self._next_date_or_none(row)
        if execution_date is None:
            return

        # 다음 거래일 거래정지 체크 (정확성 정책 13.4.2)
        next_volume = row.get("next_volume")
        if self.config.skip_no_volume and next_volume is not None and next_volume == 0:
            return

        # 갭 체크 (정확성 정책 13.4.1)
        gap_pct = (next_open - prev_close) / prev_close * 100
        if gap_pct > self.config.max_gap_pct_for_entry:
            return

        # 사전 fund 확보 (CashManager 옵션) — 강제 매도는 today 즉시 체결.
        if self.cash_manager is not None and self.cash_manager.enabled:
            # 추정 비용으로 미리 cash 확보 시도 — ExecutionResult.net_amount 사용
            est_price = self.execution_model.apply_slippage_and_tick(
                next_open, side="buy", market=self.config.market
            )
            est_quantity = int(self.config.position_size_amount // max(est_price, 1))
            if est_quantity > 0:
                est_execution = self.execution_model.calculate_buy_cost(
                    est_price, est_quantity, raw_price=next_open
                )
                events = self.cash_manager.handle_shortage(
                    self.portfolio,
                    required_cash=est_execution.net_amount,
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

        execution = self.execution_model.calculate_buy_cost(
            exec_price, quantity, raw_price=next_open
        )
        if execution.net_amount > self.portfolio.cash:
            return

        self.portfolio.buy(
            symbol=symbol,
            price=exec_price,
            quantity=quantity,
            on_date=execution_date,
            reason="entry_signal",
            execution=execution,
            signal_date=today,
        )

    def _process_sell_at_price(
        self,
        symbol: str,
        price: float,
        quantity: int,
        on_date,
        reason: str,
        result: BacktestResult,
        signal_date=None,
    ) -> None:
        """price를 슬리피지/호가/세금 처리한 뒤 FIFO로 매도.

        Parameters
        ----------
        on_date
            **체결일 (execution_date)**. exit_signal next_open 매도는 next_date,
            갭/일중/trailing/max_holding 등 당일 체결 경로는 today.
        signal_date
            신호 발생일. exit_signal 경로에서만 today를 전달, 나머지는 None
            (= execution_date와 동일).

        ExecutionResult를 sell_symbol_fifo에 전달하여 fee/tax/net이 분해된 채로
        Portfolio.trade_logs에 기록되게 한다 (리뷰 011 H1 + M2 + M4). 거래세
        (시계열) 적용은 execution_date 기준 — 매도 체결일이 속하는 세율을 사용
        (정확성 정책 13.6).
        """
        # 갭 손절/익절은 시가 그대로 체결 (이미 정확성 정책에 따라 호출자가 결정)
        # 슬리피지는 모든 매도에 보수적으로 적용
        exec_price = self.execution_model.apply_slippage_and_tick(
            price, side="sell", market=self.config.market
        )
        execution = self.execution_model.calculate_sell_proceeds(
            exec_price, quantity, on_date, raw_price=price
        )
        self.portfolio.sell_symbol_fifo(
            symbol=symbol,
            price=exec_price,
            quantity=quantity,
            on_date=on_date,
            reason=reason,
            execution=execution,
            signal_date=signal_date,
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

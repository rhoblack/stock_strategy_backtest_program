"""KRW int 금액 처리 테스트 — 정확성 정책 §14.

검증 항목 (정확성 정책 13.17 매핑):
  - ExecutionResult.gross_amount / fee / tax / net_amount 가 정수(int)임을 보장
  - Portfolio.cash가 정수임을 보장
  - DailyEquity.cash / stock_value / total_equity 가 정수임을 보장
  - BacktestResult.initial_cash / final_cash / final_equity 가 정수임을 보장
  - float 잔액으로 인한 음수 오차 방지 (부동소수 누적 오차 시나리오)
  - 거래세 반복 연산 후 int 일관성
  - _round_krw() round-half-up 동작 확인

step 034 — 트랙 A (13-s: 통화 KRW Decimal/int)
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import app.strategy  # noqa: F401 — 5개 기본 조건 자동 등록
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel, ExecutionResult, _round_krw
from app.backtest.metrics import calculate_metrics
from app.backtest.result import BacktestResult, DailyEquity
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine


# ============================================================================
# 헬퍼
# ============================================================================


def _build_series(n: int, seed: int = 42, start_price: float = 10_000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.001, scale=0.02, size=n)
    closes = start_price * np.exp(np.cumsum(returns))
    closes = closes.round(0)

    base_date = date(2024, 1, 2)
    dates = [base_date + timedelta(days=i) for i in range(n)]
    opens = closes * 1.002
    highs = closes * 1.015
    lows = closes * 0.985

    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": opens.round(0),
            "adj_high": highs.round(0),
            "adj_low": lows.round(0),
            "adj_close": closes,
            "adj_volume": np.full(n, 10_000.0),
        }
    )
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def _run_engine(
    strategy: dict,
    df: pd.DataFrame,
    *,
    initial_cash: int = 10_000_000,
    position_size_amount: float = 5_000_000,
    fee_rate: float = 0.0,
    tax_rate: float = 0.0,
    slippage: float = 0.0,
    tick_rounding: str = "nearest",
) -> tuple[BacktestResult, dict]:
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=fee_rate,
        tax_rate=tax_rate,
        slippage=slippage,
        tick_rounding=tick_rounding,
    )
    config = BacktestConfig(
        symbol="TEST",
        start_date=df["date"].iloc[0],
        end_date=df["date"].iloc[-1],
        position_size_amount=position_size_amount,
        initial_cash=initial_cash,
    )
    engine = BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)
    result = engine.run(df)
    metrics = calculate_metrics(result)
    return result, metrics


_SIMPLE_STRATEGY = {
    "entry": {
        "logic": "AND",
        "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
    },
    "exit_position": {
        "logic": "OR",
        "conditions": [
            {"type": "take_profit", "percent": 5.0},
            {"type": "stop_loss", "percent": 3.0},
        ],
    },
}


# ============================================================================
# A1. _round_krw 헬퍼 동작 검증
# ============================================================================


class TestRoundKrw:
    """_round_krw() — round-half-up (banker's rounding 아님) 검증."""

    def test_exact_integer_unchanged(self):
        assert _round_krw(100.0) == 100
        assert _round_krw(0.0) == 0

    def test_half_rounds_up(self):
        """0.5는 올림 (banker's rounding이라면 0으로 내림하지만 §14 정책은 올림)."""
        assert _round_krw(0.5) == 1
        assert _round_krw(1.5) == 2
        assert _round_krw(16.5) == 17  # 110_000 * 0.00015 = 16.5

    def test_less_than_half_rounds_down(self):
        assert _round_krw(0.4) == 0
        assert _round_krw(16.4) == 16

    def test_returns_int_type(self):
        result = _round_krw(16.5)
        assert isinstance(result, int)

    def test_large_krw_value(self):
        """10,000,000원 * 0.0015 = 15,000 (정확한 정수)."""
        assert _round_krw(10_000_000 * 0.0015) == 15_000

    def test_tax_scenario(self):
        """거래세 시나리오: gross=110_000, rate=0.00015 → 16.5 → 17."""
        gross = 110_000
        fee = _round_krw(gross * 0.00015)
        assert fee == 17

    def test_repeated_rounding_no_accumulation(self):
        """같은 연산을 100번 반복해도 결과가 동일해야 함 (결정론)."""
        results = [_round_krw(110_000 * 0.00015) for _ in range(100)]
        assert all(r == 17 for r in results)


# ============================================================================
# A2. ExecutionResult 필드 타입 검증
# ============================================================================


class TestExecutionResultIntTypes:
    """ExecutionResult.gross_amount / fee / tax / net_amount / slippage_applied가 int."""

    def test_buy_cost_fields_are_int(self):
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0023, slippage=0.0)
        res = em.calculate_buy_cost(price=10_000, quantity=100)
        assert isinstance(res.gross_amount, int), "gross_amount must be int"
        assert isinstance(res.fee, int), "fee must be int"
        assert isinstance(res.tax, int), "tax must be int"
        assert isinstance(res.net_amount, int), "net_amount must be int"
        assert isinstance(res.slippage_applied, int), "slippage_applied must be int"

    def test_sell_proceeds_fields_are_int(self):
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.0)
        res = em.calculate_sell_proceeds(price=10_000, quantity=100, on_date=date(2024, 6, 1))
        assert isinstance(res.gross_amount, int)
        assert isinstance(res.fee, int)
        assert isinstance(res.tax, int)
        assert isinstance(res.net_amount, int)

    def test_buy_net_equals_gross_plus_fee(self):
        """BUY: net_amount == gross + fee (정수 덧셈이라 오차 없음)."""
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0, slippage=0.0)
        res = em.calculate_buy_cost(price=9_837, quantity=509)
        assert res.net_amount == res.gross_amount + res.fee

    def test_sell_net_equals_gross_minus_fee_minus_tax(self):
        """SELL: net_amount == gross - fee - tax (정수 뺄셈이라 오차 없음)."""
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.0)
        res = em.calculate_sell_proceeds(price=10_347, quantity=483, on_date=date(2024, 9, 1))
        assert res.net_amount == res.gross_amount - res.fee - res.tax

    def test_tax_zero_for_buy(self):
        """BUY: tax는 항상 0."""
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0023, slippage=0.0)
        res = em.calculate_buy_cost(price=50_000, quantity=200)
        assert res.tax == 0
        assert isinstance(res.tax, int)

    def test_slippage_applied_is_int(self):
        em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.001)
        res = em.calculate_buy_cost(price=10_000, quantity=10, raw_price=9_990)
        assert isinstance(res.slippage_applied, int)

    def test_timeseries_tax_gives_int(self):
        """시계열 거래세 적용 결과도 int."""
        em = ExecutionModel(
            fee_rate=0.0,
            tax_rate=[
                {"from": "2023-01-01", "rate": 0.0020},
                {"from": "2024-01-01", "rate": 0.0018},
                {"from": "2025-01-01", "rate": 0.0015},
            ],
            slippage=0.0,
        )
        for d, rate in [
            (date(2023, 6, 1), 0.0020),
            (date(2024, 6, 1), 0.0018),
            (date(2025, 6, 1), 0.0015),
        ]:
            res = em.calculate_sell_proceeds(price=10_000, quantity=50, on_date=d)
            assert isinstance(res.tax, int)
            assert res.tax == _round_krw(res.gross_amount * rate)


# ============================================================================
# A3. Portfolio.cash 타입 검증
# ============================================================================


class TestPortfolioCashIntTypes:
    """Portfolio.cash / initial_cash 가 항상 int."""

    def test_initial_cash_is_int(self):
        p = Portfolio(initial_cash=10_000_000)
        assert isinstance(p.cash, int)
        assert isinstance(p.initial_cash, int)
        assert p.cash == 10_000_000
        assert p.initial_cash == 10_000_000

    def test_float_initial_cash_converted_to_int(self):
        """float로 초기화해도 내부에서 int로 변환."""
        p = Portfolio(initial_cash=10_000_000.0)
        assert isinstance(p.cash, int)
        assert p.cash == 10_000_000

    def test_cash_after_buy_is_int(self):
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0, slippage=0.0)
        p = Portfolio(initial_cash=10_000_000)
        execution = em.calculate_buy_cost(price=10_000, quantity=500)
        p.buy("005930", price=10_000, quantity=500, on_date=date(2024, 6, 1), execution=execution)
        assert isinstance(p.cash, int)

    def test_cash_after_sell_is_int(self):
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.0)
        p = Portfolio(initial_cash=10_000_000)
        tg_id = p.buy("005930", price=10_000, quantity=500, on_date=date(2024, 6, 1))
        sell_exec = em.calculate_sell_proceeds(price=11_000, quantity=500, on_date=date(2024, 6, 20))
        p.sell_trade_group("005930", tg_id, price=11_000, quantity=500,
                           on_date=date(2024, 6, 20), reason="take_profit", execution=sell_exec)
        assert isinstance(p.cash, int)

    def test_no_negative_float_rounding_on_zero_balance(self):
        """부동소수 누적 오차로 인한 음수 잔액 방지 시나리오.

        fee_rate=0.001이면 10,000원 * 10주 = 100,000, fee=100, net=100,100.
        초기 자금을 net과 정확히 맞추면 매수 후 잔액이 정확히 0이어야 한다.
        float 연산이었다면 -0.00001 같은 음수 오차가 발생할 수 있지만,
        정수 연산이므로 항상 정확히 0이 되어야 한다.
        """
        em = ExecutionModel(fee_rate=0.001, tax_rate=0.0, slippage=0.0)
        execution = em.calculate_buy_cost(price=10_000, quantity=10)
        # gross=100_000, fee=100, net=100_100
        assert execution.net_amount == 100_100

        p = Portfolio(initial_cash=100_100)  # 딱 맞는 초기금
        p.buy("005930", price=10_000, quantity=10, on_date=date(2024, 1, 1), execution=execution)
        # 구매 후 잔액은 정확히 0 (float이면 -0.0001 같은 오차 가능)
        assert p.cash == 0
        assert isinstance(p.cash, int)
        # 잔액이 음수가 되지 않아야 함
        assert p.cash >= 0

    def test_cash_subtraction_is_exact(self):
        """매수 후 cash = initial_cash - net_amount (정수 뺄셈이라 오차 없음)."""
        p = Portfolio(initial_cash=10_000_000)
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0, slippage=0.0)
        execution = em.calculate_buy_cost(price=9_837, quantity=509)
        p.buy("TEST", price=9_837, quantity=509, on_date=date(2024, 1, 1), execution=execution)
        assert p.cash == 10_000_000 - execution.net_amount


# ============================================================================
# A4. DailyEquity / BacktestResult 타입 검증
# ============================================================================


class TestDailyEquityIntTypes:
    """DailyEquity.cash / stock_value / total_equity 가 int."""

    def test_daily_equity_fields_are_int(self):
        result, _ = _run_engine(
            _SIMPLE_STRATEGY,
            _build_series(30, seed=1),
            initial_cash=10_000_000,
        )
        assert result.daily_equity, "daily_equity가 비어있으면 검증 불가"
        for de in result.daily_equity:
            assert isinstance(de.cash, int), f"cash must be int, got {type(de.cash)}"
            assert isinstance(de.stock_value, int), f"stock_value must be int"
            assert isinstance(de.total_equity, int), f"total_equity must be int"
            # drawdown은 비율 float
            assert isinstance(de.drawdown, float), f"drawdown must be float"

    def test_total_equity_equals_cash_plus_stock(self):
        """total_equity == cash + stock_value (정수 덧셈이라 정확히 일치)."""
        result, _ = _run_engine(
            _SIMPLE_STRATEGY,
            _build_series(30, seed=2),
            initial_cash=10_000_000,
        )
        for de in result.daily_equity:
            assert de.total_equity == de.cash + de.stock_value

    def test_backtest_result_cash_fields_are_int(self):
        result, _ = _run_engine(
            _SIMPLE_STRATEGY,
            _build_series(30, seed=3),
            initial_cash=5_000_000,
        )
        assert isinstance(result.initial_cash, int)
        assert isinstance(result.final_cash, int)
        assert isinstance(result.final_equity, int)
        assert result.initial_cash == 5_000_000

    def test_metrics_initial_cash_is_int(self):
        """calculate_metrics가 반환하는 initial_cash / final_equity가 int."""
        result, metrics = _run_engine(
            _SIMPLE_STRATEGY,
            _build_series(30, seed=4),
            initial_cash=10_000_000,
        )
        assert isinstance(metrics["initial_cash"], int)
        assert isinstance(metrics["final_equity"], int)
        # 비율 필드는 float
        assert isinstance(metrics["total_return_pct"], float)
        assert isinstance(metrics["mdd_pct"], float)


# ============================================================================
# A5. 거래세 반복 연산 후 부동소수 오차 없는지 회귀 검증 (정책 §17)
# ============================================================================


class TestFloatAccumulationPrevention:
    """거래세 반복 연산 후 int 일관성 — 정책 §17 회귀."""

    def test_repeated_tax_calculation_gives_same_int(self):
        """동일한 거래세 계산을 1000번 반복해도 결과가 항상 같은 int."""
        em = ExecutionModel(fee_rate=0.0, tax_rate=0.0018, slippage=0.0)
        results = set()
        for _ in range(1_000):
            res = em.calculate_sell_proceeds(price=10_347, quantity=483, on_date=date(2024, 9, 1))
            results.add(res.tax)
        # 결정론: 같은 입력에서는 항상 같은 결과
        assert len(results) == 1, f"비결정론적 결과 발생: {results}"
        # 타입은 항상 int
        assert isinstance(list(results)[0], int)

    def test_sequential_buy_sell_cash_conservation(self):
        """매수→매도 후 cash 잔액이 정확히 정수 덧셈/뺄셈으로 계산됨.

        float 누적 오차가 없다면: final_cash = initial - buy_cost + sell_proceeds
        이 등식이 정수 산술로 정확히 성립해야 한다.
        """
        initial = 10_000_000
        p = Portfolio(initial_cash=initial)
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.0)

        buy_exec = em.calculate_buy_cost(price=10_000, quantity=500)
        tg_id = p.buy("005930", price=10_000, quantity=500,
                      on_date=date(2024, 1, 1), execution=buy_exec)

        sell_exec = em.calculate_sell_proceeds(price=11_000, quantity=500,
                                               on_date=date(2024, 6, 1))
        p.sell_trade_group("005930", tg_id, price=11_000, quantity=500,
                           on_date=date(2024, 6, 1), reason="take_profit",
                           execution=sell_exec)

        expected_cash = initial - buy_exec.net_amount + sell_exec.net_amount
        assert p.cash == expected_cash, (
            f"잔액 불일치: {p.cash} != {expected_cash}"
        )
        assert isinstance(p.cash, int)

    def test_10_round_trips_cash_is_exact_int(self):
        """10번 매수-매도 반복 후 cash가 정확한 정수."""
        initial = 50_000_000
        p = Portfolio(initial_cash=initial)
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.0)

        total_net_gain = 0
        for i in range(10):
            buy_price = 10_000 + i * 100
            sell_price = buy_price + 500  # +5% gain
            qty = 100

            buy_exec = em.calculate_buy_cost(price=buy_price, quantity=qty)
            tg_id = p.buy(f"SYM{i:02d}", price=buy_price, quantity=qty,
                          on_date=date(2024, 1, 1 + i), execution=buy_exec)
            sell_exec = em.calculate_sell_proceeds(price=sell_price, quantity=qty,
                                                   on_date=date(2024, 6, 1 + i))
            p.sell_trade_group(f"SYM{i:02d}", tg_id, price=sell_price, quantity=qty,
                               on_date=date(2024, 6, 1 + i), reason="take_profit",
                               execution=sell_exec)
            total_net_gain += sell_exec.net_amount - buy_exec.net_amount

        assert p.cash == initial + total_net_gain
        assert isinstance(p.cash, int)

    def test_realized_profit_is_int(self):
        """sell_trade_group 후 trade_logs에 기록된 realized_profit이 int."""
        p = Portfolio(initial_cash=5_000_000)
        em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.0)
        tg_id = p.buy("005930", price=10_000, quantity=200, on_date=date(2024, 1, 1))
        sell_exec = em.calculate_sell_proceeds(price=11_000, quantity=200,
                                               on_date=date(2024, 6, 1))
        p.sell_trade_group("005930", tg_id, price=11_000, quantity=200,
                           on_date=date(2024, 6, 1), reason="take_profit",
                           execution=sell_exec)
        log = p.trade_logs[-1]
        assert isinstance(log["gross_amount"], int)
        assert isinstance(log["fee"], int)
        assert isinstance(log["tax"], int)
        assert isinstance(log["net_amount"], int)
        assert isinstance(log["realized_profit"], int)

    def test_cash_never_becomes_negative_due_to_rounding(self):
        """반올림 오차로 cash가 음수가 되는 버그가 없는지 확인.

        fee가 소수인 경우 (예: 110_000 * 0.00015 = 16.5) round-half-up 결과로
        매수 비용이 예산보다 1원 더 나올 수 있다. Portfolio 예산 부족 에러가
        발생해야지 음수 잔액이 발생하면 안 된다.
        """
        # gross = 110_000, fee = 17 (round up from 16.5), net = 110_017
        em = ExecutionModel(fee_rate=0.00015, tax_rate=0.0, slippage=0.0)
        execution = em.calculate_buy_cost(price=11_000, quantity=10)
        assert execution.net_amount == 110_017  # 110_000 + 17

        # 초기 자금이 net과 정확히 같으면 매수 성공
        p = Portfolio(initial_cash=110_017)
        p.buy("TEST", price=11_000, quantity=10, on_date=date(2024, 1, 1), execution=execution)
        assert p.cash == 0

        # 초기 자금이 1원 부족하면 ValueError
        p2 = Portfolio(initial_cash=110_016)
        with pytest.raises(ValueError, match="예수금 부족"):
            p2.buy("TEST", price=11_000, quantity=10, on_date=date(2024, 1, 1), execution=execution)


# ============================================================================
# A6. 엔진 통합: 금액 필드 int 일관성 (비용 포함 시나리오)
# ============================================================================


class TestEngineIntAmountsIntegration:
    """BacktestEngine 실행 후 trade_logs와 daily_equity의 금액 필드가 int."""

    def test_trade_logs_amount_fields_are_int(self):
        result, _ = _run_engine(
            _SIMPLE_STRATEGY,
            _build_series(60, seed=7),
            initial_cash=10_000_000,
            fee_rate=0.0015,
            tax_rate=0.0018,
            slippage=0.001,
        )
        if not result.trade_executions:
            pytest.skip("체결 없음 — 시나리오 검토 필요")
        for log in result.trade_executions:
            for field in ("gross_amount", "fee", "tax", "net_amount"):
                val = log[field]
                assert isinstance(val, int), (
                    f"trade_log['{field}'] = {val!r} (type={type(val).__name__}) — must be int"
                )

    def test_daily_equity_fields_are_int_with_costs(self):
        result, _ = _run_engine(
            _SIMPLE_STRATEGY,
            _build_series(60, seed=8),
            initial_cash=10_000_000,
            fee_rate=0.0015,
            tax_rate=0.0018,
            slippage=0.001,
        )
        for de in result.daily_equity:
            assert isinstance(de.cash, int)
            assert isinstance(de.stock_value, int)
            assert isinstance(de.total_equity, int)

    def test_total_equity_consistency_with_costs(self):
        """비용 적용 후에도 total_equity == cash + stock_value 항등식 성립."""
        result, _ = _run_engine(
            _SIMPLE_STRATEGY,
            _build_series(90, seed=9),
            initial_cash=10_000_000,
            fee_rate=0.0015,
            tax_rate=0.0018,
            slippage=0.001,
        )
        for de in result.daily_equity:
            assert de.total_equity == de.cash + de.stock_value

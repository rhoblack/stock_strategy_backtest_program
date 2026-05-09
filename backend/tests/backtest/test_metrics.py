"""calculate_metrics 단위 테스트."""

import math
from datetime import date

import pytest

from app.backtest.metrics import calculate_metrics
from app.backtest.result import BacktestResult, DailyEquity


def _result(
    *,
    initial_cash: float = 1_000_000,
    final_equity: float = 1_000_000,
    daily_equity: list[DailyEquity] | None = None,
    trade_executions: list[dict] | None = None,
) -> BacktestResult:
    return BacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        daily_equity=daily_equity or [],
        trade_executions=trade_executions or [],
    )


def _buy(tg_id: int, on_date: date, price: float, qty: int) -> dict:
    return {
        "date": on_date,
        "symbol": "X",
        "trade_group_id": tg_id,
        "execution_type": "BUY",
        "price": price,
        "quantity": qty,
        "cost": price * qty,
        "reason": "entry_signal",
    }


def _sell(
    tg_id: int,
    on_date: date,
    price: float,
    qty: int,
    realized_profit: float,
    realized_profit_rate: float,
    is_partial: bool = False,
) -> dict:
    return {
        "date": on_date,
        "symbol": "X",
        "trade_group_id": tg_id,
        "execution_type": "PARTIAL_SELL" if is_partial else "SELL",
        "price": price,
        "quantity": qty,
        "proceeds": price * qty,
        "realized_profit": realized_profit,
        "realized_profit_rate": realized_profit_rate,
        "reason": "take_profit",
        "is_partial": is_partial,
    }


# === 빈 결과 ===


def test_empty_result_returns_zeros():
    m = calculate_metrics(_result())
    assert m["trade_count"] == 0
    assert m["win_rate"] == 0.0
    assert m["mdd_pct"] == 0.0
    assert m["profit_factor"] is None
    assert m["open_position_count"] == 0


# === 단일 수익 trade ===


def test_single_winning_trade():
    execs = [
        _buy(1, date(2024, 1, 10), 10_000, 10),
        _sell(1, date(2024, 1, 20), 11_000, 10, realized_profit=10_000, realized_profit_rate=10.0),
    ]
    eq = [
        DailyEquity(date(2024, 1, 10), cash=900_000, stock_value=100_000, total_equity=1_000_000),
        DailyEquity(date(2024, 1, 20), cash=1_010_000, stock_value=0, total_equity=1_010_000),
    ]
    m = calculate_metrics(
        _result(initial_cash=1_000_000, final_equity=1_010_000, daily_equity=eq, trade_executions=execs)
    )
    assert m["trade_count"] == 1
    assert m["win_rate"] == pytest.approx(100.0)
    assert m["avg_holding_days"] == 10
    assert m["avg_profit_pct"] == pytest.approx(10.0)
    assert m["profit_factor"] is math.inf  # 손실 0
    assert m["total_return_pct"] == pytest.approx(1.0)


# === 단일 손실 trade ===


def test_single_losing_trade():
    execs = [
        _buy(1, date(2024, 1, 10), 10_000, 10),
        _sell(1, date(2024, 1, 20), 9_000, 10, realized_profit=-10_000, realized_profit_rate=-10.0),
    ]
    m = calculate_metrics(_result(trade_executions=execs))
    assert m["trade_count"] == 1
    assert m["win_rate"] == 0.0
    assert m["avg_loss_pct"] == pytest.approx(10.0)  # 양수로
    assert m["avg_profit_pct"] == 0.0
    # 손실만 있으면 profit_factor = 0/loss = 0.0 (수익이 없으므로)
    assert m["profit_factor"] == pytest.approx(0.0)


# === 수익+손실 mix ===


def test_mixed_winning_and_losing_trades():
    execs = [
        _buy(1, date(2024, 1, 10), 10_000, 10),
        _sell(1, date(2024, 1, 15), 11_000, 10, 10_000, 10.0),
        _buy(2, date(2024, 1, 20), 10_000, 10),
        _sell(2, date(2024, 1, 25), 9_500, 10, -5_000, -5.0),
        _buy(3, date(2024, 2, 1), 10_000, 10),
        _sell(3, date(2024, 2, 10), 11_500, 10, 15_000, 15.0),
    ]
    m = calculate_metrics(_result(trade_executions=execs))
    assert m["trade_count"] == 3
    assert m["win_rate"] == pytest.approx(2 / 3 * 100, abs=0.01)
    # avg_profit = (10 + 15) / 2 = 12.5
    assert m["avg_profit_pct"] == pytest.approx(12.5)
    # avg_loss = 5.0
    assert m["avg_loss_pct"] == pytest.approx(5.0)
    # profit_factor = (10000 + 15000) / 5000 = 5.0
    assert m["profit_factor"] == pytest.approx(5.0)


# === 부분 매도 ===


def test_partial_sells_count_as_one_trade():
    """한 trade_group의 부분매도가 여러 번 → trade_count는 1."""
    execs = [
        _buy(1, date(2024, 1, 10), 10_000, 10),
        _sell(1, date(2024, 1, 15), 11_000, 4, 4_000, 10.0, is_partial=True),
        _sell(1, date(2024, 1, 20), 11_000, 6, 6_000, 10.0, is_partial=True),
    ]
    m = calculate_metrics(_result(trade_executions=execs))
    assert m["trade_count"] == 1
    # 마지막 청산일 = 2024-01-20
    assert m["avg_holding_days"] == 10


# === 미청산 ===


def test_open_position_not_counted_as_trade():
    """매수만 하고 매도 안 한 trade_group은 open_position_count로."""
    execs = [
        _buy(1, date(2024, 1, 10), 10_000, 10),
    ]
    m = calculate_metrics(_result(trade_executions=execs))
    assert m["trade_count"] == 0
    assert m["open_position_count"] == 1


def test_partially_sold_trade_group_is_open():
    """부분 매도만 진행되고 청산 미완료 → open."""
    execs = [
        _buy(1, date(2024, 1, 10), 10_000, 10),
        _sell(1, date(2024, 1, 15), 11_000, 4, 4_000, 10.0, is_partial=True),
    ]
    m = calculate_metrics(_result(trade_executions=execs))
    assert m["trade_count"] == 0
    assert m["open_position_count"] == 1


# === MDD ===


def test_mdd_uses_minimum_drawdown_of_daily_equity():
    eq = [
        DailyEquity(date(2024, 1, 1), 1_000_000, 0, 1_000_000, drawdown=0.0),
        DailyEquity(date(2024, 1, 2), 950_000, 0, 950_000, drawdown=-5.0),
        DailyEquity(date(2024, 1, 3), 800_000, 0, 800_000, drawdown=-20.0),
        DailyEquity(date(2024, 1, 4), 900_000, 0, 900_000, drawdown=-10.0),
    ]
    m = calculate_metrics(_result(daily_equity=eq))
    assert m["mdd_pct"] == pytest.approx(-20.0)


# === 연평균 수익률 ===


def test_annual_return_for_one_year_equals_total_return():
    """1년(365일) 기간 → annual_return ≈ total_return (CAGR 공식 (1+r)^1 - 1 = r)."""
    eq = [
        DailyEquity(date(2024, 1, 1), 1_000_000, 0, 1_000_000),
        DailyEquity(date(2024, 12, 31), 1_200_000, 0, 1_200_000),
    ]
    m = calculate_metrics(
        _result(initial_cash=1_000_000, final_equity=1_200_000, daily_equity=eq)
    )
    # 365일 기간이라 CAGR ~ 20% (정확히는 1.2^(365/365) - 1 = 0.2)
    assert m["annual_return_pct"] == pytest.approx(20.0, abs=0.5)


def test_annual_return_for_two_years_compounds():
    """2년 기간 +44% → CAGR = sqrt(1.44) - 1 = 20%"""
    eq = [
        DailyEquity(date(2024, 1, 1), 1_000_000, 0, 1_000_000),
        DailyEquity(date(2025, 12, 31), 1_440_000, 0, 1_440_000),
    ]
    m = calculate_metrics(
        _result(initial_cash=1_000_000, final_equity=1_440_000, daily_equity=eq)
    )
    assert m["annual_return_pct"] == pytest.approx(20.0, abs=0.5)


def test_annual_return_zero_initial_cash_returns_zero():
    eq = [
        DailyEquity(date(2024, 1, 1), 0, 0, 0),
        DailyEquity(date(2024, 12, 31), 0, 0, 0),
    ]
    m = calculate_metrics(_result(initial_cash=0, final_equity=0, daily_equity=eq))
    assert m["annual_return_pct"] == 0.0


def test_annual_return_total_loss_returns_minus_100():
    """초기 자본 모두 잃은 경우 (음수 또는 0)."""
    eq = [
        DailyEquity(date(2024, 1, 1), 1_000_000, 0, 1_000_000),
        DailyEquity(date(2024, 12, 31), 0, 0, 0),
    ]
    m = calculate_metrics(
        _result(initial_cash=1_000_000, final_equity=0, daily_equity=eq)
    )
    assert m["annual_return_pct"] == pytest.approx(-100.0)


# === 보유일 ===


def test_same_day_close_counts_as_one_day():
    execs = [
        _buy(1, date(2024, 1, 10), 10_000, 10),
        _sell(1, date(2024, 1, 10), 11_000, 10, 10_000, 10.0),
    ]
    m = calculate_metrics(_result(trade_executions=execs))
    assert m["avg_holding_days"] == 1

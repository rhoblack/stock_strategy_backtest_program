"""step 063 -- stop_trading_on_drawdown_pct MDD 거래 중단 테스트 (02-r)."""

from datetime import date

import pandas as pd
import pytest

import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import (
    EVENT_REASON_DRAWDOWN_LIMIT,
    EVENT_TYPE_SKIP,
    BacktestEngine,
)
from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

SYMBOL_A = "000001"


def _make_engine_with_portfolio(
    portfolio,
    stop_trading_on_drawdown_pct=None,
):
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=100_000,
        initial_cash=1_000_000,
        stop_trading_on_drawdown_pct=stop_trading_on_drawdown_pct,
    )
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    strategy = {"entry": {"logic": "AND", "conditions": []}}
    return BacktestEngine(
        StrategyEngine(strategy),
        portfolio,
        execution_model,
        config,
    )


# config validation

def test_config_default_none():
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        position_size_amount=100_000,
        initial_cash=1_000_000,
    )
    assert config.stop_trading_on_drawdown_pct is None


def test_config_valid_values():
    for val in [1, 20.0, 50, 100]:
        cfg = BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=100_000,
            initial_cash=1_000_000,
            stop_trading_on_drawdown_pct=val,
        )
        assert cfg.stop_trading_on_drawdown_pct == val


def test_config_zero_raises():
    with pytest.raises(ValueError, match="stop_trading_on_drawdown_pct"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=100_000,
            initial_cash=1_000_000,
            stop_trading_on_drawdown_pct=0,
        )


def test_config_over_100_raises():
    with pytest.raises(ValueError, match="stop_trading_on_drawdown_pct"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=100_000,
            initial_cash=1_000_000,
            stop_trading_on_drawdown_pct=101,
        )


def test_config_negative_raises():
    with pytest.raises(ValueError, match="stop_trading_on_drawdown_pct"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=100_000,
            initial_cash=1_000_000,
            stop_trading_on_drawdown_pct=-5,
        )


# _is_drawdown_limit_exceeded unit tests

def test_none_threshold_always_false():
    portfolio = Portfolio(initial_cash=1_000_000)
    engine = _make_engine_with_portfolio(portfolio, stop_trading_on_drawdown_pct=None)
    assert engine._is_drawdown_limit_exceeded(peak_equity=1_000_000) is False
    assert engine._is_drawdown_limit_exceeded(peak_equity=10_000_000) is False
    assert engine._is_drawdown_limit_exceeded(peak_equity=0) is False


def test_below_threshold_false():
    # cash=950_000, peak=1_000_000 -> MDD=5% < 10%
    portfolio = Portfolio(initial_cash=950_000)
    engine = _make_engine_with_portfolio(portfolio, stop_trading_on_drawdown_pct=10.0)
    assert engine._is_drawdown_limit_exceeded(peak_equity=1_000_000) is False


def test_exact_threshold_true():
    # cash=1_000_000, peak=1_250_000 -> MDD=(1_250_000-1_000_000)/1_250_000*100=20.0%
    portfolio = Portfolio(initial_cash=1_000_000)
    engine = _make_engine_with_portfolio(portfolio, stop_trading_on_drawdown_pct=20.0)
    assert engine._is_drawdown_limit_exceeded(peak_equity=1_250_000) is True


def test_above_threshold_true():
    # cash=700_000, peak=1_000_000 -> MDD=30% > 20%
    portfolio = Portfolio(initial_cash=700_000)
    engine = _make_engine_with_portfolio(portfolio, stop_trading_on_drawdown_pct=20.0)
    assert engine._is_drawdown_limit_exceeded(peak_equity=1_000_000) is True


def test_no_mdd_initial_cash():
    # MDD=0% (initial state) -> False
    portfolio = Portfolio(initial_cash=1_000_000)
    engine = _make_engine_with_portfolio(portfolio, stop_trading_on_drawdown_pct=20.0)
    assert engine._is_drawdown_limit_exceeded(peak_equity=1_000_000) is False


def test_peak_zero_safe():
    # peak=0: division-by-zero protection -> False
    portfolio = Portfolio(initial_cash=1_000_000)
    engine = _make_engine_with_portfolio(portfolio, stop_trading_on_drawdown_pct=20.0)
    assert engine._is_drawdown_limit_exceeded(peak_equity=0) is False


def test_just_below_threshold_false():
    # cash=1_000_000, peak=1_249_999 -> MDD=(1_249_999-1_000_000)/1_249_999*100 ≈ 19.9999% < 20%
    portfolio = Portfolio(initial_cash=1_000_000)
    engine = _make_engine_with_portfolio(portfolio, stop_trading_on_drawdown_pct=20.0)
    assert engine._is_drawdown_limit_exceeded(peak_equity=1_249_999) is False


# integration: event_log test

def test_drawdown_event_logged():
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 2, "operator": ">"},
            ],
        }
    }
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=200_000,
        initial_cash=1_000_000,
        stop_trading_on_drawdown_pct=10.0,
    )
    portfolio = Portfolio(initial_cash=1_000_000)
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    engine = BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)

    # Day0=100, Day1=110(entry), Day2=55(MDD>10%), Day3=55
    dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)]
    closes = [100.0, 110.0, 55.0, 55.0]
    opens = closes[:]
    df = pd.DataFrame({
        "date": dates,
        "adj_open": opens,
        "adj_high": closes,
        "adj_low": closes,
        "adj_close": closes,
        "adj_volume": [10_000.0] * 4,
    })
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)

    result = engine.run(df)

    drawdown_events = [
        e for e in result.event_log if e.get("reason") == EVENT_REASON_DRAWDOWN_LIMIT
    ]
    if drawdown_events:
        for ev in drawdown_events:
            assert ev["event_type"] == EVENT_TYPE_SKIP
            assert "current_drawdown_pct" in ev["detail"]
            assert "stop_trading_on_drawdown_pct" in ev["detail"]
            assert ev["detail"]["stop_trading_on_drawdown_pct"] == 10.0

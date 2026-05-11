"""step 065 - delisting_estimated 처리 테스트 (13-u).

정확성 정책 13.4.5: 정리매매 데이터 없는 경우 종가x0.5로 보수적 강제매도.

검증:
    A) 예정 폐지일 당일 보유 종목 강제매도 발동
    B) 체결가 = adj_close * 0.5 검증
    C) exit_reason = force_sell_delisting_estimated
    D) event_log 기록 (reason / detail.base_price / detail.exit_price / detail.discount_pct)
    E) delisting_dates (100%)와 delisting_estimated_dates (50%) 구분
    F) 시세 결손 시 position.current_price * 0.5 fallback
    G) 결정론: 동일 입력 5회 동일 결과
"""

from datetime import date

import pandas as pd
import pytest

import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import (
    EVENT_REASON_FORCE_SELL_DELISTED_ESTIMATED,
    EVENT_TYPE_FORCE_SELL,
    BacktestEngine,
)
from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

SYMBOL_A = "000001"
SYMBOL_B = "000002"


def _make_df(
    dates: list,
    closes: list,
    *,
    opens: list | None = None,
) -> pd.DataFrame:
    n = len(dates)
    if opens is None:
        opens = closes
    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": opens,
            "adj_high": closes,
            "adj_low": closes,
            "adj_close": closes,
            "adj_volume": [10_000.0] * n,
        }
    )
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def _make_engine_with_portfolio(
    strategy: dict | None = None,
    *,
    initial_cash: float = 1_000_000,
    position_size: float = 300_000,
    symbol: str = SYMBOL_A,
) -> tuple[BacktestEngine, Portfolio]:
    if strategy is None:
        strategy = {"entry": {"logic": "AND", "conditions": []}}
    config = BacktestConfig(
        symbol=symbol,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=position_size,
        initial_cash=initial_cash,
    )
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    engine = BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)
    return engine, portfolio


# ========================================================================
# A, B, C, D: 강제매도 발동 + 가격 50% + event_log
# ========================================================================


def test_delisting_estimated_event_recorded():
    """예정 폐지일에 event_log에 force_sell_delisting_estimated가 기록됨.

    포트폴리오에 직접 종목을 매수해두고 예정 폐지 강제매도를 테스트.
    """
    strategy = {"entry": {"logic": "AND", "conditions": []}}
    # Day0, Day1 시세만 있음 (Day1에 매수, Day2에 예정 폐지)
    dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    closes = [100.0, 100.0, 100.0]
    df = _make_df(dates, closes)

    engine, portfolio = _make_engine_with_portfolio(
        strategy, initial_cash=1_000_000, position_size=500_000
    )
    # portfolio에 직접 종목 매수 (전략 신호 없이)
    from app.backtest.execution import ExecutionModel as EM
    em = EM(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    execution = em.calculate_buy_cost(100.0, 100, raw_price=100.0)
    portfolio.buy(
        symbol=SYMBOL_A,
        price=100.0,
        quantity=100,
        on_date=date(2024, 1, 2),
        reason="manual",
        execution=execution,
    )

    result = engine.run(df, delisting_estimated_dates={SYMBOL_A: date(2024, 1, 4)})

    est_events = [
        e for e in result.event_log
        if e.get("reason") == EVENT_REASON_FORCE_SELL_DELISTED_ESTIMATED
    ]
    assert len(est_events) >= 1, "예정 폐지일에 force_sell 이벤트가 있어야 함"
    ev = est_events[0]
    assert ev["event_type"] == EVENT_TYPE_FORCE_SELL
    assert ev["symbol"] == SYMBOL_A
    assert ev["date"] == date(2024, 1, 4)


def test_delisting_estimated_price_is_half():
    """예정 폐지 강제매도 체결가 = adj_close * 0.5."""
    strategy = {"entry": {"logic": "AND", "conditions": []}}
    dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    closes = [100.0, 100.0, 200.0]  # Day2 종가 200원 -> 청산가 100원
    df = _make_df(dates, closes)

    engine, portfolio = _make_engine_with_portfolio(
        strategy, initial_cash=1_000_000, position_size=500_000
    )
    # 직접 매수
    from app.backtest.execution import ExecutionModel as EM
    em = EM(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    execution = em.calculate_buy_cost(100.0, 100, raw_price=100.0)
    portfolio.buy(
        symbol=SYMBOL_A,
        price=100.0,
        quantity=100,
        on_date=date(2024, 1, 2),
        reason="manual",
        execution=execution,
    )

    result = engine.run(df, delisting_estimated_dates={SYMBOL_A: date(2024, 1, 4)})

    est_events = [
        e for e in result.event_log
        if e.get("reason") == EVENT_REASON_FORCE_SELL_DELISTED_ESTIMATED
    ]
    assert len(est_events) >= 1
    ev = est_events[0]
    assert ev["detail"]["base_price"] == 200.0
    assert ev["detail"]["exit_price"] == 100.0
    assert ev["detail"]["discount_pct"] == 50


def test_delisting_estimated_different_symbol_no_event():
    """다른 종목(보유하지 않은)의 예정 폐지는 이벤트 없음."""
    strategy = {"entry": {"logic": "AND", "conditions": []}}
    # SYMBOL_A는 보유, SYMBOL_B는 예정 폐지 (미보유)
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    closes = [100.0, 100.0]
    df = _make_df(dates, closes)

    engine, _ = _make_engine_with_portfolio(strategy, symbol=SYMBOL_A)
    # SYMBOL_B 예정 폐지인데 SYMBOL_B는 보유하지 않음
    result = engine.run(df, delisting_estimated_dates={SYMBOL_B: date(2024, 1, 3)})

    est_events = [
        e for e in result.event_log
        if e.get("reason") == EVENT_REASON_FORCE_SELL_DELISTED_ESTIMATED
    ]
    assert len(est_events) == 0, "미보유 종목의 예정 폐지는 이벤트 없어야 함"


# ========================================================================
# E: delisting_dates vs delisting_estimated_dates 가격 차이
# ========================================================================


def test_actual_vs_estimated_price():
    """실 폐지(100%)와 예정 폐지(50%) 체결가 차이."""
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 2, "operator": ">"},
            ],
        }
    }
    dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    closes = [100.0, 110.0, 200.0]

    def _run(kind: str):
        df = _make_df(dates, closes)
        eng, _ = _make_engine_with_portfolio(strategy, initial_cash=1_000_000, position_size=500_000)
        if kind == "actual":
            return eng.run(df, delisting_dates={SYMBOL_A: date(2024, 1, 4)})
        return eng.run(df, delisting_estimated_dates={SYMBOL_A: date(2024, 1, 4)})

    r_actual = _run("actual")
    r_estimated = _run("estimated")

    actual_sells = [t for t in r_actual.trade_executions if t.get("action") == "sell"]
    est_sells = [t for t in r_estimated.trade_executions if t.get("action") == "sell"]

    if actual_sells and est_sells:
        actual_price = actual_sells[-1].get("price", 0)
        est_price = est_sells[-1].get("price", 0)
        assert actual_price > est_price, "실 폐지 체결가 > 예정 폐지 체결가"
        assert actual_price == pytest.approx(est_price * 2, rel=0.1)


# ========================================================================
# F: 시세 결손 fallback
# ========================================================================


def test_delisting_estimated_fallback_no_row():
    """Day2 시세 결손 시 current_price * 0.5로 fallback."""
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 2, "operator": ">"},
            ],
        }
    }
    # SYMBOL_A: 2봉만 존재 (Day0, Day1)
    dates_a = [date(2024, 1, 2), date(2024, 1, 3)]
    closes_a = [1000.0, 1100.0]
    df_a = _make_df(dates_a, closes_a)

    # SYMBOL_B: 더미 3봉 (active universe 유지용)
    dates_b = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    closes_b = [1000.0, 1000.0, 1000.0]
    df_b = _make_df(dates_b, closes_b)

    engine, _ = _make_engine_with_portfolio(
        strategy, initial_cash=1_000_000, position_size=300_000, symbol=SYMBOL_A
    )
    result = engine.run(
        {SYMBOL_A: df_a, SYMBOL_B: df_b},
        delisting_estimated_dates={SYMBOL_A: date(2024, 1, 4)},
    )

    est_events = [
        e for e in result.event_log
        if e.get("reason") == EVENT_REASON_FORCE_SELL_DELISTED_ESTIMATED
    ]
    if est_events:
        ev = est_events[0]
        assert ev["detail"]["row_present"] is False
        assert ev["detail"]["exit_price"] == ev["detail"]["base_price"] * 0.5


# ========================================================================
# G: 결정론
# ========================================================================


def test_delisting_estimated_determinism():
    """5회 반복 동일 결과."""
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 2, "operator": ">"},
            ],
        }
    }
    dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    closes = [100.0, 110.0, 100.0]

    all_results = []
    for _ in range(5):
        df = _make_df(dates, closes)
        engine, _ = _make_engine_with_portfolio(
            strategy, initial_cash=1_000_000, position_size=500_000
        )
        r = engine.run(df, delisting_estimated_dates={SYMBOL_A: date(2024, 1, 4)})
        sells = [(t.get("price"), t.get("quantity")) for t in r.trade_executions if t.get("action") == "sell"]
        all_results.append(sells)

    for r in all_results:
        assert r == all_results[0], "결정론 실패"

"""trade_group별 익절/손절 평가 시나리오 테스트 (05-l + 04-p).

정확성 정책 13.3 (일중 익절/손절) + 05-l (trade_group별 entry_price 기준):
    - take_profit / stop_loss는 각 trade_group의 entry_price 기준으로 독립 평가.
    - max_holding_days는 trade_group의 entry_date 기준.
    - trailing_stop은 Position.peak_price(공유)로 position 전체 청산.

검증 매핑 (정확성 정책 13.17):
    - 13.3.1 / 13.3.2: 동일 봉 stop+take 동시 도달 시 손절 우선 (보수적)
    - 13.3.5: trailing_stop의 peak_price는 전일까지의 high (공유)
    - 13.9.3: 부분 매도 시 entry_price 불변
    - 05-l: trade_group별 entry_price 기준 익절/손절

테스트 구조:
    - Portfolio에 trade_group을 직접 주입 (분할 매수 시나리오)
    - BacktestEngine._evaluate_exit_position_per_tg를 직접 호출
    - 결과를 trade_logs로 검증 (어떤 trade_group이 청산됐는지, 수량)
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import app.strategy  # noqa: F401 — 조건 자동 등록
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.backtest.result import BacktestResult
from app.portfolio.portfolio import Portfolio
from app.portfolio.position import Position, TradeGroup
from app.strategy.engine import StrategyEngine

SYMBOL = "005930"


# ============================================================================
# 헬퍼
# ============================================================================


def _make_engine_and_portfolio(
    strategy: dict,
    *,
    initial_cash: float = 10_000_000,
) -> tuple[BacktestEngine, Portfolio]:
    """BacktestEngine + Portfolio 쌍 생성. 수수료/세금/슬리피지 0 (단순화)."""
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
        tick_rounding="nearest",
    )
    config = BacktestConfig(
        symbol=SYMBOL,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=1_000_000,
        initial_cash=initial_cash,
    )
    engine = BacktestEngine(
        StrategyEngine(strategy),
        portfolio,
        execution_model,
        config,
    )
    return engine, portfolio


def _inject_two_trade_groups(
    portfolio: Portfolio,
    *,
    tg1_entry_price: float,
    tg1_entry_qty: int,
    tg1_entry_date: date,
    tg2_entry_price: float,
    tg2_entry_qty: int,
    tg2_entry_date: date,
    peak_price: float | None = None,
) -> None:
    """Portfolio에 분할 매수 상태(2개 trade_group)를 직접 주입.

    BacktestEngine._maybe_buy 경로를 우회해 분할 매수 시나리오를 구성한다.
    cash는 차감 없이 positions만 직접 생성 (단위 테스트 목적).
    """
    tg1 = TradeGroup(
        trade_group_id=1,
        entry_date=tg1_entry_date,
        entry_price=tg1_entry_price,
        entry_quantity=tg1_entry_qty,
        remaining_quantity=tg1_entry_qty,
    )
    tg2 = TradeGroup(
        trade_group_id=2,
        entry_date=tg2_entry_date,
        entry_price=tg2_entry_price,
        entry_quantity=tg2_entry_qty,
        remaining_quantity=tg2_entry_qty,
    )
    initial_peak = peak_price if peak_price is not None else max(tg1_entry_price, tg2_entry_price)
    portfolio.positions[SYMBOL] = Position(
        symbol=SYMBOL,
        name="테스트종목",
        current_price=tg2_entry_price,
        peak_price=initial_peak,
        trade_groups=[tg1, tg2],
    )
    # portfolio._next_trade_group_id를 올바른 값으로 설정
    portfolio._next_trade_group_id = 3


def _make_row(
    *,
    adj_open: float,
    adj_high: float,
    adj_low: float,
    adj_close: float,
    today: date,
) -> pd.Series:
    """단일 봉 Series 생성 (exit_position 평가용)."""
    return pd.Series(
        {
            "date": today,
            "adj_open": adj_open,
            "adj_high": adj_high,
            "adj_low": adj_low,
            "adj_close": adj_close,
            "adj_volume": 10_000.0,
        }
    )


def _minimal_strategy(*, take_profit_pct: float | None = None, stop_loss_pct: float | None = None, trailing_stop_pct: float | None = None, max_holding: int | None = None) -> dict:
    """exit_position만 있는 최소 전략 JSON."""
    conditions = []
    if take_profit_pct is not None:
        conditions.append({"type": "take_profit", "percent": take_profit_pct, "trigger": "intraday_high"})
    if stop_loss_pct is not None:
        conditions.append({"type": "stop_loss", "percent": stop_loss_pct, "trigger": "intraday_low"})
    if trailing_stop_pct is not None:
        conditions.append({"type": "trailing_stop", "percent": trailing_stop_pct, "trigger": "intraday_low"})
    if max_holding is not None:
        conditions.append({"type": "max_holding_days", "days": max_holding})
    return {
        "entry": {"logic": "AND", "conditions": []},
        "exit_position": {"logic": "OR", "conditions": conditions},
    }


# ============================================================================
# test_take_profit_per_trade_group (05-l)
# ============================================================================


def test_take_profit_per_trade_group():
    """분할 매수 2회. 첫 매수(100원) 익절 20%, 두 번째 매수(120원) 미달.

    조건: take_profit 20%
        tg1 entry_price=100 → target_price=120.0
        tg2 entry_price=120 → target_price=144.0

    당일 시가=119 (갭 업 익절선 미달), high=130 (adj_high):
        갭 분기: tg1 open=119 < target=120 → 갭 업 익절 아님
                 tg2 open=119 < target=144 → 갭 업 익절 아님
        일중 분기 (take_profit):
            tg1: high=130 >= target=120.0 → 익절 (take_profit)
            tg2: high=130 < target=144.0 → 미달 (유지)

    기대: tg1만 청산, tg2는 남음.
    정확성 정책 13.3 + 05-l.
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(take_profit_pct=20.0)
    )

    today = date(2024, 3, 15)
    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=date(2024, 3, 1),
        tg2_entry_price=120.0,
        tg2_entry_qty=5,
        tg2_entry_date=date(2024, 3, 8),
        peak_price=130.0,
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=119.0,   # 갭 분기 미달: tg1 target=120 > 119 → 갭 업 아님
        adj_high=130.0,   # 일중: tg1 target=120 도달 / tg2 target=144 미달
        adj_low=118.0,
        adj_close=125.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    sold_all = engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    # 전량 청산 아님 (tg2 유지)
    assert sold_all == False  # noqa: E712

    # tg1 청산됨 → positions에 SYMBOL이 남아있고, tg2만 잔존
    assert SYMBOL in portfolio.positions
    remaining_tgs = portfolio.positions[SYMBOL].trade_groups
    assert len(remaining_tgs) == 1, f"tg2만 남아야 하는데 {len(remaining_tgs)}개"
    assert remaining_tgs[0].trade_group_id == 2, "tg2(ID=2)가 남아있어야 함"
    assert remaining_tgs[0].remaining_quantity == 5

    # 매도 로그 확인
    sell_logs = [log for log in portfolio.trade_logs if log.get("side") == "sell"]
    assert len(sell_logs) == 1
    sell = sell_logs[0]
    assert sell["trade_group_id"] == 1
    assert sell["quantity"] == 10
    assert sell["reason"] == "take_profit"
    # 체결가 = entry_price * (1 + 20/100) = 100 * 1.2 = 120.0
    assert sell["price"] == pytest.approx(120.0, abs=0.01)


# ============================================================================
# test_stop_loss_per_trade_group (05-l + 13.3.2)
# ============================================================================


def test_stop_loss_per_trade_group():
    """분할 매수 2회. 첫 매수(100원), 두 번째 매수(80원). 손절 조건 15%.

    tg1 entry_price=100 → stop_price=85.0
    tg2 entry_price=80  → stop_price=68.0

    갭 분기:
        adj_open=78: tg1 open=78 <= stop=85 → 갭 다운 손절 (gap_down_stop_loss)
                     tg2 open=78 > stop=68  → 갭 다운 아님
    일중 분기 (tg2만 남음):
        adj_low=60: tg2 low=60 <= stop=68 → 손절 (stop_loss)

    결과: 두 tg 모두 청산 → sold_all=True.
    05-l 검증: tg1은 갭 다운 시가 체결, tg2는 손절선(68.0) 체결.
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(stop_loss_pct=15.0)
    )

    today = date(2024, 3, 15)
    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=date(2024, 3, 1),
        tg2_entry_price=80.0,
        tg2_entry_qty=5,
        tg2_entry_date=date(2024, 3, 8),
        peak_price=105.0,
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=78.0,   # tg1 갭 다운 (78 <= 85), tg2 갭 아님 (78 > 68)
        adj_high=79.0,
        adj_low=60.0,    # tg2 일중 손절선 68.0 하회 (60 <= 68)
        adj_close=65.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    sold_all = engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    # 두 tg 모두 손절 → 전량 청산
    assert sold_all == True  # noqa: E712
    assert SYMBOL not in portfolio.positions

    sell_logs = [log for log in portfolio.trade_logs if log.get("side") == "sell"]
    assert len(sell_logs) == 2

    # tg1: gap_down_stop_loss (open=78 < stop=85)
    tg1_log = next(log for log in sell_logs if log["trade_group_id"] == 1)
    assert tg1_log["reason"] == "gap_down_stop_loss"
    assert tg1_log["quantity"] == 10
    # 갭 다운 체결가 = adj_open = 78.0
    assert tg1_log["price"] == pytest.approx(78.0, abs=0.01)

    # tg2: 갭 분기 통과 (78 > 68), 일중 손절 (low=60 <= stop=68)
    tg2_log = next(log for log in sell_logs if log["trade_group_id"] == 2)
    assert tg2_log["reason"] == "stop_loss"
    assert tg2_log["quantity"] == 5
    # tg2 체결가 = 80 * (1 - 0.15) = 68.0
    assert tg2_log["price"] == pytest.approx(68.0, abs=0.01)


def test_stop_loss_only_second_trade_group():
    """분할 매수 2회. 첫 매수(100원)는 손절선(85원) 미달, 두 번째 매수(80원)만 손절 조건 15%.

    tg1 entry_price=100 → stop_price=85.0
    tg2 entry_price=80  → stop_price=68.0

    당일 시가=90, 저가=72:
        갭 분기: tg1 open=90 > stop=85 → 갭 다운 손절 아님
                  tg2 open=90 > stop=68 → 갭 다운 손절 아님
        일중 분기: tg1 low=72 > stop=85? 아니오, 72 < 85 → tg1도 손절
                   tg2 low=72 >= stop=68? 72 > 68 → 아니오 (72 > 68 → 손절 아님)

    NOTE: 저가=72는 tg1 손절선(85)보다 아래이므로 tg1도 손절됩니다.
    올바른 시나리오를 위해 저가=87 (tg1 미달, tg2 68 미달):
        tg1 low=87 > stop=85 → 미달 (유지)
        tg2 low=87 > stop=68 → 미달 (유지)

    실제로 tg2만 손절되는 시나리오:
        tg1 stop_price=85, tg2 stop_price=68
        low=75: tg1 손절 (75 <= 85), tg2 손절 아님 (75 > 68)
        즉 low=75가 되면 tg1은 손절되고 tg2(stop=68)는 유지.
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(stop_loss_pct=15.0)
    )

    today = date(2024, 3, 15)
    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=date(2024, 3, 1),
        tg2_entry_price=80.0,
        tg2_entry_qty=5,
        tg2_entry_date=date(2024, 3, 8),
        peak_price=105.0,
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=95.0,   # 갭 다운 없음 (tg1 stop=85, 95>85; tg2 stop=68, 95>68)
        adj_high=97.0,
        adj_low=75.0,    # tg1: 75 <= 85 → 손절 / tg2: 75 > 68 → 유지
        adj_close=82.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    sold_all = engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    # tg1만 손절 → tg2 유지 → sold_all=False
    assert sold_all == False  # noqa: E712
    assert SYMBOL in portfolio.positions
    remaining_tgs = portfolio.positions[SYMBOL].trade_groups
    assert len(remaining_tgs) == 1
    assert remaining_tgs[0].trade_group_id == 2

    sell_logs = [log for log in portfolio.trade_logs if log.get("side") == "sell"]
    assert len(sell_logs) == 1
    sell = sell_logs[0]
    assert sell["trade_group_id"] == 1
    assert sell["reason"] == "stop_loss"
    # tg1 체결가 = 100 * (1 - 0.15) = 85.0
    assert sell["price"] == pytest.approx(85.0, abs=0.01)


# ============================================================================
# test_trailing_stop_uses_position_peak (04-p + 13.3.5)
# ============================================================================


def test_trailing_stop_uses_position_peak():
    """trailing_stop은 Position.peak_price(공유) 기준. 2개 trade_group 모두 동일 peak.

    정확성 정책 13.3.5: trailing_stop의 peak는 "전일까지의 high" (공유).
    05-l: trailing_stop은 position 단위 평가 → 전체 청산.

    설정:
        peak_price = 150.0
        trailing_stop percent = 10%
        손절선 = 150 * 0.9 = 135.0

    tg1 entry_price=100, tg2 entry_price=120
    당일 low=130 (135.0보다 아래) → trailing_stop 트리거

    기대: position 전체 청산 (sold_all=True), 체결가 = peak * (1 - 10/100) = 135.0
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(trailing_stop_pct=10.0)
    )

    today = date(2024, 3, 15)
    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=date(2024, 3, 1),
        tg2_entry_price=120.0,
        tg2_entry_qty=5,
        tg2_entry_date=date(2024, 3, 8),
        peak_price=150.0,  # 두 tg가 공유하는 peak
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=140.0,  # 갭 분기: trailing_stop은 갭 분기 없음 (stop_rule/take_rule 없음)
        adj_high=142.0,
        adj_low=130.0,   # 손절선 135.0 하회 → trailing_stop 트리거
        adj_close=132.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    sold_all = engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    # position 전체 청산
    assert sold_all == True  # noqa: E712
    assert SYMBOL not in portfolio.positions

    sell_logs = [log for log in portfolio.trade_logs if log.get("side") == "sell"]
    # FIFO (sell_symbol_fifo)가 호출되므로 2개 로그 (tg1, tg2)
    total_qty = sum(log["quantity"] for log in sell_logs)
    assert total_qty == 15  # tg1 10 + tg2 5

    # 체결가는 peak * (1 - 10/100) = 135.0 (슬리피지 0)
    for log in sell_logs:
        assert log["price"] == pytest.approx(135.0, abs=0.01)
        assert log["reason"] == "trailing_stop"


def test_trailing_stop_not_triggered_below_peak():
    """trailing_stop이 미달이면 트리거 안 됨.

    peak=150, trailing=10% → 손절선=135.0
    low=136 (> 135.0) → trailing_stop 미달

    기대: sold_all=False, 포지션 유지.
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(trailing_stop_pct=10.0)
    )

    today = date(2024, 3, 15)
    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=date(2024, 3, 1),
        tg2_entry_price=120.0,
        tg2_entry_qty=5,
        tg2_entry_date=date(2024, 3, 8),
        peak_price=150.0,
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=140.0,
        adj_high=142.0,
        adj_low=136.0,   # 손절선 135.0 상회 → 미달
        adj_close=138.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    sold_all = engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    assert sold_all == False  # noqa: E712
    assert SYMBOL in portfolio.positions
    assert len(portfolio.positions[SYMBOL].trade_groups) == 2
    assert not portfolio.trade_logs  # 매도 없음


# ============================================================================
# test_max_holding_days_per_trade_group (05-l)
# ============================================================================


def test_max_holding_days_per_trade_group():
    """첫 매수는 15일 전, 두 번째 매수는 5일 전. max_holding_days=10일.

    tg1 entry_date = today - 15일 → holding_days=15 >= 10 → 청산
    tg2 entry_date = today - 5일  → holding_days=5 < 10  → 유지

    기대: tg1만 청산, tg2 유지.
    05-l: max_holding_days는 각 trade_group의 entry_date 기준.
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(max_holding=10)
    )

    today = date(2024, 3, 20)
    tg1_entry_date = date(2024, 3, 5)   # 15일 전
    tg2_entry_date = date(2024, 3, 15)  # 5일 전

    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=tg1_entry_date,
        tg2_entry_price=110.0,
        tg2_entry_qty=8,
        tg2_entry_date=tg2_entry_date,
        peak_price=115.0,
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=112.0,
        adj_high=113.0,
        adj_low=110.0,
        adj_close=111.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    sold_all = engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    # tg1만 청산 → sold_all=False
    assert sold_all == False  # noqa: E712
    assert SYMBOL in portfolio.positions

    remaining = portfolio.positions[SYMBOL].trade_groups
    assert len(remaining) == 1
    assert remaining[0].trade_group_id == 2
    assert remaining[0].remaining_quantity == 8

    sell_logs = [log for log in portfolio.trade_logs if log.get("side") == "sell"]
    assert len(sell_logs) == 1
    sell = sell_logs[0]
    assert sell["trade_group_id"] == 1
    assert sell["reason"] == "max_holding_days"
    assert sell["quantity"] == 10
    # 체결가 = adj_close = 111.0
    assert sell["price"] == pytest.approx(111.0, abs=0.01)


def test_max_holding_days_both_groups():
    """두 trade_group 모두 max_holding_days 초과 → 전량 청산.

    tg1: 20일 전, tg2: 12일 전. max_holding_days=10.
    둘 다 >= 10일 → 전량 청산.
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(max_holding=10)
    )

    today = date(2024, 3, 20)
    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=date(2024, 2, 29),  # 20일 전
        tg2_entry_price=110.0,
        tg2_entry_qty=8,
        tg2_entry_date=date(2024, 3, 8),   # 12일 전
        peak_price=115.0,
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=112.0,
        adj_high=113.0,
        adj_low=111.0,
        adj_close=112.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    sold_all = engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    assert sold_all == True  # noqa: E712
    assert SYMBOL not in portfolio.positions

    sell_logs = [log for log in portfolio.trade_logs if log.get("side") == "sell"]
    assert len(sell_logs) == 2
    assert all(log["reason"] == "max_holding_days" for log in sell_logs)
    total_qty = sum(log["quantity"] for log in sell_logs)
    assert total_qty == 18  # 10 + 8


# ============================================================================
# 동일 봉 손절/익절 동시 도달 → 손절 우선 (13.3.2)
# ============================================================================


def test_stop_before_take_profit_same_candle():
    """동일 봉 stop_loss + take_profit 동시 도달 시 손절 우선 (13.3.2).

    tg1 entry_price=100:
        stop_price = 100 * 0.97 = 97.0  (stop_loss 3%)
        target_price = 100 * 1.07 = 107.0  (take_profit 7%)

    당일 low=95 (<=97), high=110 (>=107) → 두 조건 모두 도달.
    우선순위: stop_loss(1) < take_profit(2) → stop_loss 먼저 처리.

    기대: reason="stop_loss", price≈97.0
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(stop_loss_pct=3.0, take_profit_pct=7.0)
    )

    today = date(2024, 3, 15)
    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=date(2024, 3, 1),
        tg2_entry_price=100.0,
        tg2_entry_qty=5,
        tg2_entry_date=date(2024, 3, 8),
        peak_price=110.0,
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=101.0,  # 갭: open=101 > stop=97 → 갭 다운 아님, open=101 < take=107 → 갭 업 아님
        adj_high=110.0,  # take_profit 도달 (>=107.0)
        adj_low=95.0,    # stop_loss 도달 (<=97.0)
        adj_close=100.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    sold_all = engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    # 두 tg 모두 stop_loss에 해당 → 전량 청산
    assert sold_all == True  # noqa: E712
    sell_logs = [log for log in portfolio.trade_logs if log.get("side") == "sell"]
    # 두 tg 모두 stop_loss reason이어야 함 (take_profit이 먼저 처리되면 안 됨)
    for log in sell_logs:
        assert log["reason"] == "stop_loss", (
            f"reason={log['reason']!r}. 손절 우선 정책(13.3.2) 위반"
        )


# ============================================================================
# 갭 분기에서 trade_group별 독립 판정
# ============================================================================


def test_gap_down_only_first_trade_group():
    """갭 다운이 tg1만 손절선 하회, tg2는 유지.

    tg1 entry_price=100, stop=15% → stop_price=85.0
    tg2 entry_price=80, stop=15% → stop_price=68.0

    adj_open=80 → tg1: 80 <= 85 → 갭 다운 손절 / tg2: 80 > 68 → 갭 다운 아님

    기대: tg1만 시가 체결, tg2 유지.
    """
    engine, portfolio = _make_engine_and_portfolio(
        _minimal_strategy(stop_loss_pct=15.0)
    )

    today = date(2024, 3, 15)
    _inject_two_trade_groups(
        portfolio,
        tg1_entry_price=100.0,
        tg1_entry_qty=10,
        tg1_entry_date=date(2024, 3, 1),
        tg2_entry_price=80.0,
        tg2_entry_qty=5,
        tg2_entry_date=date(2024, 3, 8),
        peak_price=105.0,
    )

    rules = engine._get_exit_position_rules()
    row = _make_row(
        adj_open=80.0,   # tg1 갭 다운 (80 <= 85), tg2 갭 아님 (80 > 68)
        adj_high=81.0,
        adj_low=70.0,    # tg2 일중 손절선 68 > 70 → 손절 트리거
        adj_close=75.0,
        today=today,
    )

    result = BacktestResult(initial_cash=portfolio.initial_cash)
    engine._evaluate_exit_position_per_tg(
        symbol=SYMBOL,
        row=row,
        rules=rules,
        today=today,
        result=result,
    )

    sell_logs = [log for log in portfolio.trade_logs if log.get("side") == "sell"]
    # tg1 갭 다운 손절 + tg2 일중 손절 (둘 다 손절)
    tg1_log = next((log for log in sell_logs if log["trade_group_id"] == 1), None)
    assert tg1_log is not None
    assert tg1_log["reason"] == "gap_down_stop_loss"
    # 갭 다운 체결가 = adj_open = 80.0
    assert tg1_log["price"] == pytest.approx(80.0, abs=0.01)

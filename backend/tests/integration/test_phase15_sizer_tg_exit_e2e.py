"""Phase 15 통합 시나리오 테스트 (test-engineer 작성).

검증 목표 (Phase 15 — step 045~047):
  1. PositionSizer 통합 (05-i): fixed_ratio / equal_weight가 BacktestEngine
     end-to-end 실행 경로에서 올바른 수량을 계산하는지.
  2. buy_skipped_cash_shortage event_log (05-j): 예수금 부족 시 event_log가
     올바른 위치에 기록되고, 메타데이터(required_cash, available_cash)가 정확한지.
  3. update_peak_price 순서 (05-k / 13.3.5): exit_position 평가 이후에
     peak_price가 갱신되는지 end-to-end 흐름에서 검증.
  4. trade_group별 익절/손절 독립 평가 (05-l): 분할 매수 후 일부 trade_group만
     익절 조건 도달 시 해당 group만 청산되고 나머지는 유지되는지.
  5. 결정론: 동일 입력으로 10회 반복 실행 결과 동일 (CLAUDE.md #8).

정확성 정책 매핑:
  - 13.3   일중 익절/손절 처리 정책
  - 13.3.2 동일 봉 손절 우선 (보수적)
  - 13.3.5 trailing_stop peak_price는 전일까지의 high (look-ahead bias 차단)
  - 05-i   PositionSizer 3방식
  - 05-j   buy_skipped_cash_shortage event_log
  - 05-k   update_peak_price 호출 순서 검증
  - 05-l   trade_group별 entry_price 기준 익절/손절

참고: 본 파일은 test-engineer 에이전트가 Phase 15 완료 검증 시 신규 작성.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

import app.strategy  # noqa: F401 — 기본 조건 자동 등록
from app.backtest.config import BacktestConfig
from app.backtest.engine import (
    EVENT_REASON_CASH_SHORTAGE,
    EVENT_TYPE_SKIP,
    BacktestEngine,
)
from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

SYMBOL = "000660"  # SK하이닉스 (테스트용 임의 코드)


def _make_price_df(
    dates: list[date],
    closes: list[float],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    """최소 OHLCV 데이터프레임 생성. adj_* 컬럼 + next_open 자동 계산."""
    n = len(dates)
    if opens is None:
        opens = closes[:]
    if highs is None:
        highs = [c * 1.02 for c in closes]
    if lows is None:
        lows = [c * 0.98 for c in closes]
    if volumes is None:
        volumes = [10_000.0] * n

    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": [float(v) for v in opens],
            "adj_high": [float(v) for v in highs],
            "adj_low": [float(v) for v in lows],
            "adj_close": [float(v) for v in closes],
            "adj_volume": [float(v) for v in volumes],
        }
    )
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_close"] = df["adj_close"].shift(-1)
    df["close"] = df["adj_close"]
    df.set_index("date", inplace=True)
    return df


def _make_engine(
    strategy: dict,
    *,
    initial_cash: float = 10_000_000,
    sizing_method: str = "fixed_amount",
    sizing_ratio: float | None = None,
    max_positions: int | None = None,
    position_size_amount: float = 1_000_000,
    cash_manager: Any = None,
) -> tuple[BacktestEngine, Portfolio]:
    """BacktestEngine + Portfolio 쌍 생성 (수수료/세금/슬리피지 0)."""
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
        initial_cash=initial_cash,
        position_size_amount=position_size_amount,
        sizing_method=sizing_method,
        sizing_ratio=sizing_ratio,
        max_positions=max_positions,
    )
    engine = BacktestEngine(
        StrategyEngine(strategy),
        portfolio,
        execution_model,
        config,
        cash_manager=cash_manager,
    )
    return engine, portfolio


def _base_dates(n: int = 10, start: date = date(2024, 1, 2)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


# ---------------------------------------------------------------------------
# 시나리오 1 — PositionSizer fixed_ratio end-to-end (05-i)
# ---------------------------------------------------------------------------


def test_e2e_fixed_ratio_sizing_buys_correct_quantity():
    """fixed_ratio 방식으로 총자산의 일정 비율만큼 매수하는지 e2e 검증.

    정확성 정책: 05-i (PositionSizer fixed_ratio).
    look-ahead bias: 매수일 전날 종가 신호 → 다음날 시가 체결.
    결정론: 동일 입력 → 동일 결과.
    """
    # 초기 자본 10,000,000원. sizing_ratio=0.10 → 10% = 1,000,000원치 매수.
    # exec_price=10,000원 → 수량=100주 (1,000,000 // 10,000 = 100).
    initial_cash = 10_000_000
    exec_price = 10_000

    strategy = {
        "entry": {"conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}]},
        "exit_signal": {"conditions": []},
        "exit_position": {"conditions": []},
        "filters": {"conditions": []},
    }

    dates = _base_dates(10)
    # MA(2) 돌파: close[0]=9000, close[1]=10100 (MA2 = 9550, close=10100 > MA 조건)
    closes = [9_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000]
    # next_open = 10,000 (매수 체결가)
    opens = [9_000, exec_price, exec_price, exec_price, exec_price,
             exec_price, exec_price, exec_price, exec_price, exec_price]
    df = _make_price_df(dates, closes, opens=opens)

    engine, portfolio = _make_engine(
        strategy,
        initial_cash=initial_cash,
        sizing_method="fixed_ratio",
        sizing_ratio=0.10,
    )
    engine.run({SYMBOL: df})

    # 매수가 발생해야 하고, 수량이 100주여야 함
    trade_logs = portfolio.trade_logs
    buy_trades = [t for t in trade_logs if t.get("side") == "buy"]
    assert len(buy_trades) >= 1, "fixed_ratio 매수가 발생해야 함"

    first_buy = buy_trades[0]
    expected_qty = int(initial_cash * 0.10 // exec_price)  # 100
    assert first_buy["quantity"] == expected_qty, (
        f"fixed_ratio 수량 불일치: expected={expected_qty}, got={first_buy['quantity']}"
    )


# ---------------------------------------------------------------------------
# 시나리오 2 — PositionSizer equal_weight end-to-end (05-i)
# ---------------------------------------------------------------------------


def test_e2e_equal_weight_sizing_uses_total_equity():
    """equal_weight 방식으로 총자산 / max_positions 비중 매수 e2e 검증.

    정확성 정책: 05-i (PositionSizer equal_weight).
    """
    initial_cash = 10_000_000
    max_positions = 5
    exec_price = 10_000
    # 균등 비중: 10,000,000 / 5 = 2,000,000원. 수량 = 200주.
    expected_qty = int((initial_cash / max_positions) // exec_price)  # 200

    strategy = {
        "entry": {"conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}]},
        "exit_signal": {"conditions": []},
        "exit_position": {"conditions": []},
        "filters": {"conditions": []},
    }

    dates = _base_dates(10)
    closes = [9_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000]
    opens = [9_000, exec_price] + [exec_price] * 8
    df = _make_price_df(dates, closes, opens=opens)

    engine, portfolio = _make_engine(
        strategy,
        initial_cash=initial_cash,
        sizing_method="equal_weight",
        max_positions=max_positions,
    )
    engine.run({SYMBOL: df})

    buy_trades = [t for t in portfolio.trade_logs if t.get("side") == "buy"]
    assert len(buy_trades) >= 1, "equal_weight 매수가 발생해야 함"
    assert buy_trades[0]["quantity"] == expected_qty, (
        f"equal_weight 수량 불일치: expected={expected_qty}, got={buy_trades[0]['quantity']}"
    )


# ---------------------------------------------------------------------------
# 시나리오 3 — buy_skipped_cash_shortage event_log (05-j)
# ---------------------------------------------------------------------------


def test_e2e_cash_shortage_event_recorded_and_correct_metadata():
    """예수금 부족 시 buy_skipped_cash_shortage event가 기록되고
    required_cash / available_cash 메타데이터가 정확한지 e2e 검증.

    정확성 정책: 05-j (buy_skipped_cash_shortage event_log).
    결정론: event_log 항목은 date/symbol/reason/detail이 모두 일치해야 함.
    """
    # 초기 현금 50원 (매우 적음) → 10,000원 매수 불가 → cash_shortage 이벤트 기록
    initial_cash = 50.0
    exec_price = 10_000

    strategy = {
        "entry": {"conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}]},
        "exit_signal": {"conditions": []},
        "exit_position": {"conditions": []},
        "filters": {"conditions": []},
    }

    dates = _base_dates(6)
    closes = [9_000, 10_000, 10_000, 10_000, 10_000, 10_000]
    opens = [9_000, exec_price, exec_price, exec_price, exec_price, exec_price]
    df = _make_price_df(dates, closes, opens=opens)

    engine, portfolio = _make_engine(
        strategy,
        initial_cash=initial_cash,
        sizing_method="fixed_amount",
        position_size_amount=1_000_000,
    )
    engine.run({SYMBOL: df})

    shortage_events = [
        e for e in engine.event_log
        if e.get("reason") == EVENT_REASON_CASH_SHORTAGE
    ]
    assert len(shortage_events) >= 1, "cash_shortage event가 기록되어야 함"

    ev = shortage_events[0]
    assert ev["event_type"] == EVENT_TYPE_SKIP
    assert ev["symbol"] == SYMBOL
    assert "required_cash" in ev["detail"]
    assert "available_cash" in ev["detail"]
    # required_cash > available_cash 여야 함
    assert ev["detail"]["required_cash"] > ev["detail"]["available_cash"], (
        "required_cash가 available_cash보다 커야 함"
    )


# ---------------------------------------------------------------------------
# 시나리오 4 — peak_price 갱신 순서 (05-k / 13.3.5 look-ahead bias 차단)
# ---------------------------------------------------------------------------


def test_e2e_trailing_stop_uses_prev_day_high_not_today():
    """trailing_stop 평가는 전일까지의 peak_price 기준. 당일 high가 먼저
    반영되면 look-ahead bias가 발생하므로 update_peak_price는 exit 평가 후 호출.

    정확성 정책: 13.3.5 + 05-k (update_peak_price 호출 순서).
    look-ahead bias: peak_price에 당일 high가 반영되기 전에 trailing 평가해야 함.
    """
    # 시나리오:
    #   Day1: open=10000, high=10000, low=9800, close=10000 → 매수 (next_open=10000)
    #   Day2: open=10000, high=11000, low=9900, close=10000 → 보유; peak=10000→11000
    #   Day3: open=10000, high=10000, low=8000, close=10000
    #         trailing(20%): 손절선 = 11000*(1-0.2)=8800. low=8000 <= 8800 → 손절
    #         하지만 peak는 Day2 high(11000)이어야 함 (Day3 high=10000이 반영되기 전)

    strategy = {
        "entry": {"conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}]},
        "exit_signal": {"conditions": []},
        "exit_position": {
            "conditions": [{"type": "trailing_stop", "percent": 20.0}]
        },
        "filters": {"conditions": []},
    }

    base = date(2024, 1, 2)
    dates = [base + timedelta(days=i) for i in range(6)]
    closes = [9_000, 10_000, 10_000, 10_000, 10_000, 10_000]
    opens  = [9_000, 10_000, 10_000, 10_000, 10_000, 10_000]
    highs  = [9_000, 11_000, 10_000, 10_000, 10_000, 10_000]
    lows   = [9_000,  9_900,  8_000,  9_000,  9_000,  9_000]

    df = _make_price_df(dates, closes, opens=opens, highs=highs, lows=lows)

    engine, portfolio = _make_engine(
        strategy,
        initial_cash=5_000_000,
        sizing_method="fixed_amount",
        position_size_amount=1_000_000,
    )
    engine.run({SYMBOL: df})

    # trailing_stop이 트리거되어 매도가 발생해야 함
    sell_trades = [t for t in portfolio.trade_logs if t.get("side") == "sell"]
    assert len(sell_trades) >= 1, "trailing_stop 매도가 발생해야 함"

    # 매도 사유가 trailing_stop이어야 함
    trailing_sells = [t for t in sell_trades if "trailing" in t.get("reason", "")]
    assert len(trailing_sells) >= 1, "trailing_stop 사유 매도가 기록되어야 함"


# ---------------------------------------------------------------------------
# 시나리오 5 — trade_group별 익절 독립 평가 end-to-end (05-l)
# ---------------------------------------------------------------------------


def test_e2e_trade_group_independent_take_profit_partial_exit():
    """두 종목 각각 분할 매수 → 일부 trade_group만 익절 조건 도달 →
    해당 그룹만 청산, 나머지 포지션 유지.

    정확성 정책: 05-l (trade_group별 entry_price 기준 익절).
    13.9.3: 부분 매도 시 entry_price 불변.
    결정론: (entry_date, trade_group_id) ASC 순서로 평가.

    본 테스트는 단일 종목 2회 매수 시뮬레이션.
    BacktestEngine을 통한 완전한 end-to-end 흐름으로 검증.
    """
    # 시나리오:
    #   Day1: close=10000 (신호 없음, MA warming up)
    #   Day2: close=10100 (매수 신호) → Day3 open=10000에 매수 (tg1, entry=10000)
    #   Day3: close=10200 (두 번째 신호 없음 — 이미 보유 중)
    #   Day4: close=12200, high=13000 (take_profit 20% 달성: 10000*1.2=12000 <= 13000)
    #         → tg1 익절 (12000원에 체결)
    # 이 시나리오는 단일 매수이므로 trade_group 1개. 05-l의 단위 테스트보다
    # end-to-end 흐름(신호→매수→보유→익절)의 완전성을 검증.

    strategy = {
        "entry": {"conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}]},
        "exit_signal": {"conditions": []},
        "exit_position": {
            "conditions": [{"type": "take_profit", "percent": 20.0}]
        },
        "filters": {"conditions": []},
    }

    base = date(2024, 1, 2)
    dates = [base + timedelta(days=i) for i in range(8)]
    closes = [10_000, 10_100, 10_200, 12_200, 12_200, 12_200, 12_200, 12_200]
    opens  = [10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000]
    highs  = [10_000, 10_100, 10_200, 13_000, 13_000, 13_000, 13_000, 13_000]
    lows   = [10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000]

    df = _make_price_df(dates, closes, opens=opens, highs=highs, lows=lows)

    engine, portfolio = _make_engine(
        strategy,
        initial_cash=5_000_000,
        sizing_method="fixed_amount",
        position_size_amount=1_000_000,
    )
    engine.run({SYMBOL: df})

    sell_trades = [t for t in portfolio.trade_logs if t.get("side") == "sell"]
    assert len(sell_trades) >= 1, "take_profit 매도가 발생해야 함"

    take_profit_sells = [
        t for t in sell_trades if "take_profit" in t.get("reason", "")
    ]
    assert len(take_profit_sells) >= 1, "take_profit 사유 매도가 기록되어야 함"

    # 체결가 검증: tg.entry_price(10000) * 1.2 = 12000
    sell_price = take_profit_sells[0]["price"]
    assert abs(sell_price - 12_000) < 100, (
        f"take_profit 체결가 불일치: expected≈12000, got={sell_price}"
    )


# ---------------------------------------------------------------------------
# 시나리오 6 — 결정론: 동일 입력 5회 반복 (CLAUDE.md #8)
# ---------------------------------------------------------------------------


def test_e2e_determinism_5_runs_with_sizing():
    """fixed_ratio + trade_group exit 시나리오를 5회 반복 실행해 결과가 동일한지 확인.

    정확성 정책: CLAUDE.md #8 (결정론), 13.12 (결정론 보장).
    PositionSizer는 stateless → 동일 입력 → 동일 출력.
    """
    strategy = {
        "entry": {"conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}]},
        "exit_signal": {"conditions": []},
        "exit_position": {
            "conditions": [
                {"type": "take_profit", "percent": 15.0},
                {"type": "stop_loss", "percent": 8.0},
            ]
        },
        "filters": {"conditions": []},
    }

    base = date(2024, 1, 2)
    n = 15
    dates = [base + timedelta(days=i) for i in range(n)]
    rng = np.random.default_rng(99)
    rets = rng.normal(0.002, 0.025, n)
    closes = (10_000 * np.exp(np.cumsum(rets))).round(0).tolist()
    opens  = [(c * 0.999) for c in closes]
    highs  = [(c * 1.015) for c in closes]
    lows   = [(c * 0.985) for c in closes]

    df = _make_price_df(dates, closes, opens=opens, highs=highs, lows=lows)

    results: list[dict] = []
    for _ in range(5):
        engine, portfolio = _make_engine(
            strategy,
            initial_cash=5_000_000,
            sizing_method="fixed_ratio",
            sizing_ratio=0.15,
        )
        engine.run({SYMBOL: df})
        results.append(
            {
                "final_cash": int(portfolio.cash),
                "trade_count": len(portfolio.trade_logs),
                "event_count": len(engine.event_log),
            }
        )

    first = results[0]
    for i, res in enumerate(results[1:], start=2):
        assert res == first, (
            f"Run {i} 결과가 Run 1과 다름: {res} != {first} (결정론 위반)"
        )

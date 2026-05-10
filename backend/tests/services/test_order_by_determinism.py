"""ORDER BY 결정론 테스트 (13-t 해소 검증).

동일 데이터를 2회 조회했을 때 순서가 항상 동일한지 확인.
대상: backtest_runs, trade_executions, trade_groups, daily_equity, cash_events, strategies.

CLAUDE.md #8 / 13번 §12.1 정책 준수.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.models.backtest import BacktestStatus
from app.models.cash_event import CashEvent
from app.models.daily_equity import DailyEquity
from app.models.trade import TradeExecution, TradeGroup
from app.services import backtest_service, strategy_service


# ---------------------------------------------------------------------------
# 공통 fixture
# ---------------------------------------------------------------------------

_SAMPLE_JSON = {
    "entry": {
        "logic": "AND",
        "conditions": [
            {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
        ],
    },
    "exit_position": {
        "logic": "OR",
        "conditions": [
            {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
            {"type": "stop_loss", "percent": 3.0},
        ],
    },
}


def _build_synthetic_series(seed: int = 42, n: int = 90) -> pd.DataFrame:
    """결정론적 합성 가격 시계열."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.001, scale=0.02, size=n)
    closes = 10_000 * np.exp(np.cumsum(returns))
    closes = closes.round(0)
    high_mults = 1 + rng.uniform(0.001, 0.015, n)
    low_mults = 1 - rng.uniform(0.001, 0.015, n)
    open_jitter = rng.uniform(-0.005, 0.005, n)
    opens = (closes * (1 + open_jitter)).round(0)
    highs = (np.maximum(closes, opens) * high_mults).round(0)
    lows = (np.minimum(closes, opens) * low_mults).round(0)
    base_date = date(2024, 1, 2)
    dates = [base_date + timedelta(days=i) for i in range(n)]
    df = pd.DataFrame({
        "date": dates,
        "adj_open": opens,
        "adj_high": highs,
        "adj_low": lows,
        "adj_close": closes,
        "adj_volume": np.full(n, 10_000.0),
    })
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


@pytest.fixture
def strategy(db_session, user):
    return strategy_service.create_strategy(
        db_session,
        user_id=user.id,
        name="ORDER BY 테스트용",
        strategy_json=_SAMPLE_JSON,
    )


@pytest.fixture
def completed_run(db_session, user, strategy):
    """완료된 BacktestRun fixture (trade_executions + daily_equity 생성)."""
    df = _build_synthetic_series(seed=42, n=90)
    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="ORDER BY 결정론 검증",
        universe_config={"symbol": "GOLDEN", "position_size_amount": 5_000_000},
        start_date=df["date"].iloc[0],
        end_date=df["date"].iloc[-1],
        initial_cash=10_000_000.0,
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
        tick_rounding="nearest",
    )
    backtest_service.run_backtest(db_session, run.id, df)
    db_session.refresh(run)
    return run


# ---------------------------------------------------------------------------
# trade_executions — (execution_date ASC, id ASC)
# ---------------------------------------------------------------------------


def test_trade_executions_order_is_deterministic(db_session, completed_run):
    """trade_executions를 2회 조회해 순서가 동일한지 확인."""
    def fetch():
        return (
            db_session.query(TradeExecution)
            .filter_by(run_id=completed_run.id)
            .order_by(TradeExecution.execution_date.asc(), TradeExecution.id.asc())
            .all()
        )

    first = [(ex.execution_date, ex.id) for ex in fetch()]
    second = [(ex.execution_date, ex.id) for ex in fetch()]

    assert len(first) > 0, "trade_executions가 비어 있음 — 엔진 실행 확인 필요"
    assert first == second, "2회 조회 결과 순서가 다름 — ORDER BY 결정론 위반"


def test_trade_executions_sorted_by_date_then_id(db_session, completed_run):
    """(execution_date ASC, id ASC) 정렬 준수 검증."""
    rows = (
        db_session.query(TradeExecution)
        .filter_by(run_id=completed_run.id)
        .order_by(TradeExecution.execution_date.asc(), TradeExecution.id.asc())
        .all()
    )

    for i in range(len(rows) - 1):
        curr = rows[i]
        nxt = rows[i + 1]
        # date 오름차순 또는 같은 날이면 id 오름차순
        assert (curr.execution_date, curr.id) <= (nxt.execution_date, nxt.id), (
            f"정렬 위반: index={i}, "
            f"({curr.execution_date}, id={curr.id}) > "
            f"({nxt.execution_date}, id={nxt.id})"
        )


# ---------------------------------------------------------------------------
# trade_groups — (entry_date ASC, id ASC)
# ---------------------------------------------------------------------------


def test_trade_groups_order_is_deterministic(db_session, completed_run):
    """trade_groups를 2회 조회해 순서가 동일한지 확인."""
    def fetch():
        return (
            db_session.query(TradeGroup)
            .filter_by(run_id=completed_run.id)
            .order_by(TradeGroup.entry_date.asc(), TradeGroup.id.asc())
            .all()
        )

    first = [(tg.entry_date, tg.id) for tg in fetch()]
    second = [(tg.entry_date, tg.id) for tg in fetch()]

    assert len(first) > 0, "trade_groups가 비어 있음"
    assert first == second, "2회 조회 결과 순서가 다름 — ORDER BY 결정론 위반"


# ---------------------------------------------------------------------------
# daily_equity — (date ASC, id ASC)
# ---------------------------------------------------------------------------


def test_daily_equity_order_is_deterministic(db_session, completed_run):
    """daily_equity를 2회 조회해 순서가 동일한지 확인."""
    def fetch():
        return (
            db_session.query(DailyEquity)
            .filter_by(run_id=completed_run.id)
            .order_by(DailyEquity.date.asc(), DailyEquity.id.asc())
            .all()
        )

    first = [(eq.date, eq.id) for eq in fetch()]
    second = [(eq.date, eq.id) for eq in fetch()]

    assert len(first) > 0, "daily_equity가 비어 있음"
    assert first == second, "2회 조회 결과 순서가 다름 — ORDER BY 결정론 위반"


def test_daily_equity_sorted_by_date_then_id(db_session, completed_run):
    """(date ASC, id ASC) 정렬 준수 검증."""
    rows = (
        db_session.query(DailyEquity)
        .filter_by(run_id=completed_run.id)
        .order_by(DailyEquity.date.asc(), DailyEquity.id.asc())
        .all()
    )

    for i in range(len(rows) - 1):
        curr = rows[i]
        nxt = rows[i + 1]
        assert (curr.date, curr.id) <= (nxt.date, nxt.id), (
            f"정렬 위반: index={i}, "
            f"(date={curr.date}, id={curr.id}) > "
            f"(date={nxt.date}, id={nxt.id})"
        )


# ---------------------------------------------------------------------------
# cash_events — (date ASC, id ASC)
# ---------------------------------------------------------------------------


def test_cash_events_order_deterministic_with_multiple_events(db_session, user):
    """같은 날짜에 여러 CashEvent가 있을 때 id 기준 결정론 확인."""
    # strategy + run 없이 직접 CashEvent 삽입 (단위 테스트)
    from datetime import timezone

    from app.models.backtest import BacktestRun, BacktestStatus
    from app.models.strategy import Strategy

    strat = strategy_service.create_strategy(
        db_session,
        user_id=user.id,
        name="cash_event 테스트",
        strategy_json=_SAMPLE_JSON,
    )
    from datetime import datetime as dt

    run = BacktestRun(
        user_id=user.id,
        strategy_id=strat.id,
        run_name="cash_event_order_test",
        strategy_snapshot_json=_SAMPLE_JSON,
        universe_config_json={"symbol": "X"},
        start_date=date(2024, 1, 2),
        end_date=date(2024, 3, 31),
        initial_cash=1_000_000.0,
        fee_rate=0.0,
        tax_rate_json=0.0,
        slippage=0.0,
        status=BacktestStatus.COMPLETED,
        created_at=dt.now(timezone.utc),
    )
    db_session.add(run)
    db_session.flush()

    # 같은 날짜의 이벤트 3건 — id 자동 증가 순서로 정렬되어야 함
    same_date = date(2024, 2, 1)
    for i in range(3):
        db_session.add(
            CashEvent(
                run_id=run.id,
                date=same_date,
                event_type="cash_shortage",
                cash_before=float(500_000 - i * 1000),
                cash_after=float(400_000 - i * 1000),
                created_at=dt.now(timezone.utc),
            )
        )
    db_session.commit()

    def fetch():
        return (
            db_session.query(CashEvent)
            .filter_by(run_id=run.id)
            .order_by(CashEvent.date.asc(), CashEvent.id.asc())
            .all()
        )

    first = [ev.id for ev in fetch()]
    second = [ev.id for ev in fetch()]

    assert len(first) == 3
    assert first == second, "같은 날짜 cash_events — id 기준 순서가 불일치"
    # id 오름차순 확인
    assert first == sorted(first), "id ASC 정렬 위반"


# ---------------------------------------------------------------------------
# strategies — (updated_at DESC, id DESC)
# ---------------------------------------------------------------------------


def test_strategies_list_order_is_deterministic(db_session, user):
    """list_strategies가 2회 반환 순서 동일한지 확인."""
    # 여러 전략 생성
    for i in range(5):
        strategy_service.create_strategy(
            db_session,
            user_id=user.id,
            name=f"전략 {i}",
            strategy_json=_SAMPLE_JSON,
        )

    first = [s.id for s in strategy_service.list_strategies(db_session, user_id=user.id)]
    second = [s.id for s in strategy_service.list_strategies(db_session, user_id=user.id)]

    assert len(first) == 5
    assert first == second, "list_strategies 2회 결과 순서가 다름"


def test_strategies_list_sorted_updated_at_desc(db_session, user):
    """updated_at DESC, id DESC 정렬 준수 검증.

    updated_at이 같은 전략은 id DESC로 정렬되어야 한다.
    SQLite에서 AUTOINCREMENT id가 삽입 순서를 반영하므로
    같은 updated_at이면 나중에 생성된 것이 먼저 온다 (id DESC).
    """
    strategies = [
        strategy_service.create_strategy(
            db_session,
            user_id=user.id,
            name=f"순서 테스트 {i}",
            strategy_json=_SAMPLE_JSON,
        )
        for i in range(3)
    ]

    result = strategy_service.list_strategies(db_session, user_id=user.id)

    # 결과에서 인접 쌍이 (updated_at DESC, id DESC) 정렬을 지키는지 확인
    for i in range(len(result) - 1):
        curr = result[i]
        nxt = result[i + 1]
        assert (curr.updated_at, curr.id) >= (nxt.updated_at, nxt.id), (
            f"정렬 위반: index={i}, "
            f"updated_at={curr.updated_at}, id={curr.id} < "
            f"updated_at={nxt.updated_at}, id={nxt.id}"
        )

    # 생성된 전략 id가 결과에 모두 포함되는지
    result_ids = {s.id for s in result}
    created_ids = {s.id for s in strategies}
    assert created_ids.issubset(result_ids)


# ---------------------------------------------------------------------------
# strategy_versions — (version ASC, id ASC)
# ---------------------------------------------------------------------------


def test_strategy_versions_order_is_deterministic(db_session, user):
    """list_strategy_versions가 2회 반환 순서 동일한지 확인."""
    strat = strategy_service.create_strategy(
        db_session,
        user_id=user.id,
        name="버전 정렬 테스트",
        strategy_json=_SAMPLE_JSON,
    )
    # 버전 추가
    updated_json = dict(_SAMPLE_JSON)
    updated_json["_test"] = "v2"
    strategy_service.update_strategy(
        db_session,
        strat.id,
        user_id=user.id,
        strategy_json=updated_json,
        change_note="v2",
    )

    first = [v.version for v in strategy_service.list_strategy_versions(
        db_session, strat.id, user_id=user.id
    )]
    second = [v.version for v in strategy_service.list_strategy_versions(
        db_session, strat.id, user_id=user.id
    )]

    assert len(first) == 2
    assert first == second, "list_strategy_versions 2회 결과 순서가 다름"
    assert first == sorted(first), "version ASC 정렬 위반"

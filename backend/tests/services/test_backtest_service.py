"""backtest_service 통합 테스트.

Phase 1 BacktestEngine + Phase 2 모델 매핑까지 end-to-end로 검증.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.models.backtest import BacktestStatus
from app.models.daily_equity import DailyEquity
from app.models.trade import TradeExecution, TradeGroup
from app.services import backtest_service, strategy_service


@pytest.fixture
def strategy(db_session, user, sample_strategy_json):
    return strategy_service.create_strategy(
        db_session, user_id=user.id, name="MA5+익절손절", strategy_json=sample_strategy_json
    )


def _build_synthetic_series(seed: int, n: int) -> pd.DataFrame:
    """결정론적 합성 가격 (Phase 1 golden test와 동일 방식)."""
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
        "adj_open": opens, "adj_high": highs, "adj_low": lows, "adj_close": closes,
        "adj_volume": np.full(n, 10_000.0),
    })
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def test_create_backtest_run_saves_snapshot(db_session, user, strategy):
    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="테스트1",
        universe_config={"symbol": "GOLDEN", "position_size_amount": 5_000_000},
        start_date=date(2024, 1, 2),
        end_date=date(2024, 12, 31),
        initial_cash=10_000_000.0,
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
    )
    assert run.id is not None
    assert run.status == BacktestStatus.PENDING
    # snapshot 저장 확인
    assert run.strategy_snapshot_json == strategy.strategy_json
    # 스냅샷은 deep copy — 원본 변경 시 영향 없음
    strategy.strategy_json["entry"]["conditions"][0]["ma_period"] = 999
    db_session.commit()
    db_session.refresh(run)
    assert run.strategy_snapshot_json["entry"]["conditions"][0]["ma_period"] == 5


def test_run_backtest_persists_full_result(db_session, user, strategy):
    df = _build_synthetic_series(seed=42, n=90)

    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="GOLDEN seed=42",
        universe_config={"symbol": "GOLDEN", "position_size_amount": 5_000_000},
        start_date=df["date"].iloc[0],
        end_date=df["date"].iloc[-1],
        initial_cash=10_000_000.0,
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
        tick_rounding="nearest",
    )
    result = backtest_service.run_backtest(db_session, run.id, df)

    db_session.refresh(run)
    assert run.status == BacktestStatus.COMPLETED
    assert run.progress_pct == 100.0
    assert run.started_at is not None
    assert run.finished_at is not None

    # Phase 1 골든 테스트와 동일한 핵심 지표 (Phase 1 frozen 값과 일치)
    assert result.trade_count == 8
    assert result.open_position_count == 1
    assert result.win_rate == pytest.approx(37.5, abs=0.01)
    assert result.final_equity == pytest.approx(10_188_570.0, abs=1.0)

    # daily_equity 영속화
    eq_count = db_session.query(DailyEquity).filter_by(run_id=run.id).count()
    assert eq_count == 90

    # trade_groups + executions 영속화 (BUY 9 + SELL 8)
    tg_count = db_session.query(TradeGroup).filter_by(run_id=run.id).count()
    assert tg_count == 9
    ex_count = db_session.query(TradeExecution).filter_by(run_id=run.id).count()
    assert ex_count == 17  # 9 BUY + 8 SELL


def test_run_backtest_marks_failed_on_exception(db_session, user, strategy):
    """잘못된 df (필수 컬럼 없음) → 엔진이 예외 → status=FAILED."""
    bad_df = pd.DataFrame({"date": [date(2024, 1, 1)], "adj_close": [100]})
    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="bad",
        universe_config={"symbol": "X"},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        initial_cash=1_000_000.0,
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
    )
    # 엔진이 KeyError 발생 (필수 컬럼 없음). 그 외 일관 처리는 service가 status=FAILED로 잡음.
    with pytest.raises(KeyError):
        backtest_service.run_backtest(db_session, run.id, bad_df)

    db_session.refresh(run)
    assert run.status == BacktestStatus.FAILED
    assert run.error_message is not None
    assert run.finished_at is not None


def test_get_backtest_summary_pending(db_session, user, strategy):
    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="x",
        universe_config={"symbol": "X"},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        initial_cash=1_000_000.0,
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
    )
    summary = backtest_service.get_backtest_summary(db_session, run.id)
    assert summary["status"] == "pending"
    assert summary["summary"] is None


def test_get_backtest_summary_completed(db_session, user, strategy):
    df = _build_synthetic_series(seed=42, n=90)
    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="x",
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

    summary = backtest_service.get_backtest_summary(db_session, run.id)
    assert summary["status"] == "completed"
    assert summary["summary"]["trade_count"] == 8


def test_run_backtest_unknown_run_raises(db_session):
    from app.core.exceptions import BacktestRunNotFoundError

    df = _build_synthetic_series(seed=42, n=10)
    with pytest.raises(BacktestRunNotFoundError):
        backtest_service.run_backtest(db_session, 999, df)


def test_persist_idempotency_separate_runs(db_session, user, strategy):
    """같은 run_id에 두 번 실행하지 않고 새 run 만들면 결과는 독립적."""
    df = _build_synthetic_series(seed=42, n=60)

    runs = []
    for _ in range(2):
        r = backtest_service.create_backtest_run(
            db_session,
            user_id=user.id,
            strategy_id=strategy.id,
            run_name="repeat",
            universe_config={"symbol": "GOLDEN", "position_size_amount": 5_000_000},
            start_date=df["date"].iloc[0],
            end_date=df["date"].iloc[-1],
            initial_cash=10_000_000.0,
            fee_rate=0.0,
            tax_rate=0.0,
            slippage=0.0,
            tick_rounding="nearest",
        )
        backtest_service.run_backtest(db_session, r.id, df)
        runs.append(r)

    # 두 run의 trade_groups가 독립적
    tg1 = db_session.query(TradeGroup).filter_by(run_id=runs[0].id).count()
    tg2 = db_session.query(TradeGroup).filter_by(run_id=runs[1].id).count()
    assert tg1 == tg2  # 결정론

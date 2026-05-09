"""DailyEquity 모델 테스트."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.backtest import BacktestRun
from app.models.daily_equity import DailyEquity
from app.models.strategy import Strategy
from app.models.user import User


@pytest.fixture
def run(db_session):
    u = User(email="t@example.com")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    s = Strategy(
        user_id=u.id,
        name="X",
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    r = BacktestRun(
        user_id=u.id,
        strategy_id=s.id,
        strategy_snapshot_json=s.strategy_json,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        initial_cash=10_000_000.0,
        fee_rate=0.0,
        tax_rate_json=0.0,
        slippage=0.0,
        created_at=datetime.now(UTC),
    )
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r


def _eq(run, day_offset: int = 0, **overrides):
    defaults = dict(
        run_id=run.id,
        date=date(2024, 1, 1) + timedelta(days=day_offset),
        cash=9_000_000.0,
        stock_value=1_000_000.0,
        total_equity=10_000_000.0,
        positions_count=1,
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return DailyEquity(**defaults)


def test_create_daily_equity(db_session, run):
    eq = _eq(run, drawdown=-2.5)
    db_session.add(eq)
    db_session.commit()
    db_session.refresh(eq)

    assert eq.id is not None
    assert eq.run_id == run.id
    assert eq.daily_return == 0.0
    assert eq.cumulative_return == 0.0
    assert eq.drawdown == -2.5


def test_unique_constraint_run_date(db_session, run):
    db_session.add(_eq(run, day_offset=0))
    db_session.commit()

    db_session.add(_eq(run, day_offset=0))  # 같은 (run_id, date)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_multiple_dates_per_run(db_session, run):
    for offset in range(5):
        db_session.add(_eq(run, day_offset=offset, total_equity=10_000_000.0 + offset * 1000))
    db_session.commit()

    rows = (
        db_session.query(DailyEquity)
        .filter_by(run_id=run.id)
        .order_by(DailyEquity.date)
        .all()
    )
    assert len(rows) == 5
    assert rows[0].date == date(2024, 1, 1)
    assert rows[4].date == date(2024, 1, 5)


def test_run_delete_cascades_daily_equity(db_session, run):
    db_session.add(_eq(run, day_offset=0))
    db_session.add(_eq(run, day_offset=1))
    db_session.commit()

    run_id = run.id
    db_session.delete(run)
    db_session.commit()

    assert db_session.query(DailyEquity).filter_by(run_id=run_id).count() == 0


def test_repr(db_session, run):
    eq = _eq(run, total_equity=12_345_678.0, drawdown=-3.21)
    db_session.add(eq)
    db_session.commit()
    s = repr(eq)
    assert "DailyEquity" in s
    assert "12345678" in s

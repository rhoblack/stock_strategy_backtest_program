"""BacktestRun + BacktestResult 모델 테스트."""

from datetime import UTC, date, datetime

import pytest

from app.models.backtest import BacktestResult, BacktestRun
from app.models.enums import BacktestStatus
from app.models.strategy import Strategy
from app.models.user import User


@pytest.fixture
def user_and_strategy(db_session):
    u = User(email="trader@example.com")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    s = Strategy(
        user_id=u.id,
        name="MA Cross",
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    return u, s


def _new_run(user, strategy, **overrides) -> BacktestRun:
    defaults = dict(
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="테스트",
        strategy_snapshot_json=strategy.strategy_json,
        universe_config_json={"market": "KOSPI", "selection_method": "all"},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        initial_cash=10_000_000.0,
        fee_rate=0.00015,
        tax_rate_json=[
            {"from": "2024-01-01", "rate": 0.0018},
            {"from": "2025-01-01", "rate": 0.0015},
        ],
        slippage=0.001,
        random_seed=42,
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return BacktestRun(**defaults)


def test_create_backtest_run_with_defaults(db_session, user_and_strategy):
    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.id is not None
    assert run.status == BacktestStatus.PENDING
    assert run.progress_pct == 0.0
    assert run.execution_price_type == "next_open"
    assert run.use_adjusted_price is True
    assert run.tick_rounding == "buy_up_sell_down"
    assert run.priority_method == "trading_value_desc"
    assert run.priority_tie_breaker == "symbol_asc"
    assert run.error_message is None


def test_backtest_run_jsons_round_trip(db_session, user_and_strategy):
    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # tax_rate_json 시계열 round-trip
    assert isinstance(run.tax_rate_json, list)
    assert run.tax_rate_json[0]["rate"] == 0.0018
    # universe_config 보존
    assert run.universe_config_json["market"] == "KOSPI"


def test_backtest_run_status_transition(db_session, user_and_strategy):
    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()

    run.status = BacktestStatus.RUNNING
    run.started_at = datetime.now(UTC)
    run.progress_pct = 50.0
    db_session.commit()
    db_session.refresh(run)
    assert run.status == BacktestStatus.RUNNING

    run.status = BacktestStatus.COMPLETED
    run.finished_at = datetime.now(UTC)
    run.progress_pct = 100.0
    db_session.commit()
    db_session.refresh(run)
    assert run.status == BacktestStatus.COMPLETED


def test_backtest_run_user_relationship(db_session, user_and_strategy):
    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.user.id == user.id
    assert run.strategy.id == strategy.id


def test_create_backtest_result_for_run(db_session, user_and_strategy):
    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    result = BacktestResult(
        run_id=run.id,
        initial_cash=10_000_000.0,
        final_equity=10_188_570.0,
        total_return_pct=1.8857,
        annual_return_pct=7.96,
        mdd_pct=-4.9032,
        trade_count=8,
        open_position_count=1,
        win_rate=37.5,
        avg_holding_days=7.5,
        avg_profit_pct=6.13,
        avg_loss_pct=3.0,
        profit_factor=1.2252,
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    assert result.id is not None
    assert result.run_id == run.id

    db_session.refresh(run)
    assert run.result is result


def test_backtest_result_unique_per_run(db_session, user_and_strategy):
    """한 run에는 result가 1개만 존재."""
    from sqlalchemy.exc import IntegrityError

    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    r1 = BacktestResult(
        run_id=run.id,
        initial_cash=10_000_000.0,
        final_equity=11_000_000.0,
        total_return_pct=10.0,
    )
    db_session.add(r1)
    db_session.commit()

    r2 = BacktestResult(
        run_id=run.id,
        initial_cash=10_000_000.0,
        final_equity=12_000_000.0,
        total_return_pct=20.0,
    )
    db_session.add(r2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_run_delete_cascades_result(db_session, user_and_strategy):
    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    result = BacktestResult(
        run_id=run.id,
        initial_cash=10_000_000.0,
        final_equity=10_000_000.0,
        total_return_pct=0.0,
    )
    db_session.add(result)
    db_session.commit()

    result_id = result.id
    db_session.delete(run)
    db_session.commit()

    assert db_session.query(BacktestResult).filter_by(id=result_id).first() is None


def test_strategy_delete_restrict_when_runs_exist(db_session, user_and_strategy):
    """Strategy에 backtest_runs가 있으면 strategy 삭제는 RESTRICT로 차단되어야 함.

    SQLite는 FK 제약이 PRAGMA foreign_keys=ON 시점에만 활성화되는데, conftest는
    기본 SQLite 설정이라 실제 RESTRICT 위반을 SQLAlchemy가 잡지 못할 수 있음.
    이 경우 cascade 동작 대신 모델의 의도(ON DELETE RESTRICT) 자체만 검증.
    """
    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()

    # ondelete='RESTRICT'가 모델에 설정되어 있는지 메타로 확인
    from app.models.backtest import BacktestRun as _Run

    fk = next(iter(_Run.__table__.c.strategy_id.foreign_keys))
    assert fk.ondelete == "RESTRICT"


def test_backtest_run_repr(db_session, user_and_strategy):
    user, strategy = user_and_strategy
    run = _new_run(user, strategy)
    db_session.add(run)
    db_session.commit()
    s = repr(run)
    assert "BacktestRun" in s
    assert "pending" in s

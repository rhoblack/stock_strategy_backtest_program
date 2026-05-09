"""TradeGroup + TradeExecution 모델 테스트."""

from datetime import UTC, date, datetime

import pytest

from app.models.backtest import BacktestRun
from app.models.enums import TradeExecutionType
from app.models.strategy import Strategy
from app.models.trade import TradeExecution, TradeGroup
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


def _new_tg(run, **overrides) -> TradeGroup:
    defaults = dict(
        run_id=run.id,
        symbol="005930",
        name="삼성전자",
        entry_date=date(2024, 3, 12),
        entry_price=72_000.0,
        entry_quantity=13,
        remaining_quantity=13,
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return TradeGroup(**defaults)


def test_create_trade_group(db_session, run):
    tg = _new_tg(run)
    db_session.add(tg)
    db_session.commit()
    db_session.refresh(tg)

    assert tg.id is not None
    assert tg.symbol == "005930"
    assert tg.remaining_quantity == 13
    assert tg.fully_closed_at is None
    assert tg.run.id == run.id


def test_trade_group_partial_sell_keeps_entry_price(db_session, run):
    """부분 매도 후에도 entry_price 변경 안 됨 (정확성 정책 13.9.3)."""
    tg = _new_tg(run, entry_price=10_000.0, entry_quantity=10, remaining_quantity=10)
    db_session.add(tg)
    db_session.commit()
    db_session.refresh(tg)

    tg.remaining_quantity -= 4
    db_session.commit()
    db_session.refresh(tg)

    assert tg.remaining_quantity == 6
    assert tg.entry_price == 10_000.0  # 변경 안 됨


def test_create_buy_execution(db_session, run):
    tg = _new_tg(run)
    db_session.add(tg)
    db_session.commit()
    db_session.refresh(tg)

    ex = TradeExecution(
        trade_group_id=tg.id,
        run_id=run.id,
        execution_date=date(2024, 3, 12),
        execution_type=TradeExecutionType.BUY,
        price=72_000.0,
        quantity=13,
        gross_amount=72_000 * 13,
        fee=0.0,
        tax=0.0,
        net_amount=72_000 * 13,
        created_at=datetime.now(UTC),
    )
    db_session.add(ex)
    db_session.commit()
    db_session.refresh(ex)

    assert ex.is_buy is True
    assert ex.is_sell is False
    assert ex.realized_profit is None


def test_create_sell_execution(db_session, run):
    tg = _new_tg(run)
    db_session.add(tg)
    db_session.commit()
    db_session.refresh(tg)

    ex = TradeExecution(
        trade_group_id=tg.id,
        run_id=run.id,
        execution_date=date(2024, 4, 5),
        execution_type=TradeExecutionType.SELL,
        price=78_200.0,
        quantity=13,
        gross_amount=78_200 * 13,
        fee=152.49,
        tax=1_829.88,
        net_amount=78_200 * 13 - 152.49 - 1_829.88,
        realized_profit=80_600.0,
        realized_profit_rate=8.61,
        exit_reason="take_profit",
        created_at=datetime.now(UTC),
    )
    db_session.add(ex)
    db_session.commit()
    db_session.refresh(ex)

    assert ex.is_sell is True
    assert ex.is_buy is False
    assert ex.exit_reason == "take_profit"
    assert ex.reason_text == "take_profit"


def test_partial_sell_executions_under_one_trade_group(db_session, run):
    """한 trade_group에 PARTIAL_SELL 여러 건 + 마지막에 SELL."""
    tg = _new_tg(run, entry_quantity=10, remaining_quantity=10)
    db_session.add(tg)
    db_session.commit()
    db_session.refresh(tg)

    for d, qty, kind in [
        (date(2024, 3, 12), 10, TradeExecutionType.BUY),
        (date(2024, 4, 1), 4, TradeExecutionType.PARTIAL_SELL),
        (date(2024, 4, 10), 6, TradeExecutionType.SELL),
    ]:
        db_session.add(
            TradeExecution(
                trade_group_id=tg.id,
                run_id=run.id,
                execution_date=d,
                execution_type=kind,
                price=10_000.0,
                quantity=qty,
                gross_amount=10_000 * qty,
                fee=0.0,
                tax=0.0,
                net_amount=10_000 * qty,
                created_at=datetime.now(UTC),
            )
        )
    db_session.commit()
    db_session.refresh(tg)

    assert len(tg.executions) == 3
    # order_by execution_date
    assert [e.execution_date for e in tg.executions] == [
        date(2024, 3, 12),
        date(2024, 4, 1),
        date(2024, 4, 10),
    ]


def test_trade_group_delete_cascades_executions(db_session, run):
    tg = _new_tg(run)
    db_session.add(tg)
    db_session.commit()
    db_session.refresh(tg)

    db_session.add(
        TradeExecution(
            trade_group_id=tg.id,
            run_id=run.id,
            execution_date=date(2024, 3, 12),
            execution_type=TradeExecutionType.BUY,
            price=72_000.0,
            quantity=13,
            gross_amount=72_000 * 13,
            net_amount=72_000 * 13,
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    tg_id = tg.id
    db_session.delete(tg)
    db_session.commit()

    assert (
        db_session.query(TradeExecution).filter_by(trade_group_id=tg_id).first() is None
    )


def test_run_delete_cascades_trade_groups(db_session, run):
    """BacktestRun 삭제 시 모든 trade_groups + executions 같이 삭제."""
    tg = _new_tg(run)
    db_session.add(tg)
    db_session.commit()
    db_session.refresh(tg)

    db_session.add(
        TradeExecution(
            trade_group_id=tg.id,
            run_id=run.id,
            execution_date=date(2024, 3, 12),
            execution_type=TradeExecutionType.BUY,
            price=72_000.0,
            quantity=13,
            gross_amount=72_000 * 13,
            net_amount=72_000 * 13,
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    run_id = run.id
    db_session.delete(run)
    db_session.commit()

    assert db_session.query(TradeGroup).filter_by(run_id=run_id).first() is None
    assert (
        db_session.query(TradeExecution).filter_by(run_id=run_id).first() is None
    )

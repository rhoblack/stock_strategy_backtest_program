"""backtest_service 통합 테스트.

Phase 1 BacktestEngine + Phase 2 모델 매핑까지 end-to-end로 검증.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.models.backtest import BacktestStatus
from app.models.cash_event import CashEvent
from app.models.daily_equity import DailyEquity
from app.models.enums import TradeExecutionType
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


# ==========================================================================
# 014 — TradeExecution.fee/tax + DailyEquity.daily_return/cumulative_return
# + CashEvent 비용 분해 영속화 회귀
# ==========================================================================


def test_trade_executions_persist_fee_and_tax_with_costs(db_session, user, strategy):
    """fee_rate/tax_rate>0 시나리오에서 TradeExecution.fee/tax가 정확히 저장.

    리뷰 011 외부 4.7 + 014 step. ExecutionResult dataclass(013) → trade_logs →
    DB 컬럼 매핑이 0 하드코드 없이 분해되는지 확인.

    BUY는 tax=0 강제 (ExecutionResult.calculate_buy_cost), SELL은 tax > 0.
    """
    df = _build_synthetic_series(seed=42, n=90)

    fee_rate = 0.0015
    tax_rate = 0.0023  # 13.6 시계열의 단일 값 형태 (전 기간 동일)

    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="fee+tax",
        universe_config={"symbol": "GOLDEN", "position_size_amount": 5_000_000},
        start_date=df["date"].iloc[0],
        end_date=df["date"].iloc[-1],
        initial_cash=10_000_000.0,
        fee_rate=fee_rate,
        tax_rate=tax_rate,
        slippage=0.0,
        tick_rounding="nearest",
    )
    backtest_service.run_backtest(db_session, run.id, df)

    execs = (
        db_session.query(TradeExecution)
        .filter_by(run_id=run.id)
        .order_by(TradeExecution.id)
        .all()
    )
    assert execs, "체결이 0건이면 회귀를 검증할 수 없음 — 합성 데이터 검토 필요"

    buys = [e for e in execs if e.execution_type == TradeExecutionType.BUY]
    sells = [
        e
        for e in execs
        if e.execution_type
        in (TradeExecutionType.SELL, TradeExecutionType.PARTIAL_SELL)
    ]
    assert buys and sells

    for buy in buys:
        # BUY: tax 0 강제 (ExecutionResult), fee = gross * fee_rate
        assert buy.tax == 0.0
        expected_fee = buy.gross_amount * fee_rate
        assert buy.fee == pytest.approx(expected_fee, rel=1e-9)
        # net_amount = gross + fee
        assert buy.net_amount == pytest.approx(buy.gross_amount + buy.fee, rel=1e-9)
        # gross = price * quantity (체결가 기준)
        assert buy.gross_amount == pytest.approx(buy.price * buy.quantity, rel=1e-9)

    for sell in sells:
        assert sell.tax > 0.0  # 시계열 적용 결과
        expected_tax = sell.gross_amount * tax_rate
        expected_fee = sell.gross_amount * fee_rate
        assert sell.tax == pytest.approx(expected_tax, rel=1e-9)
        assert sell.fee == pytest.approx(expected_fee, rel=1e-9)
        # net = gross - fee - tax
        assert sell.net_amount == pytest.approx(
            sell.gross_amount - sell.fee - sell.tax, rel=1e-9
        )


def test_daily_equity_persists_returns(db_session, user, strategy):
    """DailyEquity.daily_return / cumulative_return이 시퀀스 일관성 유지.

    M5 회귀. % 단위 — drawdown / mdd_pct와 동일.
    cumulative_return[i] ≈ ∏(1 + daily_return/100) - 1, % 환산.
    """
    df = _build_synthetic_series(seed=42, n=90)

    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="daily-returns",
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

    rows = (
        db_session.query(DailyEquity)
        .filter_by(run_id=run.id)
        .order_by(DailyEquity.date)
        .all()
    )
    assert len(rows) == 90

    initial_cash = 10_000_000.0
    prev_equity = initial_cash

    for row in rows:
        # daily_return = (eq - prev) / prev * 100
        expected_daily = (row.total_equity - prev_equity) / prev_equity * 100
        assert row.daily_return == pytest.approx(expected_daily, rel=1e-9, abs=1e-9)
        # cumulative_return = (eq - initial) / initial * 100
        expected_cum = (row.total_equity - initial_cash) / initial_cash * 100
        assert row.cumulative_return == pytest.approx(expected_cum, rel=1e-9, abs=1e-9)
        prev_equity = row.total_equity

    # 시퀀스 일관성: ∏(1 + daily/100) ≈ 1 + cumulative[-1]/100
    product = 1.0
    for row in rows:
        product *= 1 + row.daily_return / 100
    final_cum_ratio = 1 + rows[-1].cumulative_return / 100
    assert product == pytest.approx(final_cum_ratio, rel=1e-6)


def test_daily_equity_returns_default_to_zero_with_zero_initial_cash(
    db_session, user, strategy
):
    """initial_cash=0 같은 가드 시나리오에서 daily/cum_return은 0으로 안전 저장.

    엔진 자체가 initial_cash=0를 거부할 수 있으나, 영속화 함수의 가드 로직 자체를
    문서적으로 검증 (NOT NULL 컬럼이라 None이면 IntegrityError 발생).
    """
    # 이 케이스는 단위 테스트로 _persist_daily_equity 직접 호출
    from app.backtest.result import DailyEquity as DEDataclass
    from app.models.backtest import BacktestRun

    run = BacktestRun(
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="zero-initial",
        strategy_snapshot_json={},
        universe_config_json={},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        initial_cash=0.0,
        fee_rate=0.0,
        tax_rate_json=0.0,
        slippage=0.0,
        execution_price_type="next_open",
        use_adjusted_price=True,
        tick_rounding="nearest",
        priority_method="trading_value_desc",
        priority_tie_breaker="symbol_asc",
        random_seed=None,
        status=BacktestStatus.COMPLETED,
        created_at=backtest_service._utcnow(),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    eqs = [
        DEDataclass(
            date=date(2024, 1, 1),
            cash=0.0,
            stock_value=0.0,
            total_equity=0.0,
            drawdown=0.0,
            positions_count=0,
        ),
        DEDataclass(
            date=date(2024, 1, 2),
            cash=0.0,
            stock_value=0.0,
            total_equity=0.0,
            drawdown=0.0,
            positions_count=0,
        ),
    ]
    backtest_service._persist_daily_equity(db_session, run, eqs)
    db_session.commit()

    rows = db_session.query(DailyEquity).filter_by(run_id=run.id).all()
    assert len(rows) == 2
    assert all(r.daily_return == 0.0 for r in rows)
    assert all(r.cumulative_return == 0.0 for r in rows)


def test_cash_events_persist_fee_tax_breakdown(db_session, user):
    """CashManager의 cash_event 비용 분해(exec_price/raw_price/gross/fee/tax/net)가
    DB CashEvent 컬럼에 그대로 영속화 (014 / 리뷰 011 C2).
    """
    # cash_management 정책이 있는 전략
    strategy_json = {
        "name": "강제매도 시나리오",
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
        "cash_management": {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.5},
                "target_selection": {"method": "lowest_return"},
                "repeat_until_cash_sufficient": True,
            },
        },
    }
    strategy = strategy_service.create_strategy(
        db_session, user_id=user.id, name="강제매도", strategy_json=strategy_json
    )

    # CashManager.handle_shortage가 실제로 발동하는지는 합성 데이터 + 단일 종목
    # 구조에서는 보장되지 않으므로, 단위 테스트로 _persist_cash_events 직접 호출.
    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="cash-events",
        universe_config={"symbol": "X"},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        initial_cash=1_000_000.0,
        fee_rate=0.0015,
        tax_rate=0.0023,
        slippage=0.0,
    )

    # CashManager가 만들 dict 형식 그대로 (013 step에서 정의)
    fake_events = [
        {
            "date": date(2024, 1, 5),
            "event_type": "cash_shortage",
            "cash_before": 100.0,
            "required_cash": 5_000.0,
            "action": "partial_sell",
            "symbol": "AAA",
            "sell_quantity": 10,
            "sell_amount": 9_877.0,  # 호환: net_amount과 동일
            "exec_price": 1_000.0,
            "raw_price": 1_000.0,
            "gross_amount": 10_000.0,
            "fee": 15.0,
            "tax": 23.0,
            "net_amount": 9_962.0,
            "cash_after": 10_062.0,
            "reason": "cash_shortage_partial_sell",
        }
    ]
    backtest_service._persist_cash_events(db_session, run, fake_events)
    db_session.commit()

    rows = db_session.query(CashEvent).filter_by(run_id=run.id).all()
    assert len(rows) == 1
    ev = rows[0]
    assert ev.event_type == "cash_shortage"
    assert ev.symbol == "AAA"
    assert ev.exec_price == pytest.approx(1_000.0)
    assert ev.raw_price == pytest.approx(1_000.0)
    assert ev.gross_amount == pytest.approx(10_000.0)
    assert ev.fee == pytest.approx(15.0)
    assert ev.tax == pytest.approx(23.0)
    assert ev.net_amount == pytest.approx(9_962.0)
    # 호환 키 sell_amount도 그대로 유지
    assert ev.sell_amount == pytest.approx(9_877.0)


def test_cash_events_persist_legacy_no_breakdown(db_session, user, strategy):
    """ExecutionModel 미주입(legacy) 경로의 cash_event는 분해 키가 없을 수 있음 —
    None 허용으로 안전 영속화.
    """
    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="cash-events-legacy",
        universe_config={"symbol": "X"},
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        initial_cash=1_000_000.0,
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
    )

    legacy_events = [
        {
            "date": date(2024, 1, 5),
            "event_type": "cash_shortage",
            "cash_before": 100.0,
            "required_cash": 5_000.0,
            "action": "partial_sell",
            "symbol": "BBB",
            "sell_quantity": 5,
            "sell_amount": 5_000.0,
            "cash_after": 5_100.0,
            "reason": "cash_shortage_partial_sell",
            # exec_price/raw_price/gross/fee/tax/net 키 없음 (legacy 경로)
        }
    ]
    backtest_service._persist_cash_events(db_session, run, legacy_events)
    db_session.commit()

    ev = db_session.query(CashEvent).filter_by(run_id=run.id).one()
    assert ev.fee is None
    assert ev.tax is None
    assert ev.gross_amount is None
    assert ev.net_amount is None
    assert ev.exec_price is None
    assert ev.raw_price is None
    # 호환 키는 채워짐
    assert ev.sell_amount == pytest.approx(5_000.0)


def test_golden_fixture_regression_cost_zero(db_session, user, strategy):
    """Phase 1 골든 fixture 지표가 014/015 변경 후에도 동일.

    fee=0/tax=0/slippage=0 default로 실행 시 final_equity / total_return / mdd /
    trade_count / win_rate / profit_factor가 frozen 값과 일치.

    015 (signal_date vs execution_date 분리): avg_holding_days만 7.5 → 6.5로 갱신.
    entry는 next_open(다음 거래일) 체결로 entry_date가 1일 미뤄지지만 intraday
    take/stop은 당일 체결이라 exit_date는 그대로 → 실제 보유일수 1일 단축이 정합.
    """
    df = _build_synthetic_series(seed=42, n=90)

    run = backtest_service.create_backtest_run(
        db_session,
        user_id=user.id,
        strategy_id=strategy.id,
        run_name="GOLDEN regression",
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

    # Phase 1 골든 frozen 9지표
    assert result.final_equity == pytest.approx(10_188_570.0, abs=1.0)
    assert result.total_return_pct == pytest.approx(1.8857, abs=0.001)
    assert result.mdd_pct == pytest.approx(-4.9032, abs=0.01)
    assert result.trade_count == 8
    assert result.win_rate == pytest.approx(37.5, abs=0.01)
    assert result.avg_holding_days == pytest.approx(6.5, abs=0.01)
    assert result.profit_factor == pytest.approx(1.2252, abs=0.001)

    # fee=tax=0이므로 모든 TradeExecution.fee=0, tax=0
    execs = db_session.query(TradeExecution).filter_by(run_id=run.id).all()
    for ex in execs:
        assert ex.fee == 0.0
        assert ex.tax == 0.0
        # gross == net (비용 0)
        assert ex.gross_amount == pytest.approx(ex.net_amount, abs=1e-9)

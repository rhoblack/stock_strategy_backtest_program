"""Backtest API (10번 문서 4절).

dev 모드는 단순 BackgroundTasks로 비동기 실행 (시연/소형용).
운영 시 Celery/RQ/arq 등 작업 큐로 교체.

user_id 스코프 (10번 9절): 모든 단일 자원 엔드포인트가 user_id를 받고
서비스 레이어에서 BacktestRun.user_id == user_id를 강제한다. 미소유
시 BACKTEST_RUN_NOT_FOUND.

에러는 AppError raise → errors.py handler가 표준 envelope으로 변환.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_db_session
from app.core.exceptions import (
    BacktestNotRunningError,
    BacktestRunNotFoundError,
    InvalidParameterValueError,
)
from app.db.session import make_session_factory
from app.main_state import get_engine
from app.models.backtest import BacktestRun, BacktestStatus
from app.models.cash_event import CashEvent
from app.models.daily_equity import DailyEquity
from app.models.trade import TradeExecution, TradeGroup
from app.schemas.backtest import BacktestCreate, BacktestRunOut, BacktestSummaryOut
from app.services import backtest_service

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


def _run_in_background(run_id: int) -> None:
    """BackgroundTask용 — 자체 DB session으로 실행."""
    import contextlib

    SessionLocal = make_session_factory(get_engine())
    with SessionLocal() as session, contextlib.suppress(Exception):
        # 서비스가 status=FAILED + error_message로 저장 후 재발생 — 백그라운드는 swallow
        backtest_service.run_backtest(session, run_id, df=None)


@router.post(
    "",
    response_model=BacktestRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="백테스트 실행 (비동기)",
)
def create_backtest(
    payload: BacktestCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    run = backtest_service.create_backtest_run(
        session,
        user_id=user_id,
        strategy_id=payload.strategy_id,
        run_name=payload.run_name,
        universe_config=payload.universe_config,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_cash=payload.initial_cash,
        fee_rate=payload.fee_rate,
        tax_rate=payload.tax_rate,
        slippage=payload.slippage,
        execution_price_type=payload.execution_price_type,
        use_adjusted_price=payload.use_adjusted_price,
        tick_rounding=payload.tick_rounding,
        priority_method=payload.priority_method,
        priority_tie_breaker=payload.priority_tie_breaker,
        random_seed=payload.random_seed,
    )

    background.add_task(_run_in_background, run.id)
    return run


def _get_run_or_raise(
    session: Session, run_id: int, *, user_id: int
) -> BacktestRun:
    """user_id 스코프 강제 — 미소유 또는 미존재 모두 NOT_FOUND."""
    run = session.get(BacktestRun, run_id)
    if run is None or run.user_id != user_id:
        raise BacktestRunNotFoundError(f"BacktestRun id={run_id} 없음")
    return run


@router.get("/{run_id}/status", response_model=BacktestRunOut, summary="실행 상태")
def get_status(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    return _get_run_or_raise(session, run_id, user_id=user_id)


@router.get(
    "/{run_id}/summary",
    response_model=BacktestSummaryOut,
    summary="요약 결과",
)
def get_summary(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    return backtest_service.get_backtest_summary(session, run_id, user_id=user_id)


@router.get("/{run_id}/trades", summary="거래 내역 (trade_groups)")
def list_trades(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    _get_run_or_raise(session, run_id, user_id=user_id)
    rows = (
        session.query(TradeGroup)
        .filter_by(run_id=run_id)
        .order_by(TradeGroup.entry_date)
        .all()
    )
    items = []
    for tg in rows:
        execs = (
            session.query(TradeExecution)
            .filter_by(trade_group_id=tg.id)
            .order_by(TradeExecution.execution_date)
            .all()
        )
        items.append(
            {
                "trade_group_id": tg.id,
                "symbol": tg.symbol,
                "name": tg.name,
                "entry_date": tg.entry_date.isoformat(),
                "entry_price": tg.entry_price,
                "entry_quantity": tg.entry_quantity,
                "remaining_quantity": tg.remaining_quantity,
                "fully_closed_at": tg.fully_closed_at.isoformat() if tg.fully_closed_at else None,
                "final_profit": tg.final_profit,
                "final_profit_rate": tg.final_profit_rate,
                "executions": [
                    {
                        "execution_date": ex.execution_date.isoformat(),
                        "execution_type": ex.execution_type.value,
                        "price": ex.price,
                        "quantity": ex.quantity,
                        "realized_profit": ex.realized_profit,
                        "exit_reason": ex.exit_reason,
                    }
                    for ex in execs
                ],
            }
        )
    return {"items": items, "total_count": len(items)}


@router.get("/{run_id}/chart-data", summary="차트 데이터 (candles + markers + equity)")
def get_chart_data(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    """단일 종목 백테스트 결과 차트 데이터 (08번 16절).

    dev 모드: synthetic_seed/synthetic_n으로 candles 재생성.
    Phase 14 PriceLoader 도입 시 daily_prices에서 직접 조회로 교체.
    """
    run = _get_run_or_raise(session, run_id, user_id=user_id)

    cfg = run.universe_config_json or {}
    seed = int(cfg.get("synthetic_seed", 42))
    n = int(cfg.get("synthetic_n", 90))

    from app.services.synthetic_data import build_synthetic_series

    df = build_synthetic_series(seed=seed, n=n, base_date=run.start_date)
    candles = [
        {
            "time": row["date"].isoformat(),
            "open": float(row["adj_open"]),
            "high": float(row["adj_high"]),
            "low": float(row["adj_low"]),
            "close": float(row["adj_close"]),
        }
        for _, row in df.iterrows()
    ]

    executions = (
        session.query(TradeExecution)
        .filter_by(run_id=run_id)
        .order_by(TradeExecution.execution_date)
        .all()
    )
    markers = [
        {
            "time": ex.execution_date.isoformat(),
            "type": ex.execution_type.value,
            "price": ex.price,
            "quantity": ex.quantity,
            "exit_reason": ex.exit_reason,
        }
        for ex in executions
    ]

    equity_rows = (
        session.query(DailyEquity)
        .filter_by(run_id=run_id)
        .order_by(DailyEquity.date)
        .all()
    )
    equity_curve = [
        {"time": eq.date.isoformat(), "value": eq.total_equity, "drawdown": eq.drawdown}
        for eq in equity_rows
    ]

    return {
        "candles": candles,
        "markers": markers,
        "equity_curve": equity_curve,
    }


@router.get("/{run_id}/daily-equity", summary="일별 자산")
def list_daily_equity(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    _get_run_or_raise(session, run_id, user_id=user_id)
    rows = (
        session.query(DailyEquity)
        .filter_by(run_id=run_id)
        .order_by(DailyEquity.date)
        .all()
    )
    return {
        "items": [
            {
                "date": eq.date.isoformat(),
                "cash": eq.cash,
                "stock_value": eq.stock_value,
                "total_equity": eq.total_equity,
                "drawdown": eq.drawdown,
                "positions_count": eq.positions_count,
            }
            for eq in rows
        ],
        "total_count": len(rows),
    }


@router.get("/{run_id}/cash-events", summary="예수금 이벤트")
def list_cash_events(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    _get_run_or_raise(session, run_id, user_id=user_id)
    rows = (
        session.query(CashEvent)
        .filter_by(run_id=run_id)
        .order_by(CashEvent.date)
        .all()
    )
    return {
        "items": [
            {
                "date": ev.date.isoformat(),
                "event_type": ev.event_type,
                "cash_before": ev.cash_before,
                "required_cash": ev.required_cash,
                "cash_after": ev.cash_after,
                "action": ev.action,
                "symbol": ev.symbol,
                "sell_quantity": ev.sell_quantity,
                "sell_amount": ev.sell_amount,
                "reason": ev.reason,
            }
            for ev in rows
        ],
        "total_count": len(rows),
    }


@router.get("/{run_id}/export/{kind}", summary="CSV/ZIP Export (09번 문서)")
def export(
    run_id: int,
    kind: str,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    """kind: summary | trades | daily-equity | cash-events | strategy | zip."""
    from fastapi.responses import Response

    from app.services import csv_exporter

    run = _get_run_or_raise(session, run_id, user_id=user_id)

    csv_kinds = {
        "summary": ("summary.csv", csv_exporter.export_summary_csv),
        "trades": ("trades.csv", csv_exporter.export_trades_csv),
        "daily-equity": ("daily_equity.csv", csv_exporter.export_daily_equity_csv),
        "cash-events": ("cash_events.csv", csv_exporter.export_cash_events_csv),
    }
    if kind in csv_kinds:
        filename, fn = csv_kinds[kind]
        content = fn(session, run)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if kind == "strategy":
        content = csv_exporter.export_strategy_snapshot_json(run)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="strategy_snapshot.json"'
            },
        )
    if kind == "zip":
        content_bytes = csv_exporter.export_zip(session, run)
        filename = f"backtest_run_{run.id}.zip"
        return Response(
            content=content_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise InvalidParameterValueError(
        f"export kind이 올바르지 않습니다: {kind!r}",
        details=[
            {
                "field": "kind",
                "message": "허용: summary, trades, daily-equity, cash-events, strategy, zip",
            }
        ],
    )


@router.post("/{run_id}/cancel", response_model=BacktestRunOut, summary="실행 취소")
def cancel(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    run = _get_run_or_raise(session, run_id, user_id=user_id)
    if run.status not in (BacktestStatus.PENDING, BacktestStatus.RUNNING):
        # handler가 BACKTEST_NOT_RUNNING(409)으로 변환
        raise BacktestNotRunningError(
            f"이미 종료된 실행입니다 (status={run.status.value}).",
            details=[{"field": "status", "message": run.status.value}],
        )
    run.status = BacktestStatus.CANCELLED
    session.commit()
    return run

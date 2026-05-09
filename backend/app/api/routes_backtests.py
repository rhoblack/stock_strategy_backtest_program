"""Backtest API (10번 문서 4절).

dev 모드는 단순 BackgroundTasks로 비동기 실행 (시연/소형용).
운영 시 Celery/RQ/arq 등 작업 큐로 교체.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_db_session
from app.core.exceptions import BacktestRunNotFoundError, StrategyNotFoundError
from app.db.session import make_session_factory
from app.main_state import get_engine
from app.models.backtest import BacktestRun, BacktestStatus
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
    try:
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
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()["error"]) from exc

    background.add_task(_run_in_background, run.id)
    return run


@router.get("/{run_id}/status", response_model=BacktestRunOut, summary="실행 상태")
def get_status(run_id: int, session: Session = Depends(get_db_session)):
    run = session.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "BACKTEST_RUN_NOT_FOUND"})
    return run


@router.get(
    "/{run_id}/summary",
    response_model=BacktestSummaryOut,
    summary="요약 결과",
)
def get_summary(run_id: int, session: Session = Depends(get_db_session)):
    try:
        return backtest_service.get_backtest_summary(session, run_id)
    except BacktestRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()["error"]) from exc


@router.get("/{run_id}/trades", summary="거래 내역 (trade_groups)")
def list_trades(run_id: int, session: Session = Depends(get_db_session)):
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


@router.get("/{run_id}/daily-equity", summary="일별 자산")
def list_daily_equity(run_id: int, session: Session = Depends(get_db_session)):
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


@router.post("/{run_id}/cancel", response_model=BacktestRunOut, summary="실행 취소")
def cancel(run_id: int, session: Session = Depends(get_db_session)):
    run = session.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "BACKTEST_RUN_NOT_FOUND"})
    if run.status not in (BacktestStatus.PENDING, BacktestStatus.RUNNING):
        raise HTTPException(
            status_code=409,
            detail={"code": "BACKTEST_NOT_RUNNING", "status": run.status.value},
        )
    run.status = BacktestStatus.CANCELLED
    session.commit()
    return run

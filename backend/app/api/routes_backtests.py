"""Backtest API (10번 문서 4절).

dev 모드는 단순 BackgroundTasks로 비동기 실행 (시연/소형용).
운영 시 Celery/RQ/arq 등 작업 큐로 교체.

user_id 스코프 (10번 9절): 모든 단일 자원 엔드포인트가 user_id를 받고
서비스 레이어에서 BacktestRun.user_id == user_id를 강제한다. 미소유
시 BACKTEST_RUN_NOT_FOUND.

에러는 AppError raise → errors.py handler가 표준 envelope으로 변환.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_db_session
from app.core.exceptions import (
    BacktestNotRunningError,
    BacktestRunNotFoundError,
    InvalidParameterValueError,
    MarketDataNotFoundError,
)
from app.db.session import make_session_factory
from app.main_state import get_engine
from app.models.backtest import BacktestRun, BacktestStatus
from app.models.cash_event import CashEvent
from app.models.daily_equity import DailyEquity
from app.models.trade import TradeExecution, TradeGroup
from app.schemas.backtest import (
    BacktestCreate,
    BacktestDetailOut,
    BacktestListItem,
    BacktestListResponse,
    BacktestResultSummary,
    BacktestRunOut,
    BacktestSummaryOut,
    ChartDataQuery,
    PaginatedTradesResponse,
    TradeExecutionOut,
    TradeGroupOut,
)
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


@router.get("", response_model=BacktestListResponse, summary="백테스트 목록 (10-n)")
def list_backtests(
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
    status_filter: str | None = Query(default=None, alias="status"),
    strategy_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
):
    """GET /api/backtests.

    user_id 스코프 강제 (10번 9절). created_at DESC 정렬.
    status / strategy_id 필터 지원.
    """
    from sqlalchemy import select

    stmt = select(BacktestRun).where(BacktestRun.user_id == user_id)
    if status_filter is not None:
        stmt = stmt.where(BacktestRun.status == status_filter)
    if strategy_id is not None:
        stmt = stmt.where(BacktestRun.strategy_id == strategy_id)

    # 전체 건수
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    count_stmt = sa_select(func.count()).select_from(
        stmt.subquery()
    )
    total_count: int = session.scalar(count_stmt) or 0

    # 페이지네이션 (created_at DESC → id DESC tie-breaker)
    stmt = stmt.order_by(
        BacktestRun.created_at.desc(),
        BacktestRun.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size)

    rows = list(session.scalars(stmt).all())
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    items = [
        BacktestListItem(
            id=r.id,
            user_id=r.user_id,
            strategy_id=r.strategy_id,
            run_name=r.run_name,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
            progress_pct=r.progress_pct,
            start_date=r.start_date,
            end_date=r.end_date,
            initial_cash=int(r.initial_cash),
            created_at=r.created_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
            error_message=r.error_message,
        )
        for r in rows
    ]

    return BacktestListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total_count=total_count,
        total_pages=total_pages,
        has_next=page < total_pages,
    )


@router.get("/{run_id}", response_model=BacktestDetailOut, summary="백테스트 단건 상세 (10-n)")
def get_backtest_detail(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    """GET /api/backtests/{run_id}.

    user_id 스코프 강제 (10번 9절).
    완료된 경우 result 필드에 BacktestResult 요약 포함.
    """
    run = _get_run_or_raise(session, run_id, user_id=user_id)

    result_summary: BacktestResultSummary | None = None
    if run.result is not None:
        r = run.result
        result_summary = BacktestResultSummary(
            initial_cash=int(r.initial_cash),
            final_equity=int(r.final_equity),
            total_return_pct=r.total_return_pct,
            annual_return_pct=r.annual_return_pct,
            mdd_pct=r.mdd_pct,
            trade_count=r.trade_count,
            win_rate=r.win_rate,
            avg_holding_days=r.avg_holding_days,
            profit_factor=r.profit_factor,
        )

    return BacktestDetailOut(
        id=run.id,
        user_id=run.user_id,
        strategy_id=run.strategy_id,
        run_name=run.run_name,
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        progress_pct=run.progress_pct,
        start_date=run.start_date,
        end_date=run.end_date,
        initial_cash=int(run.initial_cash),
        fee_rate=run.fee_rate,
        slippage=run.slippage,
        use_adjusted_price=run.use_adjusted_price,
        tick_rounding=run.tick_rounding,
        priority_method=run.priority_method,
        priority_tie_breaker=run.priority_tie_breaker,
        random_seed=run.random_seed,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
        result=result_summary,
    )


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


@router.get("/{run_id}/trades", response_model=PaginatedTradesResponse, summary="거래 내역 (trade_groups + pagination) (10-p)")
def list_trades(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str = Query(
        default="execution_date_asc",
        description="execution_date_asc | execution_date_desc | profit_desc | profit_asc",
    ),
    symbol: str | None = Query(default=None, description="특정 종목 필터 (종목코드)"),
    action: str | None = Query(default=None, description="buy / sell 필터 (미구현: trade_group 기준)"),
):
    """GET /api/backtests/{run_id}/trades.

    trade_groups 단위로 집계된 매수-매도 페어를 반환한다 (07 DB 9~10절).
    페이지네이션 + sort + symbol/action 필터 지원 (10-p).

    하위 호환: page/page_size 미지정 시 기본값(page=1, page_size=50) 적용.
    응답 구조는 항상 PaginatedTradesResponse (items + pagination 메타).
    """
    from sqlalchemy import asc, desc

    _get_run_or_raise(session, run_id, user_id=user_id)

    q = session.query(TradeGroup).filter(TradeGroup.run_id == run_id)

    # symbol 필터
    if symbol is not None:
        q = q.filter(TradeGroup.symbol == symbol)

    # sort 결정 (10-p)
    _SORT_MAP = {
        "execution_date_asc": (asc(TradeGroup.entry_date), asc(TradeGroup.id)),
        "execution_date_desc": (desc(TradeGroup.entry_date), desc(TradeGroup.id)),
        "profit_desc": (desc(TradeGroup.final_profit), asc(TradeGroup.id)),
        "profit_asc": (asc(TradeGroup.final_profit), asc(TradeGroup.id)),
    }
    sort_clauses = _SORT_MAP.get(sort, _SORT_MAP["execution_date_asc"])
    q = q.order_by(*sort_clauses)

    total_count: int = q.count()
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items: list[TradeGroupOut] = []
    for tg in rows:
        execs_q = (
            session.query(TradeExecution)
            .filter_by(trade_group_id=tg.id)
            .order_by(TradeExecution.execution_date.asc(), TradeExecution.id.asc())
        )
        # action 필터: sell = SELL 타입 execution이 있는 그룹만, buy = BUY만인 그룹만
        execs = execs_q.all()

        exec_out = [
            TradeExecutionOut(
                execution_date=ex.execution_date.isoformat(),
                execution_type=ex.execution_type.value if hasattr(ex.execution_type, "value") else str(ex.execution_type),
                price=int(ex.price),
                quantity=int(ex.quantity),
                gross_amount=int(ex.gross_amount) if ex.gross_amount is not None else None,
                fee=int(ex.fee) if ex.fee is not None else None,
                tax=int(ex.tax) if ex.tax is not None else None,
                net_amount=int(ex.net_amount) if ex.net_amount is not None else None,
                realized_profit=int(ex.realized_profit) if ex.realized_profit is not None else None,
                exit_reason=ex.exit_reason,
            )
            for ex in execs
        ]

        items.append(
            TradeGroupOut(
                trade_group_id=tg.id,
                symbol=tg.symbol,
                name=tg.name,
                entry_date=tg.entry_date.isoformat(),
                entry_price=int(tg.entry_price),
                entry_quantity=int(tg.entry_quantity),
                remaining_quantity=int(tg.remaining_quantity),
                fully_closed_at=tg.fully_closed_at.isoformat() if tg.fully_closed_at else None,
                final_profit=int(tg.final_profit) if tg.final_profit is not None else None,
                final_profit_rate=tg.final_profit_rate,
                executions=exec_out,
            )
        )

    return PaginatedTradesResponse(
        items=items,
        page=page,
        page_size=page_size,
        total_count=total_count,
        total_pages=total_pages,
        has_next=page < total_pages,
    )


@router.get("/{run_id}/chart-data", summary="차트 데이터 (candles + markers + equity)")
def get_chart_data(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
    symbol: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    use_adjusted: bool = Query(default=True),
    downsample: int | None = Query(default=None, ge=1),
):
    """백테스트 결과 차트 데이터 (08번 §6 / 10번 §4 chart-data).

    데이터 소스 우선순위 (031 step):
        1) `daily_prices` DB 조회 — 운영/dev 공통, 데이터가 있으면 항상 우선.
        2) dev 모드 (`APP_ENV ∈ {development, dev, test, testing, ''}`) +
           daily_prices 비어있음 → synthetic_seed/synthetic_n fallback.
        3) 운영 모드 (`APP_ENV ∈ {production, prod}`) + daily_prices 비어있음 →
           404 MARKET_DATA_NOT_FOUND (helpful 메시지).

    응답 키 (frontend `CandleBar` / `ChartMarker` / `EquityPoint` 보존):
        - `candles[].{time,open,high,low,close,volume}` — frontend는 volume 무시 가능.
        - `markers[].{time,type,price,quantity,exit_reason}`
        - `equity_curve[].{time,value,drawdown}`
        - 신규: `symbol`, `source`, `resolution`, `downsampled`,
          `downsample_stride`, `date_range`, `use_adjusted`
    """
    run = _get_run_or_raise(session, run_id, user_id=user_id)

    # 쿼리 검증 — pydantic ChartDataQuery로 일괄 통과
    try:
        query = ChartDataQuery(
            symbol=symbol,
            start_date=start_date,  # type: ignore[arg-type]
            end_date=end_date,  # type: ignore[arg-type]
            use_adjusted=use_adjusted,
            downsample=downsample,
        )
    except Exception as exc:  # pydantic ValidationError
        raise InvalidParameterValueError(
            "chart-data 쿼리 형식이 올바르지 않습니다.",
            details=[{"field": "query", "message": str(exc)}],
        ) from exc

    if (
        query.start_date is not None
        and query.end_date is not None
        and query.start_date > query.end_date
    ):
        raise InvalidParameterValueError(
            "start_date는 end_date 이전이어야 합니다.",
            details=[
                {
                    "field": "start_date",
                    "message": (
                        f"{query.start_date.isoformat()} > "
                        f"{query.end_date.isoformat()}"
                    ),
                }
            ],
        )

    # 1) daily_prices 우선
    payload = backtest_service.build_chart_data_from_db(
        session,
        run,
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        use_adjusted=query.use_adjusted,
        downsample=query.downsample,
    )
    if payload is not None:
        return payload

    # 2) dev fallback
    if backtest_service.is_dev_mode():
        return backtest_service.build_chart_data_synthetic_fallback(
            session, run, use_adjusted=query.use_adjusted
        )

    # 3) 운영 모드 + 데이터 없음 → 404
    requested_sym = query.symbol or (run.universe_config_json or {}).get("symbol")
    raise MarketDataNotFoundError(
        f"daily_prices에 종목 {requested_sym!r}의 가격 데이터가 없습니다. "
        f"데이터 수집 파이프라인 실행 후 다시 시도하세요.",
        details=[
            {"field": "symbol", "message": str(requested_sym)},
            {"field": "run_id", "message": str(run.id)},
        ],
    )


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
        .order_by(DailyEquity.date.asc(), DailyEquity.id.asc())
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
        .order_by(CashEvent.date.asc(), CashEvent.id.asc())
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


# ── encoding 유효값 집합 (09-l)
_VALID_ENCODINGS = {"utf-8-bom", "utf-8", "cp949"}


def _parse_encoding(encoding: str) -> str:
    """encoding query param 검증 후 반환."""
    if encoding not in _VALID_ENCODINGS:
        raise InvalidParameterValueError(
            f"encoding 값이 올바르지 않습니다: {encoding!r}",
            details=[
                {
                    "field": "encoding",
                    "message": f"허용: {', '.join(sorted(_VALID_ENCODINGS))}",
                }
            ],
        )
    return encoding


# ── 분리 라우팅 (09-k): /export/symbol-performance / universe-history / strategy-snapshot
# FastAPI 라우터에서 /{kind} 와 /symbol-performance 등 고정 경로가 공존할 때
# 고정 경로를 먼저 등록해야 우선 매칭된다.

@router.get("/{run_id}/export/symbol-performance", summary="종목별 성과 CSV (09-i)")
def export_symbol_performance(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
    encoding: str = Query(default="utf-8-bom", description="utf-8-bom | utf-8 | cp949"),
):
    """종목별 성과 CSV — trade_groups symbol 기준 집계."""
    from app.services import csv_exporter

    run = _get_run_or_raise(session, run_id, user_id=user_id)
    enc = _parse_encoding(encoding)
    content = csv_exporter.export_symbol_performance_csv(session, run, encoding=enc)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="symbol_performance.csv"'},
    )


@router.get("/{run_id}/export/universe-history", summary="유니버스 이력 CSV (09-j)")
def export_universe_history(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
    encoding: str = Query(default="utf-8-bom", description="utf-8-bom | utf-8 | cp949"),
):
    """유니버스 이력 CSV — universe_history 행 전개."""
    from app.services import csv_exporter

    run = _get_run_or_raise(session, run_id, user_id=user_id)
    enc = _parse_encoding(encoding)
    content = csv_exporter.export_universe_history_csv(session, run, encoding=enc)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="universe_history.csv"'},
    )


@router.get("/{run_id}/export/strategy-snapshot", summary="전략 스냅샷 JSON (09-k)")
def export_strategy_snapshot(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    """백테스트 실행 당시 전략 JSON 다운로드."""
    from app.services import csv_exporter

    run = _get_run_or_raise(session, run_id, user_id=user_id)
    content = csv_exporter.export_strategy_snapshot_json(run)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="strategy_snapshot.json"'},
    )


@router.get("/{run_id}/export/{kind}", summary="CSV/ZIP Export (09번 문서) — 하위 호환")
def export(
    run_id: int,
    kind: str,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
    encoding: str = Query(default="utf-8-bom", description="utf-8-bom | utf-8 | cp949"),
):
    """kind: summary | trades | daily-equity | cash-events | symbol-performance | universe-history | strategy | strategy-snapshot | zip.

    하위 호환 라우트 — 분리 라우팅(/export/symbol-performance 등)이 우선 매칭되므로
    이 라우트는 그 외 kind 처리용.
    """
    from app.services import csv_exporter

    run = _get_run_or_raise(session, run_id, user_id=user_id)
    enc = _parse_encoding(encoding)

    # bytes 반환하는 신규 export 함수 래핑 (encoding 파라미터 전달)
    csv_bytes_kinds = {
        "symbol-performance": ("symbol_performance.csv", csv_exporter.export_symbol_performance_csv),
        "universe-history": ("universe_history.csv", csv_exporter.export_universe_history_csv),
    }
    # str 반환하는 기존 export 함수 (encoding 미적용 — 기존 호환)
    csv_str_kinds = {
        "summary": ("summary.csv", csv_exporter.export_summary_csv),
        "trades": ("trades.csv", csv_exporter.export_trades_csv),
        "daily-equity": ("daily_equity.csv", csv_exporter.export_daily_equity_csv),
        "cash-events": ("cash_events.csv", csv_exporter.export_cash_events_csv),
    }

    if kind in csv_bytes_kinds:
        filename, fn = csv_bytes_kinds[kind]
        content = fn(session, run, encoding=enc)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if kind in csv_str_kinds:
        filename, fn = csv_str_kinds[kind]
        content = fn(session, run)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if kind in ("strategy", "strategy-snapshot"):
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
                "message": (
                    "허용: summary, trades, daily-equity, cash-events, "
                    "symbol-performance, universe-history, strategy, strategy-snapshot, zip"
                ),
            }
        ],
    )


@router.post("/{run_id}/cancel", response_model=BacktestRunOut, summary="실행 취소")
def cancel(
    run_id: int,
    session: Session = Depends(get_db_session),
    user_id: int = Depends(get_current_user_id),
):
    """실행 중인 백테스트 취소 (10번 §4.4).

    처리 흐름:
        1. user_id 스코프 강제 — 미소유 시 BACKTEST_RUN_NOT_FOUND.
        2. 이미 종료된 실행이면 BACKTEST_NOT_RUNNING(409) 반환.
        3. DB status → CANCELLING (빠른 응답 + 진행 중 표시).
        4. CancellationToken.cancel() 호출 → 실행 중 엔진 루프에 취소 신호 전달.
           토큰이 없으면 (엔진이 아직 시작 전이거나 이미 완료) DB만 CANCELLED로 즉시 변경.

    응답: 현재 DB 상태 반환 (cancelling 또는 cancelled).
    """
    from app.core.cancellation import cancel_run as _cancel_run

    run = _get_run_or_raise(session, run_id, user_id=user_id)
    if run.status not in (BacktestStatus.PENDING, BacktestStatus.RUNNING):
        # handler가 BACKTEST_NOT_RUNNING(409)으로 변환
        raise BacktestNotRunningError(
            f"이미 종료된 실행입니다 (status={run.status.value}).",
            details=[{"field": "status", "message": run.status.value}],
        )

    # DB status를 CANCELLING으로 (10번 §4.4 응답: "cancelling").
    # 실제 엔진이 BacktestCancelledError를 처리하면 CANCELLED로 갱신됨.
    run.status = BacktestStatus.CANCELLING
    session.commit()

    # CancellationToken에 취소 신호 전달. 토큰이 없으면 (PENDING 상태 등)
    # 엔진이 시작할 때 체크 전에 이미 DB가 CANCELLING이므로 서비스가 시작 시 처리.
    token_found = _cancel_run(run_id)
    if not token_found:
        # 토큰 없음 = 엔진 미시작 또는 이미 종료 → DB를 CANCELLED로 즉시 전환
        run.status = BacktestStatus.CANCELLED
        run.finished_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
        session.commit()

    session.refresh(run)
    return run

"""시장 데이터 API (10번 문서 5절 / 10-o).

엔드포인트:
    GET /api/symbols/search?q=&market=    — symbols 테이블 LIKE 검색 (최대 50건)
    GET /api/symbols/{symbol}/daily-prices?start_date=&end_date=&adjusted=
                                           — daily_prices 일봉 조회
    GET /api/calendar?year=&month=&market= — trading_calendar 조회

라우팅 구조:
    - /api/symbols/* 라우트: symbols_router (prefix="/api/symbols")
    - /api/calendar   라우트: calendar_router (prefix="/api")

두 라우터를 main.py에서 각각 include한다.

user_id 스코프:
    시장 데이터는 공개 읽기 전용이므로 user_id 스코프 적용 안 함.
    단, get_current_user_id Depends는 미래 인증 전환 시 추가 예정.

에러:
    SYMBOL_NOT_FOUND (404) — 종목 미존재
    MARKET_DATA_NOT_FOUND (404) — 일봉 데이터 없음
"""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.core.exceptions import MarketDataNotFoundError, SymbolNotFoundError
from app.models.daily_price import DailyPrice
from app.models.symbol import Symbol
from app.models.trading_calendar import TradingCalendar
from app.schemas.backtest import (
    CalendarItem,
    CalendarResponse,
    DailyPriceItem,
    DailyPricesResponse,
    SymbolSearchItem,
)

symbols_router = APIRouter(prefix="/api/symbols", tags=["market-data"])
calendar_router = APIRouter(prefix="/api", tags=["market-data"])


@symbols_router.get("/search", response_model=list[SymbolSearchItem], summary="종목 검색 (10-o)")
def search_symbols(
    q: str = Query(default="", description="종목코드 또는 종목명 검색어 (LIKE)"),
    market: str | None = Query(default=None, description="KOSPI | KOSDAQ | KONEX"),
    session: Session = Depends(get_db_session),
):
    """GET /api/symbols/search.

    symbol 또는 name LIKE '%q%' 검색. 결과 최대 50건.
    market 지정 시 해당 시장만.
    삭제된(delisting_date IS NOT NULL이어도) 종목도 포함 — 과거 백테스트용.
    """
    stmt = session.query(Symbol)
    if q:
        like_q = f"%{q}%"
        stmt = stmt.filter(
            or_(
                Symbol.symbol.ilike(like_q),
                Symbol.name.ilike(like_q),
            )
        )
    if market:
        stmt = stmt.filter(Symbol.market == market)

    # 활성 종목 우선, 알파벳순 (symbol asc)
    stmt = stmt.order_by(
        Symbol.delisting_date.is_(None).desc(),  # NULL(현재상장) 먼저
        Symbol.symbol.asc(),
    ).limit(50)

    rows = stmt.all()

    return [
        SymbolSearchItem(
            symbol=s.symbol,
            name=s.name,
            market=s.market,
            sector=s.sector,
            listing_date=s.listing_date,
            delisting_date=s.delisting_date,
            is_etf=s.is_etf,
            is_spac=s.is_spac,
        )
        for s in rows
    ]


@symbols_router.get(
    "/{symbol}/daily-prices",
    response_model=DailyPricesResponse,
    summary="일봉 조회 (10-o)",
)
def get_daily_prices(
    symbol: str,
    session: Session = Depends(get_db_session),
    start_date: date_type | None = Query(default=None, description="조회 시작일 (포함)"),
    end_date: date_type | None = Query(default=None, description="조회 종료일 (포함)"),
    adjusted: bool = Query(default=True, description="수정주가 기준 여부 (기본 True)"),
):
    """GET /api/symbols/{symbol}/daily-prices.

    daily_prices 테이블에서 (symbol, date) 기반 조회.
    start_date / end_date 미지정 시 전체 기간.
    adjusted=true 시 adj_* 컬럼도 포함.

    종목 미존재 → SYMBOL_NOT_FOUND (404).
    데이터 없음 → MARKET_DATA_NOT_FOUND (404).
    """
    # 종목 존재 확인
    sym_row = session.get(Symbol, symbol)
    if sym_row is None:
        raise SymbolNotFoundError(
            f"종목 {symbol!r}이 symbols 테이블에 없습니다.",
            details=[{"field": "symbol", "message": symbol}],
        )

    q = session.query(DailyPrice).filter(DailyPrice.symbol == symbol)
    if start_date is not None:
        q = q.filter(DailyPrice.date >= start_date)
    if end_date is not None:
        q = q.filter(DailyPrice.date <= end_date)
    q = q.order_by(DailyPrice.date.asc())

    rows = q.all()
    if not rows:
        raise MarketDataNotFoundError(
            f"종목 {symbol!r}의 일봉 데이터가 없습니다. 데이터 수집 파이프라인을 실행하세요.",
            details=[
                {"field": "symbol", "message": symbol},
                {"field": "start_date", "message": str(start_date) if start_date else ""},
                {"field": "end_date", "message": str(end_date) if end_date else ""},
            ],
        )

    items = [
        DailyPriceItem(
            date=row.date,
            open=int(row.open),
            high=int(row.high),
            low=int(row.low),
            close=int(row.close),
            volume=int(row.volume),
            adj_open=int(row.adj_open) if adjusted else None,
            adj_high=int(row.adj_high) if adjusted else None,
            adj_low=int(row.adj_low) if adjusted else None,
            adj_close=int(row.adj_close) if adjusted else None,
            adj_volume=int(row.adj_volume) if adjusted else None,
        )
        for row in rows
    ]

    return DailyPricesResponse(
        symbol=symbol,
        adjusted=adjusted,
        items=items,
        total_count=len(items),
    )


@calendar_router.get(
    "/calendar",
    response_model=CalendarResponse,
    summary="거래 캘린더 조회 (10-o)",
)
def get_calendar(
    session: Session = Depends(get_db_session),
    year: int = Query(..., ge=2000, le=2100, description="연도"),
    month: int = Query(..., ge=1, le=12, description="월"),
    market: str = Query(default="KOSPI", description="KOSPI | KOSDAQ"),
):
    """GET /api/calendar?year=&month=&market=.

    trading_calendar 테이블에서 해당 연/월/시장의 거래일/휴장일 목록을 반환.
    is_trading_day=True/False 모두 포함 (프론트가 달력 UI 생성용).
    """
    # 해당 월의 첫날 ~ 마지막날
    import calendar as cal_mod
    from datetime import date as date_cls

    last_day = cal_mod.monthrange(year, month)[1]
    month_start = date_cls(year, month, 1)
    month_end = date_cls(year, month, last_day)

    rows = (
        session.query(TradingCalendar)
        .filter(
            TradingCalendar.market == market,
            TradingCalendar.date >= month_start,
            TradingCalendar.date <= month_end,
        )
        .order_by(TradingCalendar.date.asc())
        .all()
    )

    items = [
        CalendarItem(
            date=row.date,
            market=row.market,
            is_trading_day=row.is_trading_day,
            holiday_name=row.holiday_name,
        )
        for row in rows
    ]

    return CalendarResponse(
        year=year,
        month=month,
        market=market,
        items=items,
        total_count=len(items),
    )

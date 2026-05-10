"""Backtest API Pydantic 스키마."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── 페이지네이션 표준 (10번 10절)

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_count: int
    total_pages: int
    has_next: bool


class BacktestCreate(BaseModel):
    strategy_id: int
    run_name: str = ""
    universe_config: dict[str, Any] = Field(default_factory=dict)
    start_date: date_type
    end_date: date_type
    initial_cash: float = 10_000_000.0
    fee_rate: float = 0.00015
    tax_rate: Any = 0.0018  # float | list[{from, rate}]
    slippage: float = 0.001
    execution_price_type: str = "next_open"
    use_adjusted_price: bool = True
    tick_rounding: str = "buy_up_sell_down"
    priority_method: str = "trading_value_desc"
    priority_tie_breaker: str = "symbol_asc"
    random_seed: int | None = None


class BacktestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    strategy_id: int
    run_name: str
    status: str
    progress_pct: float
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BacktestSummaryOut(BaseModel):
    run_id: int
    status: str
    progress_pct: float
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    summary: dict | None


class ChartDataQuery(BaseModel):
    """GET /api/backtests/{run_id}/chart-data 쿼리 옵션 (10번 §4 chart-data).

    - `symbol`: 단일 종목 지정 (복수 종목 백테스트 시 어느 종목의 차트인지). 미지정 시
      `BacktestRun.universe_config_json["symbol"]`로 fallback (단일 종목 백테스트).
    - `start_date` / `end_date`: 차트 표시 구간. 미지정 시 BacktestRun 전체 기간.
      `BacktestRun.[start|end]_date`로 자동 클램프 (밖으로 나갈 수 없음).
    - `use_adjusted`: True 시 `adj_*` 가격, False 시 원 가격 (`open/high/low/close`).
      기본 True (13.7 정책 — 가격 조건/체결과 동일 컬럼).
    - `downsample`: 양의 정수면 stride 다운샘플링 (`df[::stride]`). 미지정 시 응답
      크기가 1MB(약 4000봉 이상) 초과하면 자동 stride 결정. `downsample=1`은
      "다운샘플링 안함" 강제.

    결정론 (CLAUDE.md #8):
        - daily_prices는 (date ASC) 정렬
        - trade_executions는 (execution_date ASC, id ASC) tie-breaker
        - downsample stride는 입력값에 결정적 (n // max_points 등)
    """

    symbol: str | None = None
    start_date: date_type | None = None
    end_date: date_type | None = None
    use_adjusted: bool = True
    downsample: int | None = None


# ── 백테스트 목록 / 상세 스키마 (10-n / 10번 §4)

class BacktestListItem(BaseModel):
    """GET /api/backtests 목록 단건."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    strategy_id: int
    run_name: str
    status: str
    progress_pct: float
    start_date: date_type
    end_date: date_type
    initial_cash: int  # KRW 정수 (13-s §14)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class BacktestResultSummary(BaseModel):
    """백테스트 결과 요약 (BacktestResult → inline embed)."""

    initial_cash: int
    final_equity: int
    total_return_pct: float
    annual_return_pct: float
    mdd_pct: float
    trade_count: int
    win_rate: float
    avg_holding_days: float
    profit_factor: float | None = None


class BacktestDetailOut(BaseModel):
    """GET /api/backtests/{id} 단건 상세."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    strategy_id: int
    run_name: str
    status: str
    progress_pct: float
    start_date: date_type
    end_date: date_type
    initial_cash: int
    fee_rate: float
    slippage: float
    use_adjusted_price: bool
    tick_rounding: str
    priority_method: str
    priority_tie_breaker: str
    random_seed: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    result: BacktestResultSummary | None = None  # 완료된 경우 포함


class BacktestListResponse(BaseModel):
    """GET /api/backtests 페이지네이션 응답."""

    items: list[BacktestListItem]
    page: int
    page_size: int
    total_count: int
    total_pages: int
    has_next: bool


# ── trades 페이지네이션 스키마 (10-p / 10번 §4 trades)

class TradeExecutionOut(BaseModel):
    """trade_execution 단건 출력."""

    execution_date: str
    execution_type: str
    price: int  # KRW 정수
    quantity: int
    gross_amount: int | None = None
    fee: int | None = None
    tax: int | None = None
    net_amount: int | None = None
    realized_profit: int | None = None  # KRW 정수
    exit_reason: str | None = None


class TradeGroupOut(BaseModel):
    """trade_group 단건 (executions 포함)."""

    trade_group_id: int
    symbol: str
    name: str | None = None
    entry_date: str
    entry_price: int  # KRW 정수
    entry_quantity: int
    remaining_quantity: int
    fully_closed_at: str | None = None
    final_profit: int | None = None  # KRW 정수
    final_profit_rate: float | None = None
    executions: list[TradeExecutionOut] = []


class PaginatedTradesResponse(BaseModel):
    """GET /api/backtests/{id}/trades 페이지네이션 응답 (10-p)."""

    items: list[TradeGroupOut]
    page: int
    page_size: int
    total_count: int
    total_pages: int
    has_next: bool


# ── 시장 데이터 스키마 (10-o / 10번 §5)

class SymbolSearchItem(BaseModel):
    """GET /api/symbols/search 결과 단건."""

    symbol: str
    name: str
    market: str
    sector: str | None = None
    listing_date: date_type
    delisting_date: date_type | None = None
    is_etf: bool
    is_spac: bool


class DailyPriceItem(BaseModel):
    """GET /api/symbols/{symbol}/daily-prices 결과 단건."""

    date: date_type
    open: int   # KRW 정수
    high: int
    low: int
    close: int
    volume: int
    adj_open: int | None = None
    adj_high: int | None = None
    adj_low: int | None = None
    adj_close: int | None = None
    adj_volume: int | None = None


class DailyPricesResponse(BaseModel):
    """GET /api/symbols/{symbol}/daily-prices 응답."""

    symbol: str
    adjusted: bool
    items: list[DailyPriceItem]
    total_count: int


class CalendarItem(BaseModel):
    """GET /api/calendar 결과 단건."""

    date: date_type
    market: str
    is_trading_day: bool
    holiday_name: str | None = None


class CalendarResponse(BaseModel):
    """GET /api/calendar 응답."""

    year: int
    month: int
    market: str
    items: list[CalendarItem]
    total_count: int

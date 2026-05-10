"""Backtest API Pydantic 스키마."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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

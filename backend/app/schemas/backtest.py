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

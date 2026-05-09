"""백테스트 실행 설정.

Phase 1 단일 종목 한정. universe / priority / cash_management는 후속 단계.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type


@dataclass(frozen=True)
class BacktestConfig:
    """단일 종목 백테스트 설정."""

    symbol: str
    start_date: date_type
    end_date: date_type
    position_size_amount: float  # fixed_amount: 종목당 매수 금액
    initial_cash: float

    market: str = "KOSPI"
    entry_price_type: str = "next_open"
    exit_price_type: str = "next_open"
    max_gap_pct_for_entry: float = 5.0  # 정확성 정책 13.4.1
    skip_no_volume: bool = True  # 정확성 정책 13.4.4

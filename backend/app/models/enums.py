"""DB enum 모음."""

from __future__ import annotations

from enum import StrEnum


class BacktestStatus(StrEnum):
    """백테스트 실행 상태 (07번 문서 7절)."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TradeExecutionType(StrEnum):
    """체결 종류 (07번 문서 10절)."""

    BUY = "BUY"
    SELL = "SELL"
    PARTIAL_SELL = "PARTIAL_SELL"

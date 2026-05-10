"""DB enum 모음."""

from __future__ import annotations

from enum import StrEnum


class BacktestStatus(StrEnum):
    """백테스트 실행 상태 (07번 문서 7절 + 10번 §4.4).

    cancelling: cancel 요청이 DB에 기록되었고 엔진 루프에 취소 신호를 전달한 상태.
                다음 날짜 루프에서 BacktestCancelledError가 발생하면 cancelled로 전이.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class TradeExecutionType(StrEnum):
    """체결 종류 (07번 문서 10절)."""

    BUY = "BUY"
    SELL = "SELL"
    PARTIAL_SELL = "PARTIAL_SELL"

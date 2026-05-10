"""CashEvent 모델 (07번 10절).

CashManager가 발동된 이벤트 기록 (예수금 부족 → 일부 매도 / 매수 실패).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.backtest import BacktestRun


class CashEvent(Base):
    __tablename__ = "cash_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # cash_shortage / partial_sell / buy_skipped_cash_shortage

    cash_before: Mapped[int] = mapped_column(Integer, nullable=False)         # KRW 정수 §14
    required_cash: Mapped[int | None] = mapped_column(Integer, nullable=True) # KRW 정수 §14
    cash_after: Mapped[int] = mapped_column(Integer, nullable=False)           # KRW 정수 §14

    action: Mapped[str | None] = mapped_column(String(50), nullable=True)  # partial_sell
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sell_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sell_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 호환: net_amount과 동일, KRW 정수

    # 강제 매도 비용 분해 (014 step / 리뷰 011 C2 영속화).
    # ExecutionModel을 거친 강제 매도는 fee/tax가 분해되어 들어옴 — 그대로 저장.
    # CashManager에 ExecutionModel이 주입되지 않은 dev/legacy 경로면 fee/tax=0, gross=net.
    exec_price: Mapped[int | None] = mapped_column(Integer, nullable=True)     # KRW 정수 §14
    raw_price: Mapped[float | None] = mapped_column(Float, nullable=True)      # 감사용, 소수 허용
    gross_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)   # KRW 정수 §14
    fee: Mapped[int | None] = mapped_column(Integer, nullable=True)            # KRW 정수 §14
    tax: Mapped[int | None] = mapped_column(Integer, nullable=True)            # KRW 정수 §14
    net_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)     # KRW 정수 §14

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[BacktestRun] = relationship()

    def __repr__(self) -> str:
        return (
            f"<CashEvent {self.event_type} {self.date} "
            f"{self.symbol or '-'} {self.cash_before:.0f}→{self.cash_after:.0f}>"
        )

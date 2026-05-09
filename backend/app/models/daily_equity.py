"""DailyEquity 모델 (07번 9절).

Phase 1의 backtest.result.DailyEquity dataclass를 영속화.
(run_id, date) 복합 인덱스로 한 백테스트의 시계열 조회를 빠르게.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.backtest import BacktestRun


class DailyEquity(Base):
    """일별 자산 스냅샷."""

    __tablename__ = "daily_equity"
    __table_args__ = (
        UniqueConstraint("run_id", "date", name="uq_daily_equity_run_date"),
        Index("ix_daily_equity_run_date", "run_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False
    )

    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    stock_value: Mapped[float] = mapped_column(Float, nullable=False)
    total_equity: Mapped[float] = mapped_column(Float, nullable=False)

    daily_return: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cumulative_return: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    drawdown: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    positions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[BacktestRun] = relationship()

    def __repr__(self) -> str:
        return (
            f"<DailyEquity run_id={self.run_id} {self.date} "
            f"equity={self.total_equity:.0f} drawdown={self.drawdown:.2f}%>"
        )

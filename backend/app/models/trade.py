"""TradeGroup + TradeExecution 모델.

설계서 07번 9~10절. Phase 1의 portfolio.position.TradeGroup / Portfolio.trade_logs를
영속화. 모델명 충돌을 피하기 위해 DB 모델은 TradeGroupRow / TradeExecutionRow가
아니라 같은 이름 TradeGroup / TradeExecution을 사용 (서로 다른 패키지).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TradeExecutionType

# 정확성 정책 §14: 모든 금액(KRW)은 정수. DB 컬럼 타입을 Integer로 유지.
# entry_price / realized_profit / final_profit 은 소수 원 단위가 없으므로
# 런타임에서는 int이지만, 외부 호환성을 위해 Float 컬럼을 유지하는 필드도 있다.
# 비율 필드(realized_profit_rate, final_profit_rate)는 float 유지.

if TYPE_CHECKING:
    from app.models.backtest import BacktestRun


class TradeGroup(Base):
    """매수 lot 1개 (DB 영속화 버전).

    Portfolio의 메모리 TradeGroup과 1:1로 매핑.
    부분 매도가 진행되어도 entry_price는 절대 변경 안 함 (정확성 정책 13.9.3).
    """

    __tablename__ = "trade_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), default="", nullable=False)

    entry_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    entry_price: Mapped[int] = mapped_column(Integer, nullable=False)  # KRW 정수 §14
    entry_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    fully_closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    final_profit: Mapped[int | None] = mapped_column(Integer, nullable=True)   # KRW 정수 §14
    final_profit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 비율 float

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 관계
    run: Mapped[BacktestRun] = relationship()
    executions: Mapped[list[TradeExecution]] = relationship(
        back_populates="trade_group",
        cascade="all, delete-orphan",
        order_by="TradeExecution.execution_date",
    )

    def __repr__(self) -> str:
        return (
            f"<TradeGroup id={self.id} {self.symbol} "
            f"entry={self.entry_price}@{self.entry_quantity} remain={self.remaining_quantity}>"
        )


class TradeExecution(Base):
    """매수/매도 1건의 체결 기록 (07번 10절).

    부분 매도 시 같은 trade_group에 여러 SELL/PARTIAL_SELL execution이 생성됨.
    """

    __tablename__ = "trade_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_group_id: Mapped[int] = mapped_column(
        ForeignKey("trade_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    execution_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    # 신호 발생일 (next_open 체결의 경우 execution_date보다 1 거래일 앞).
    # 갭/일중 stop·take/trailing/max_holding/cash_manager 강제 매도는 당일 체결이라
    # signal_date == execution_date. 마이그레이션 이전 기존 row와 호환을 위해 NULL 허용.
    # (017 step / CLAUDE.md look-ahead 체크리스트 + 13.15 정책)
    signal_date: Mapped[date_type | None] = mapped_column(
        Date, nullable=True, default=None
    )
    execution_type: Mapped[TradeExecutionType] = mapped_column(
        SAEnum(TradeExecutionType, native_enum=False, length=20), nullable=False
    )

    price: Mapped[int] = mapped_column(Integer, nullable=False)        # KRW 정수 §14
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # 비용 분해 — 모두 KRW 정수 (정확성 정책 §14)
    gross_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    fee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    net_amount: Mapped[int] = mapped_column(Integer, nullable=False)

    # 매도 시만 채움
    realized_profit: Mapped[int | None] = mapped_column(Integer, nullable=True)   # KRW 정수
    realized_profit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 비율 float
    exit_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 관계
    trade_group: Mapped[TradeGroup] = relationship(back_populates="executions")

    def __repr__(self) -> str:
        return (
            f"<TradeExecution {self.execution_type.value} "
            f"{self.price}@{self.quantity} on {self.execution_date}>"
        )

    @property
    def is_buy(self) -> bool:
        return self.execution_type == TradeExecutionType.BUY

    @property
    def is_sell(self) -> bool:
        return self.execution_type in (
            TradeExecutionType.SELL,
            TradeExecutionType.PARTIAL_SELL,
        )

    @property
    def reason_text(self) -> str:
        return self.exit_reason or ""

    # 추가 가독성
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

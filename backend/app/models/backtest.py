"""BacktestRun + BacktestResult 모델.

설계서 07번 7~8절. 정확성 정책 스냅샷 컬럼 (tax_rate_json, priority_method,
random_seed, tick_rounding, use_adjusted_price)을 모두 포함하여 재현성 보장.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
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

from app.db.base import Base, TimestampMixin
from app.models.enums import BacktestStatus

if TYPE_CHECKING:
    from app.models.strategy import Strategy
    from app.models.user import User


class BacktestRun(Base):
    """백테스트 실행 기록.

    실행 당시의 모든 설정 (전략 JSON 스냅샷 + 정확성 정책)을 함께 저장하여
    전략이 나중에 수정되어도 재현 가능.
    """

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # 실행 정보
    run_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    strategy_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    universe_config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # 기간 / 초기자금
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    initial_cash: Mapped[int] = mapped_column(Integer, nullable=False)  # KRW 정수 §14

    # 비용 / 정확성 정책 스냅샷
    fee_rate: Mapped[float] = mapped_column(Float, nullable=False)
    tax_rate_json: Mapped[dict | float | list] = mapped_column(JSON, nullable=False)
    slippage: Mapped[float] = mapped_column(Float, nullable=False)
    execution_price_type: Mapped[str] = mapped_column(String(50), default="next_open", nullable=False)
    use_adjusted_price: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tick_rounding: Mapped[str] = mapped_column(String(50), default="buy_up_sell_down", nullable=False)

    # priority / 결정론
    priority_method: Mapped[str] = mapped_column(String(50), default="trading_value_desc", nullable=False)
    priority_tie_breaker: Mapped[str] = mapped_column(String(50), default="symbol_asc", nullable=False)
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 상태
    status: Mapped[BacktestStatus] = mapped_column(
        SAEnum(BacktestStatus, native_enum=False, length=20),
        default=BacktestStatus.PENDING,
        nullable=False,
        index=True,
    )
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 시각
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 관계
    user: Mapped[User] = relationship()
    strategy: Mapped[Strategy] = relationship()
    result: Mapped[BacktestResult | None] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:
        return f"<BacktestRun id={self.id} status={self.status.value}>"


class BacktestResult(Base, TimestampMixin):
    """백테스트 요약 결과 (1:1 backtest_runs).

    calculate_metrics 결과를 그대로 매핑.
    """

    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # 핵심 지표 (calculate_metrics 키와 동일 의미)
    initial_cash: Mapped[int] = mapped_column(Integer, nullable=False)    # KRW 정수 §14
    final_equity: Mapped[int] = mapped_column(Integer, nullable=False)    # KRW 정수 §14
    total_return_pct: Mapped[float] = mapped_column(Float, nullable=False)  # 비율 float
    annual_return_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mdd_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    trade_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_position_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_holding_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_profit_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_loss_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)

    run: Mapped[BacktestRun] = relationship(back_populates="result")

    def __repr__(self) -> str:
        return (
            f"<BacktestResult run_id={self.run_id} "
            f"return={self.total_return_pct:.2f}% trades={self.trade_count}>"
        )

"""DailyPrice 모델 (일봉, 07번 §12 / 06번 §7 / 13번 §7).

13.7 수정주가 정책:
- `close`(원 가격) + `adj_close`(수정 가격) 둘 다 NOT NULL 보유.
- 가격 조건 / 체결가는 기본 `adj_*`. 거래대금 필터만 `close × volume` 사용.

14.10 결손 정책:
- forward-fill 금지. 결손 봉(거래정지 / 단일가 등)은 `daily_prices`에 row 없음.
- 거래일 여부는 `trading_calendar`로만 판단.

UniqueConstraint(symbol, date) + (symbol, date) 복합 인덱스로 시계열 조회 + 중복 방지.
(date) 단일 인덱스는 날짜별 cross-section 유니버스 조회용 (07번 §18).
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
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.symbol import Symbol


class DailyPrice(Base):
    """일봉.

    BacktestEngine이 PriceLoader를 통해 받게 될 컬럼은 다음과 같다:
        - 원 가격: open / high / low / close / volume
        - 수정 가격: adj_open / adj_high / adj_low / adj_close / adj_volume (13.7)
        - 메타: market_cap (시가총액 시계열, 14.8.3 priority `market_cap_desc`용)

    수정주가 / 거래량은 corporate_action 발생 시 과거 전체 재계산되며 (14.9),
    재계산은 후속 step의 data_pipeline 책임. 본 step은 컬럼만 정의.
    """

    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_daily_prices_symbol_date"),
        Index("ix_daily_prices_symbol_date", "symbol", "date"),
        Index("ix_daily_prices_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("symbols.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)

    # 원 가격 / 거래량 (NOT NULL — 결손 봉은 row 자체가 없음)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)

    # 수정 가격 / 거래량 (13.7 NOT NULL — 정책상 둘 다 계산되어 들어와야 함)
    adj_open: Mapped[float] = mapped_column(Float, nullable=False)
    adj_high: Mapped[float] = mapped_column(Float, nullable=False)
    adj_low: Mapped[float] = mapped_column(Float, nullable=False)
    adj_close: Mapped[float] = mapped_column(Float, nullable=False)
    adj_volume: Mapped[float] = mapped_column(Float, nullable=False)

    # 시가총액 시계열 (14.8.3, priority `market_cap_desc` 결정론용). NULL 허용 — 초기 백필 시 미수집 가능.
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 관계
    symbol_ref: Mapped[Symbol] = relationship(back_populates="daily_prices")

    def __repr__(self) -> str:
        return (
            f"<DailyPrice {self.symbol} {self.date} "
            f"adj_close={self.adj_close} volume={self.volume:.0f}>"
        )

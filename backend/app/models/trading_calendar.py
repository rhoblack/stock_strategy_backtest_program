"""TradingCalendar 모델 (07번 §12-A / 14번 §14 / 13번 §11).

KRX 거래일 / 휴장일을 시장별로 보존.

PK는 (date, market) 복합. 동일 날짜에 KOSPI/KOSDAQ이 모두 거래일인 게 사실상이지만,
설계 문서가 시장별 분리 보존을 권고하므로 그대로 따른다 (장 일부 시장 단축거래일 등 향후 확장 호환).

14.10 결손 정책: 거래일 캘린더가 결손되면 백테스트 실행을 차단해야 한다 (07번 §12-A).
이 정책은 후속 step의 BacktestEngine 통합 시점에서 강제된다.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TradingCalendar(Base):
    """거래일 캘린더.

    `is_trading_day=False`인 row는 휴장일을 명시 (holiday_name 함께 보존).
    `is_trading_day=True`인 row는 정상 거래일 (holiday_name=NULL).

    is_trading_day=True인 (date, market)을 BacktestEngine이 거래일 시퀀스로 사용한다.
    """

    __tablename__ = "trading_calendar"
    __table_args__ = (Index("ix_trading_calendar_market_date", "market", "date"),)

    # 복합 PK: 같은 날짜에 시장별로 1행씩
    date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    market: Mapped[str] = mapped_column(String(20), primary_key=True)  # KOSPI / KOSDAQ

    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    holiday_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        kind = "TRADE" if self.is_trading_day else f"HOLIDAY({self.holiday_name or '-'})"
        return f"<TradingCalendar {self.market} {self.date} {kind}>"

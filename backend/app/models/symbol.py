"""Symbol 모델 (종목 마스터, 07번 §11 / 06번 §6 / 14번 §10).

생존편향 완화(13.13 / 14.10) 정책에 따라 폐지 종목도 보존한다:
- listing_date는 NOT NULL (수집 시 채워야 함)
- delisting_date는 NULL 허용 (NULL = 현재 상장 중)

`is_etf` / `is_etn` / `is_spac` / `is_preferred` / `is_managed` / `is_halted` 플래그는
06번 §8 UniverseSelector의 공통 필터(`exclude_*` 옵션)와 매핑된다.

본 모델은 시장데이터 트랙 1단계의 최소 필수 컬럼만 정의하며,
`shares_outstanding` 등 시가총액 계산에 필요한 추가 컬럼은 후속 step에서 보강한다.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.daily_price import DailyPrice


class Symbol(Base, TimestampMixin):
    """종목 마스터.

    PK는 `symbol`(종목코드 6자리 문자열). KRX 코드체계는 6자리 숫자지만
    문자열 보관 (선두 0 보존, KOSDAQ Q-suffix 등 향후 확장 호환).

    인덱스:
        - (market, listing_date): 특정 시장의 시점 기준 유니버스 조회
        - (delisting_date): 상장폐지 종목 추적
    """

    __tablename__ = "symbols"
    __table_args__ = (
        Index("ix_symbols_market_listing", "market", "listing_date"),
        Index("ix_symbols_delisting_date", "delisting_date"),
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)  # KOSPI / KOSDAQ / KONEX
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 13.13 / 14.10 생존편향: listing_date는 항상 채움, delisting_date는 NULL 허용
    listing_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    delisting_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    # 06번 §8 공통 필터 플래그
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_etn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_spac: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_halted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 관계: 일봉 (daily_prices.symbol → symbols.symbol)
    daily_prices: Mapped[list[DailyPrice]] = relationship(
        back_populates="symbol_ref",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # last_updated_at은 TimestampMixin의 updated_at으로 대체

    def __repr__(self) -> str:
        status = "active" if self.delisting_date is None else f"delisted={self.delisting_date}"
        return f"<Symbol {self.symbol} {self.market} {status}>"

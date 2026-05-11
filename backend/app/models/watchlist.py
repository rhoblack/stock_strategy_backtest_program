"""Watchlist + WatchlistItem 모델.

설계서 07번 13절. 관심종목 그룹을 사용자별로 관리한다.

user_id 스코프 (10번 9절):
    모든 CRUD는 user_id 필터를 강제해야 한다.
    다른 사용자의 watchlist_id 접근 → 404 반환.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Watchlist(Base):
    """관심종목 그룹.

    PK: id (auto-increment int)
    user_id: 소유자. 10.9 scope 정책 — 모든 접근에 user_id 필터 필수.
    """

    __tablename__ = "watchlists"
    __table_args__ = (
        Index("ix_watchlists_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # 관계
    items: Mapped[list[WatchlistItem]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItem.added_at",
    )

    def __repr__(self) -> str:
        return f"<Watchlist id={self.id} user_id={self.user_id} name={self.name!r}>"


class WatchlistItem(Base):
    """관심종목 그룹의 개별 종목.

    복합 유니크: (watchlist_id, symbol) — 같은 그룹에 동일 종목 중복 추가 방지.
    """

    __tablename__ = "watchlist_items"
    __table_args__ = (
        Index("ix_watchlist_items_watchlist_id", "watchlist_id"),
        Index("ix_watchlist_items_wl_sym", "watchlist_id", "symbol", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # 관계
    watchlist: Mapped[Watchlist] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return f"<WatchlistItem watchlist_id={self.watchlist_id} symbol={self.symbol!r}>"

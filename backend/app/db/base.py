"""SQLAlchemy 베이스 + 공통 mixin.

설계서 07번 문서 17절. SQLAlchemy 2.x 스타일 (DeclarativeBase + mapped_column).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """모든 모델이 상속할 베이스. SQLAlchemy 2.x 스타일."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """created_at / updated_at 공통 컬럼.

    timezone-aware UTC datetime 사용 (정확성 정책 13.13).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

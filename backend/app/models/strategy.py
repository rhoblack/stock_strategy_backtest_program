"""Strategy + StrategyVersion 모델.

설계서 07번 5~6절. strategy_json은 02번 schema 형식.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Strategy(Base, TimestampMixin):
    """사용자가 GUI에서 만든 전략.

    soft delete: deleted_at IS NULL인 행만 활성. 관련 백테스트 결과 보존을 위해
    물리 삭제는 하지 않는 것이 권장.
    """

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    strategy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # 관계
    user: Mapped[User] = relationship(back_populates="strategies")
    versions: Mapped[list[StrategyVersion]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.version",
    )

    def __repr__(self) -> str:
        return f"<Strategy id={self.id} name={self.name!r}>"


class StrategyVersion(Base):
    """전략 수정 이력 한 항목.

    한 strategy_id 안에서 version은 1부터 단조 증가.
    """

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    strategy: Mapped[Strategy] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return f"<StrategyVersion strategy_id={self.strategy_id} version={self.version}>"

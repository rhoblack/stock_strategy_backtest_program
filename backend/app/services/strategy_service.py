"""Strategy CRUD + 버전 자동 관리 서비스.

설계서 02번 / 07번 5~6절. update_strategy 호출 시 자동으로 StrategyVersion
한 줄 추가 (감사 / rollback 용도).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import StrategyNotFoundError
from app.models.strategy import Strategy, StrategyVersion


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_strategy(
    session: Session,
    *,
    user_id: int,
    name: str,
    strategy_json: dict[str, Any],
    description: str = "",
    tags: list[str] | None = None,
    favorite: bool = False,
) -> Strategy:
    """전략 생성 + 첫 버전(version=1) 자동 추가."""
    strategy = Strategy(
        user_id=user_id,
        name=name,
        description=description,
        strategy_json=strategy_json,
        tags=list(tags or []),
        favorite=favorite,
    )
    session.add(strategy)
    session.flush()  # PK 발급

    initial_version = StrategyVersion(
        strategy_id=strategy.id,
        version=1,
        strategy_json=copy.deepcopy(strategy_json),
        change_note="초기 버전",
        created_at=_utcnow(),
    )
    session.add(initial_version)
    session.commit()
    session.refresh(strategy)
    return strategy


def update_strategy(
    session: Session,
    strategy_id: int,
    *,
    strategy_json: dict[str, Any] | None = None,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    favorite: bool | None = None,
    change_note: str = "",
) -> Strategy:
    """전략 수정. strategy_json이 변경되면 자동으로 새 StrategyVersion 추가.

    name/description/tags/favorite만 바뀐 경우는 버전 추가하지 않음.
    """
    strategy = get_strategy(session, strategy_id)

    json_changed = strategy_json is not None and strategy_json != strategy.strategy_json

    if name is not None:
        strategy.name = name
    if description is not None:
        strategy.description = description
    if tags is not None:
        strategy.tags = list(tags)
    if favorite is not None:
        strategy.favorite = favorite
    if strategy_json is not None:
        strategy.strategy_json = strategy_json

    if json_changed:
        next_version = _next_version_number(session, strategy_id)
        session.add(
            StrategyVersion(
                strategy_id=strategy_id,
                version=next_version,
                strategy_json=copy.deepcopy(strategy_json),
                change_note=change_note,
                created_at=_utcnow(),
            )
        )

    session.commit()
    session.refresh(strategy)
    return strategy


def duplicate_strategy(session: Session, strategy_id: int, *, new_name: str) -> Strategy:
    """전략 깊은 복사. 새 strategy_id 발급, version=1로 초기화."""
    src = get_strategy(session, strategy_id)
    return create_strategy(
        session,
        user_id=src.user_id,
        name=new_name,
        strategy_json=copy.deepcopy(src.strategy_json),
        description=src.description,
        tags=list(src.tags),
        favorite=False,  # 복사본은 즐겨찾기 해제
    )


def soft_delete_strategy(session: Session, strategy_id: int) -> Strategy:
    """deleted_at 설정. 물리 삭제하지 않음 — 백테스트 결과 보존."""
    strategy = get_strategy(session, strategy_id)
    strategy.deleted_at = _utcnow()
    session.commit()
    session.refresh(strategy)
    return strategy


def list_strategies(
    session: Session,
    *,
    user_id: int,
    include_deleted: bool = False,
) -> list[Strategy]:
    stmt = select(Strategy).where(Strategy.user_id == user_id)
    if not include_deleted:
        stmt = stmt.where(Strategy.deleted_at.is_(None))
    stmt = stmt.order_by(Strategy.updated_at.desc())
    return list(session.scalars(stmt).all())


def get_strategy(
    session: Session,
    strategy_id: int,
    *,
    allow_deleted: bool = False,
) -> Strategy:
    stmt = select(Strategy).where(Strategy.id == strategy_id)
    if not allow_deleted:
        stmt = stmt.where(Strategy.deleted_at.is_(None))
    strategy = session.scalars(stmt).one_or_none()
    if strategy is None:
        raise StrategyNotFoundError(f"Strategy id={strategy_id} 없음")
    return strategy


def list_strategy_versions(session: Session, strategy_id: int) -> list[StrategyVersion]:
    """전략의 버전 이력. version 오름차순."""
    # 먼저 strategy 존재 확인 (없으면 명확한 에러)
    get_strategy(session, strategy_id, allow_deleted=True)
    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version)
    )
    return list(session.scalars(stmt).all())


# === 내부 ===


def _next_version_number(session: Session, strategy_id: int) -> int:
    from sqlalchemy import func

    stmt = select(func.max(StrategyVersion.version)).where(
        StrategyVersion.strategy_id == strategy_id
    )
    current_max = session.scalar(stmt) or 0
    return current_max + 1

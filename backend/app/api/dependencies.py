"""FastAPI 공통 의존성.

MVP는 단일 시스템 유저 (id=1). 멀티유저 인증은 Phase 4 후속.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import make_session_factory
from app.main_state import get_engine


def get_db_session() -> Iterator[Session]:
    SessionLocal = make_session_factory(get_engine())
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user_id() -> int:
    """MVP는 user_id=1 시스템 유저 (인증 없음)."""
    return 1
